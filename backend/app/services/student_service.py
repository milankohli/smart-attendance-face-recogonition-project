"""
app/services/student_service.py
───────────────────────────────────────────────────────────────────────────────
Business logic for student/person registration and face-embedding management.

Orchestrates:
  • StudentRepository    — persisting/fetching/deleting student rows
  • EmbeddingRepository — persisting/fetching 512-D face embeddings
  • EmbeddingGenerator (ML layer) — generating embeddings from raw frames
  • FaceDetector (ML layer)       — detecting and cropping faces

Changes from previous version
──────────────────────────────
• REMOVED: UserRepository dependency — this service no longer creates or
  manages User accounts. Viewer account creation is now handled exclusively
  by POST /auth/register (public self-registration).

• REMOVED: _ensure_viewer_account() — the entire auto-account-creation
  method has been deleted. No user accounts are ever created here.

• REMOVED: Viewer account deactivation in delete() — deleting a student
  no longer touches the users table. The viewer's User account is managed
  separately (admin can disable via /users endpoint if needed).

• REMOVED: hash_password import — no longer needed in this service.

• add_face_sample() — the call to _ensure_viewer_account() at the bottom
  of the method has been removed. Embedding logic is unchanged.

Admin student registration creates ONLY a Student record + face embeddings.
It does NOT create any User account.
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.ml.embedding_generator import EmbeddingGenerator
from app.ml.face_detector import FaceDetector
from app.models.embedding import EMBEDDING_DIM, FaceEmbedding
from app.models.student import Student
from app.repositories.embedding_repo import EmbeddingRepository
from app.repositories.student_repo import StudentRepository
from app.schemas.student import StudentCreate, StudentUpdate

log = get_logger(__name__)


class StudentServiceError(Exception):
    """Base exception for StudentService business-logic errors."""


class DuplicateStudentError(StudentServiceError):
    """Raised when a student_code or email already exists."""


class StudentNotFoundError(StudentServiceError):
    """Raised when a student lookup returns no result."""


class NoFaceDetectedError(StudentServiceError):
    """Raised when the face detector finds no face in a submitted frame."""


class StudentService:
    """
    Business-logic layer for student/person management and face registration.

    All methods are async and operate within the provided SQLAlchemy
    AsyncSession. Commits are left to the caller / unit-of-work boundary
    (typically the FastAPI route); all mutations only flush.

    This service does NOT touch the users table.  User/viewer account
    lifecycle is handled by the auth router (self-registration) and the
    users router (admin management).
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        face_detector: FaceDetector | None = None,
        embedding_generator: EmbeddingGenerator | None = None,
    ) -> None:
        self._session = session
        self._student_repo = StudentRepository(session)
        self._embedding_repo = EmbeddingRepository(session)
        # Allow injection in tests; default to singletons otherwise
        self._detector = face_detector or FaceDetector()
        self._embedder = embedding_generator or EmbeddingGenerator()

    # ── Student CRUD ──────────────────────────────────────────────────────

    async def register(self, payload: StudentCreate) -> Student:
        """
        Create a new student/person record.

        Called by:
          • Admin routes (POST /students) — creates student + face data only,
            no User account.
          • Auth registration flow (POST /auth/register) — the auth router
            calls StudentRepository.create() directly and handles User creation
            itself; this method is NOT called in that flow.

        Raises:
            DuplicateStudentError: if student_code or email already exists.
        """
        # Guard: duplicate code
        existing = await self._student_repo.get_by_code(payload.student_code)
        if existing:
            raise DuplicateStudentError(
                f"A person with code '{payload.student_code}' already exists "
                f"(id={existing.id})."
            )
        # Guard: duplicate email
        if payload.email:
            existing_email = await self._student_repo.get_by_email(str(payload.email))
            if existing_email:
                raise DuplicateStudentError(
                    f"A person with email '{payload.email}' already exists."
                )

        student = await self._student_repo.create(
            name=payload.name,
            student_code=payload.student_code,
            email=str(payload.email) if payload.email else None,
            department=payload.department,
        )
        log.info(
            "Person registered",
            extra={"ctx_student_id": student.id, "ctx_student_code": student.student_code},
        )
        return student

    async def get(self, student_id: int, *, load_embeddings: bool = False) -> Student:
        """
        Fetch a student/person by ID.

        Raises:
            StudentNotFoundError: if no student with the given ID exists.
        """
        student = await self._student_repo.get_by_id(student_id, load_embeddings=load_embeddings)
        if student is None:
            raise StudentNotFoundError(f"Person id={student_id} not found.")
        return student

    async def list_active(
        self,
        *,
        department: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[Student], int]:
        """
        Return (students, total_count) for active persons.

        The total count is fetched via a separate COUNT query so the
        router can build a paginated response without loading all rows.
        """
        students = await self._student_repo.list_active(
            department=department, skip=skip, limit=limit
        )
        total = await self._student_repo.count_active()
        return students, total

    async def update(self, student_id: int, payload: StudentUpdate) -> Student:
        """
        Apply a partial update to a student record.

        Raises:
            StudentNotFoundError: if no student with the given ID exists.
        """
        student = await self.get(student_id)
        update_data = payload.model_dump(exclude_none=True)
        # Normalise EmailStr → plain str for SQLAlchemy
        if "email" in update_data and update_data["email"] is not None:
            update_data["email"] = str(update_data["email"])
        await self._student_repo.update(student, **update_data)
        return student

    async def delete(self, student_id: int) -> None:
        """
        Permanently delete a student and all their face embeddings.

        Attendance records for the student are preserved: the DB sets their
        student_id FK to NULL (ON DELETE SET NULL) while student_name and
        student_code remain on each record for historical display.

        NOTE: This method does NOT touch the users table. If the student had
        a viewer account (created via self-registration), that User record is
        left intact. An admin can disable it separately via PATCH /users/{id}.
        This preserves the principle that User accounts are decoupled from
        Student records in the new flow.

        Raises:
            StudentNotFoundError: if no student with the given ID exists.
        """
        student = await self.get(student_id)

        # Delete all face embeddings explicitly first so the embedding
        # repository can log them individually and clean up file references.
        await self._embedding_repo.delete_all_for_student(student_id)

        # Hard-delete the student row. The ORM cascades to any remaining
        # embeddings; the DB ON DELETE SET NULL nullifies attendance FKs.
        await self._student_repo.delete(student)
        log.info(
            "Student permanently deleted",
            extra={
                "ctx_student_id": student_id,
                "ctx_student_code": student.student_code,
            },
        )

    # ── Face Registration ──────────────────────────────────────────────────

    async def add_face_sample(
        self,
        student_id: int,
        *,
        frame: np.ndarray,
        save_crop: bool = True,
    ) -> FaceEmbedding:
        """
        Detect a face in `frame`, generate its 512-D FaceNet embedding,
        and persist it as a FaceEmbedding for the given student.

        This method ONLY creates face embeddings. It does NOT create any
        User account. Auto-VIEWER-account creation has been removed.

        Args:
            student_id:  ID of the student to associate the embedding with.
            frame:       BGR numpy array (as returned by OpenCV VideoCapture).
            save_crop:   If True, save the aligned face crop to MEDIA_ROOT
                         and store its path in `source_image_path`.

        Returns:
            The newly created FaceEmbedding row.

        Raises:
            StudentNotFoundError: if the student doesn't exist.
            NoFaceDetectedError:  if the detector finds no face in the frame.
        """
        student = await self.get(student_id)

        # Detect and crop the face region
        face_crop = self._detector.detect_and_crop(frame)
        if face_crop is None:
            raise NoFaceDetectedError(
                f"No face detected in the submitted frame for person id={student_id}."
            )

        # Generate the embedding from the aligned crop
        embedding_vector: list[float] = self._embedder.generate(face_crop)

        # Optionally save the face crop image
        source_image_path: str | None = None
        if save_crop:
            source_image_path = await self._save_face_crop(
                student_id=student_id,
                face_crop=face_crop,
            )

        # Persist the embedding
        embedding = await self._embedding_repo.create(
            student_id=student.id,
            embedding=embedding_vector,
            source_image_path=source_image_path,
        )
        log.info(
            "Face sample added",
            extra={"ctx_student_id": student_id, "ctx_embedding_id": embedding.id},
        )

        # NOTE: _ensure_viewer_account() has been removed.
        # Viewer accounts are created during self-registration (POST /auth/register)
        # before face capture begins — never auto-created here.

        return embedding

    async def add_face_samples_batch(
        self,
        student_id: int,
        *,
        frames: list[np.ndarray],
    ) -> list[FaceEmbedding]:
        """
        Register multiple frames in one call (mirrors the desktop app's
        capture loop that collects N samples per student).

        Frames where no face is detected are skipped with a warning rather
        than raising an exception — this allows a batch of, say, 10 frames
        to succeed even if 1 or 2 had poor lighting.

        Returns:
            List of successfully created FaceEmbedding rows.
        """
        embeddings: list[FaceEmbedding] = []
        for i, frame in enumerate(frames):
            try:
                emb = await self.add_face_sample(student_id, frame=frame)
                embeddings.append(emb)
            except NoFaceDetectedError:
                log.warning(
                    "No face detected in batch frame — skipped",
                    extra={"ctx_student_id": student_id, "ctx_frame_index": i},
                )
        log.info(
            "Batch face registration complete",
            extra={
                "ctx_student_id": student_id,
                "ctx_frames_submitted": len(frames),
                "ctx_embeddings_created": len(embeddings),
            },
        )
        return embeddings

    async def list_embeddings(self, student_id: int) -> Sequence[FaceEmbedding]:
        """Return all stored face samples for a student (metadata only, no raw vectors)."""
        await self.get(student_id)  # existence check
        return await self._embedding_repo.list_for_student(student_id)

    async def delete_embedding(self, student_id: int, embedding_id: int) -> None:
        """
        Remove a single face sample from a student.

        Raises:
            StudentNotFoundError: if the student doesn't exist.
            ValueError:           if the embedding doesn't belong to this student.
        """
        await self.get(student_id)
        embedding = await self._embedding_repo.get_by_id(embedding_id)
        if embedding is None or embedding.student_id != student_id:
            raise ValueError(
                f"Embedding id={embedding_id} not found for person id={student_id}."
            )
        await self._embedding_repo.delete(embedding)

    async def clear_embeddings(self, student_id: int) -> int:
        """
        Remove all face samples for a student (re-registration workflow).

        Returns the number of rows deleted.
        """
        await self.get(student_id)
        return await self._embedding_repo.delete_all_for_student(student_id)

    # ── Internal helpers ──────────────────────────────────────────────────

    async def _save_face_crop(self, student_id: int, face_crop: np.ndarray) -> str:
        """
        Save an aligned face crop to MEDIA_ROOT and return its relative path.

        Creates the directory structure:
            <MEDIA_ROOT>/faces/<student_id>/face_<timestamp>.jpg
        """
        import cv2
        from datetime import datetime

        base_dir = Path(settings.MEDIA_ROOT) / "faces" / str(student_id)
        base_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"face_{timestamp}.jpg"
        filepath = base_dir / filename

        cv2.imwrite(str(filepath), face_crop)
        relative_path = str(filepath)
        log.debug("Face crop saved", extra={"ctx_path": relative_path})
        return relative_path
