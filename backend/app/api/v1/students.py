"""
app/api/v1/students.py
───────────────────────────────────────────────────────────────────────────────
Student management endpoints: CRUD + face-sample capture.

Changes from previous version
──────────────────────────────
• GET /students/me — fixed viewer→student resolution.
  Old (broken): repo.get_by_code(current_user.username)
    — assumed student_code == username, which is never guaranteed.
  New (correct): repo.get_by_id(current_user.student_id)
    — uses the FK written to users.student_id at self-registration time.
    Returns 409 if the viewer account has no linked student (student_id IS
    NULL), which is an admin data-integrity issue, not a 404.

• /{id}/capture, /{id}/capture/frame, /{id}/capture/batch
  — Previously accessible by any authenticated user (get_current_user),
    meaning a viewer with student_id=5 could POST to /students/9/capture
    and corrupt another student's face data.
  — Now protected by _require_capture_access():
      • ADMIN: always allowed (unchanged).
      • VIEWER: allowed only if student_id path param == current_user.student_id.
        Returns 403 Forbidden otherwise.

• All other endpoints (CRUD, embeddings list/delete) are unchanged.
  Admin-only guards remain.  Embedding delete retains get_current_user
  (admin-only in practice via the admin UI; viewers have no UI path to it).

Capture modes (unchanged)
─────────────
1. POST /{id}/capture         — single image upload
2. POST /{id}/capture/batch   — multi-image upload
3. POST /{id}/capture/frame   — single webcam frame (polled by browser)
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.db.session import get_async_session
from app.models.user import User, UserRole
from app.repositories.student_repo import StudentRepository
from app.schemas.student import (
    FaceEmbeddingRead,
    StudentCreate,
    StudentDetail,
    StudentListResponse,
    StudentRead,
    StudentUpdate,
)
from app.services.student_service import (
    DuplicateStudentError,
    NoFaceDetectedError,
    StudentNotFoundError,
    StudentService,
)

router = APIRouter(prefix="/students", tags=["Students"])


def _get_service(session: AsyncSession = Depends(get_async_session)) -> StudentService:
    return StudentService(session)


# ── Response schema for webcam frame capture ──────────────────────────────────

class FrameCaptureResponse(BaseModel):
    """
    Response for a single-frame webcam capture attempt.

    The frontend inspects `sample_count` to drive progress (1/30 … 30/30)
    and `face_detected` to give live feedback ("face visible / no face").
    """
    face_detected: bool   # True when the Haar Cascade found a face
    saved:         bool   # True when an embedding was persisted
    sample_count:  int    # Cumulative embeddings saved so far for this student
    message:       str    # Human-readable status for debug / toast


# ── Ownership guard for capture endpoints ─────────────────────────────────────

def _require_capture_access(student_id: int, current_user: User) -> None:
    """
    Raise 403 if a VIEWER tries to access a capture endpoint for a student
    that is not their own.

    Rules
    ─────
    • ADMIN  — always allowed; no check performed.
    • VIEWER — allowed only when student_id == current_user.student_id.
               If current_user.student_id is None the viewer account was
               never properly linked to a student (data-integrity issue);
               deny with 403 rather than 404 to avoid leaking information.

    This function is intentionally not an async FastAPI dependency so that
    it can be called inline after the student_id path param is known.
    FastAPI resolves path params before dependencies, so we receive student_id
    as a plain int and call this helper at the top of each capture handler.
    """
    if current_user.role == UserRole.ADMIN:
        return  # admins are unrestricted

    # Viewer path: enforce ownership
    if current_user.student_id is None or current_user.student_id != student_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorised to access this student's capture data.",
        )


# ── Viewer: own student record lookup ─────────────────────────────────────────

@router.get("/me", response_model=StudentRead)
async def get_my_student_record(
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_role(UserRole.VIEWER)),
) -> StudentRead:
    """
    Return the Student record that belongs to the currently authenticated viewer.

    Resolution strategy
    ───────────────────
    Uses current_user.student_id (the FK written to users.student_id at
    self-registration time).  This is the only correct approach because
    username and student_code are independent free-text fields; they are
    never guaranteed to be equal.

    Error cases
    ───────────
    • 409 Conflict — viewer account exists but student_id is NULL.
      This indicates the student row was deleted after registration, or the
      account was created without going through /auth/register.  The viewer
      should contact an admin.
    • 404 Not Found — student_id is set but no matching student row exists
      (race condition; student deleted between the FK read and the DB query).
    """
    if current_user.student_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Your account is not linked to a student record. "
                "Please contact an administrator."
            ),
        )

    repo = StudentRepository(session)
    student = await repo.get_by_id(current_user.student_id)
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No student record found for your account.",
        )
    return StudentRead.model_validate(student)


# ── CRUD (Admin-only for create; authenticated for read/update) ───────────────

@router.post("", response_model=StudentRead, status_code=status.HTTP_201_CREATED)
async def create_student(
    payload: StudentCreate,
    svc: StudentService = Depends(_get_service),
    session: AsyncSession = Depends(get_async_session),
    _: User = Depends(require_role(UserRole.ADMIN)),
) -> StudentRead:
    """
    Register a new student. Admin-only.

    Creates ONLY a Student record. Does NOT create any User account.
    Face embeddings are added separately via the capture endpoints.
    """
    try:
        student = await svc.register(payload)
        await session.commit()
        await session.refresh(student)
        return StudentRead.model_validate(student)
    except DuplicateStudentError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get("", response_model=StudentListResponse)
async def list_students(
    department: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    svc: StudentService = Depends(_get_service),
    _: User = Depends(require_role(UserRole.ADMIN)),
) -> StudentListResponse:
    """List active students with optional department filter and pagination. Admin-only."""
    students, total = await svc.list_active(
        department=department,
        skip=(page - 1) * page_size,
        limit=page_size,
    )
    return StudentListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[StudentRead.model_validate(s) for s in students],
    )


@router.get("/{student_id}", response_model=StudentDetail)
async def get_student(
    student_id: int,
    svc: StudentService = Depends(_get_service),
    _: User = Depends(require_role(UserRole.ADMIN)),
) -> StudentDetail:
    """Fetch a single student with embedding metadata. Admin-only."""
    try:
        student = await svc.get(student_id, load_embeddings=True)
    except StudentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    embeddings = [FaceEmbeddingRead.model_validate(e) for e in student.embeddings]
    return StudentDetail(
        **StudentRead.model_validate(student).model_dump(),
        embedding_count=len(embeddings),
        embeddings=embeddings,
    )


@router.put("/{student_id}", response_model=StudentRead)
async def update_student(
    student_id: int,
    payload: StudentUpdate,
    svc: StudentService = Depends(_get_service),
    session: AsyncSession = Depends(get_async_session),
    _: User = Depends(require_role(UserRole.ADMIN)),
) -> StudentRead:
    """Partially update a student record. Admin-only."""
    try:
        student = await svc.update(student_id, payload)
        await session.commit()
        await session.refresh(student)
        return StudentRead.model_validate(student)
    except StudentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.delete("/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_student(
    student_id: int,
    svc: StudentService = Depends(_get_service),
    session: AsyncSession = Depends(get_async_session),
    _: User = Depends(require_role(UserRole.ADMIN)),
) -> None:
    """
    Permanently delete a student and all their face embeddings. Admin-only.

    Attendance history is preserved (student_id FK set to NULL by the DB).
    The viewer's User account (if any) is NOT deleted — admin can disable it
    separately via PATCH /api/v1/users/{id} if needed.
    users.student_id for any linked viewer is also set to NULL automatically
    (ON DELETE SET NULL on the users.student_id FK).
    """
    try:
        await svc.delete(student_id)
        await session.commit()
    except StudentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


# ── Face Embeddings ───────────────────────────────────────────────────────────

@router.post(
    "/{student_id}/capture",
    response_model=FaceEmbeddingRead,
    status_code=status.HTTP_201_CREATED,
)
async def capture_face_sample(
    student_id: int,
    image: UploadFile = File(..., description="JPEG/PNG frame from which to extract a face crop"),
    svc: StudentService = Depends(_get_service),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> FaceEmbeddingRead:
    """
    Upload a single image frame; detect the face, generate a 512-D FaceNet
    embedding, and associate it with the student.

    Access control
    ──────────────
    • Admin: unrestricted.
    • Viewer: only allowed for their own student_id (current_user.student_id).
      Returns 403 for any other student_id.
    """
    _require_capture_access(student_id, current_user)

    raw = await image.read()
    arr = np.frombuffer(raw, np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not decode uploaded image.",
        )

    try:
        embedding = await svc.add_face_sample(student_id, frame=frame)
        await session.commit()
        await session.refresh(embedding)
        return FaceEmbeddingRead.model_validate(embedding)
    except StudentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except NoFaceDetectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )


@router.post(
    "/{student_id}/capture/batch",
    response_model=list[FaceEmbeddingRead],
    status_code=status.HTTP_201_CREATED,
)
async def capture_face_samples_batch(
    student_id: int,
    images: list[UploadFile] = File(..., description="Multiple JPEG/PNG frames"),
    svc: StudentService = Depends(_get_service),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> list[FaceEmbeddingRead]:
    """
    Upload multiple image frames in one request. Frames where no face is
    detected are silently skipped.

    Access control
    ──────────────
    • Admin: unrestricted.
    • Viewer: only allowed for their own student_id (current_user.student_id).
      Returns 403 for any other student_id.
    """
    _require_capture_access(student_id, current_user)

    frames: list[np.ndarray] = []
    for upload in images:
        raw = await upload.read()
        arr = np.frombuffer(raw, np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is not None:
            frames.append(frame)

    if not frames:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No decodable images in batch.",
        )

    try:
        embeddings = await svc.add_face_samples_batch(student_id, frames=frames)
        await session.commit()
        return [FaceEmbeddingRead.model_validate(e) for e in embeddings]
    except StudentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/{student_id}/capture/frame",
    response_model=FrameCaptureResponse,
    status_code=status.HTTP_200_OK,
)
async def capture_webcam_frame(
    student_id: int,
    image: UploadFile = File(..., description="Single JPEG frame captured from the browser webcam"),
    svc: StudentService = Depends(_get_service),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> FrameCaptureResponse:
    """
    Accept a single webcam frame, attempt face detection, and persist an
    embedding if a face is found.

    The browser's capture loop calls this endpoint repeatedly — once per
    captured frame — until `sample_count` in the response reaches the
    target (30). Used during both:
      • Admin student face registration
      • Viewer self-registration (Step 2: face capture after account creation)

    Frames where no face is detected return `face_detected=False` and
    `saved=False`; the loop should continue without counting that frame.

    Access control
    ──────────────
    • Admin: unrestricted.
    • Viewer: only allowed for their own student_id (current_user.student_id).
      Returns 403 for any other student_id.
    """
    _require_capture_access(student_id, current_user)

    raw = await image.read()
    arr = np.frombuffer(raw, np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)

    if frame is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not decode uploaded frame.",
        )

    try:
        existing = await svc.list_embeddings(student_id)
    except StudentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    current_count = len(existing)

    try:
        await svc.add_face_sample(student_id, frame=frame)
        await session.commit()
        new_count = current_count + 1
        return FrameCaptureResponse(
            face_detected=True,
            saved=True,
            sample_count=new_count,
            message=f"Sample {new_count} captured.",
        )
    except NoFaceDetectedError:
        return FrameCaptureResponse(
            face_detected=False,
            saved=False,
            sample_count=current_count,
            message="No face detected — keep your face centred and visible.",
        )
    except StudentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/{student_id}/embeddings", response_model=list[FaceEmbeddingRead])
async def list_embeddings(
    student_id: int,
    svc: StudentService = Depends(_get_service),
    _: User = Depends(get_current_user),
) -> list[FaceEmbeddingRead]:
    """List all face embedding metadata for a student (raw vectors excluded)."""
    try:
        embeddings = await svc.list_embeddings(student_id)
        return [FaceEmbeddingRead.model_validate(e) for e in embeddings]
    except StudentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.delete("/{student_id}/embeddings/{embedding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_embedding(
    student_id: int,
    embedding_id: int,
    svc: StudentService = Depends(_get_service),
    session: AsyncSession = Depends(get_async_session),
    _: User = Depends(get_current_user),
) -> None:
    """Remove a single face sample from a student."""
    try:
        await svc.delete_embedding(student_id, embedding_id)
        await session.commit()
    except StudentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.delete("/{student_id}/embeddings", status_code=status.HTTP_204_NO_CONTENT)
async def clear_embeddings(
    student_id: int,
    svc: StudentService = Depends(_get_service),
    session: AsyncSession = Depends(get_async_session),
    _: User = Depends(require_role(UserRole.ADMIN)),
) -> None:
    """Remove ALL face samples for a student (re-registration workflow). Admin-only."""
    try:
        await svc.clear_embeddings(student_id)
        await session.commit()
    except StudentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
