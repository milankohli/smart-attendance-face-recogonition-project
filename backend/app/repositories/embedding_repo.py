"""
app/repositories/embedding_repo.py
───────────────────────────────────────────────────────────────────────────────
Repository for FaceEmbedding CRUD and in-memory cosine similarity search.

The central method here is `find_nearest`, which loads stored embeddings
(persisted as JSON via the `_FloatListJSON` column type — see
app/models/embedding.py) and computes cosine similarity in NumPy. This
mirrors the desktop app's in-process NumPy cosine search over a pickled
embedding store.

NOTE: This repository previously used pgvector's `<=>` distance operator
and `cast(..., Vector(EMBEDDING_DIM))`. After the migration to plain JSON
storage (see app/models/embedding.py docstring), `FaceEmbedding.embedding`
is a TEXT column — pgvector operators/casts against it raise a database
error (surfaced to clients as a 500 on /recognition/identify). The pgvector
extension is therefore no longer required; everything below is pure
Python/NumPy.

The cosine similarity score returned to callers is in [-1, 1] (practically
[0, 1] for normalised FaceNet vectors), where 1.0 means identical vectors
and 0.0 means orthogonal.
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from typing import NamedTuple, Sequence

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.embedding import EMBEDDING_DIM, FaceEmbedding

log = get_logger(__name__)


class EmbeddingMatch(NamedTuple):
    """Result of a nearest-neighbour search."""

    embedding: FaceEmbedding
    similarity: float  # [0, 1] — higher is more similar


class EmbeddingRepository:
    """Data-access layer for the `face_embeddings` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Read ──────────────────────────────────────────────────────────────

    async def get_by_id(self, embedding_id: int) -> FaceEmbedding | None:
        """Fetch a FaceEmbedding by primary key."""
        return await self._session.get(FaceEmbedding, embedding_id)

    async def list_for_student(self, student_id: int) -> Sequence[FaceEmbedding]:
        """Return all stored embeddings for a given student (for audit/display)."""
        stmt = (
            select(FaceEmbedding)
            .where(FaceEmbedding.student_id == student_id)
            .order_by(FaceEmbedding.created_at)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def count_for_student(self, student_id: int) -> int:
        """Return how many face samples are stored for a student."""
        stmt = (
            select(func.count())
            .select_from(FaceEmbedding)
            .where(FaceEmbedding.student_id == student_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def find_nearest(
        self,
        query_vector: list[float],
        *,
        top_k: int = 5,
        student_ids: list[int] | None = None,
    ) -> list[EmbeddingMatch]:
        """
        Return the `top_k` most similar stored embeddings to `query_vector`,
        ranked by cosine similarity (highest first).

        Args:
            query_vector: The 512-D FaceNet embedding to search against.
            top_k:        Number of nearest neighbours to return.
            student_ids:  Optional whitelist — restrict search to these
                          student IDs (e.g. for department-scoped auth).

        Returns:
            List of EmbeddingMatch(embedding, similarity) sorted from
            highest to lowest similarity. Returns an empty list if there
            are no stored embeddings to compare against (callers — see
            AttendanceService.process_frame — treat an empty list as
            "no registered students" rather than an error).

        Notes:
            • Rows whose stored vector length doesn't match `EMBEDDING_DIM`
              (or the query vector's length) are skipped with a warning
              rather than raising — a single malformed row should not
              crash the whole recognition request.
            • Zero-norm vectors (all-zero embeddings) are skipped to avoid
              division-by-zero in the cosine similarity computation.
            • `embedding.student` is eagerly loaded via selectinload so
              `match.embedding.student_id` / `match.embedding.student` are
              always safely accessible without a lazy-load on the async
              session.
        """
        if not query_vector:
            log.warning("find_nearest called with an empty query vector")
            return []

        if len(query_vector) != EMBEDDING_DIM:
            raise ValueError(
                f"Query vector has {len(query_vector)} dimensions; "
                f"expected {EMBEDDING_DIM}."
            )

        query_arr = np.asarray(query_vector, dtype=np.float64)
        query_norm = float(np.linalg.norm(query_arr))
        if query_norm == 0.0:
            log.warning("find_nearest called with a zero-norm query vector")
            return []

        # Load all candidate rows (with student relationship pre-loaded so
        # `match.embedding.student` / `.student_id` never trigger a lazy
        # load on the async session).
        stmt = select(FaceEmbedding).options(selectinload(FaceEmbedding.student))
        if student_ids is not None:
            stmt = stmt.where(FaceEmbedding.student_id.in_(student_ids))

        result = await self._session.execute(stmt)
        rows: Sequence[FaceEmbedding] = result.scalars().all()

        if not rows:
            log.debug("find_nearest: no stored embeddings to compare against")
            return []

        scored: list[tuple[float, FaceEmbedding]] = []
        for row in rows:
            # `_FloatListJSON.process_result_value` already deserialised
            # this to list[float]; defend against None / malformed rows
            # (e.g. NULL or a row written before the dimension was fixed).
            stored = row.embedding
            if stored is None:
                log.warning(
                    "Skipping embedding row with NULL vector",
                    extra={"ctx_embedding_id": row.id, "ctx_student_id": row.student_id},
                )
                continue

            stored_arr = np.asarray(stored, dtype=np.float64)
            if stored_arr.shape != query_arr.shape:
                log.warning(
                    "Skipping embedding row with mismatched dimensions",
                    extra={
                        "ctx_embedding_id": row.id,
                        "ctx_student_id": row.student_id,
                        "ctx_stored_shape": stored_arr.shape,
                        "ctx_query_shape": query_arr.shape,
                    },
                )
                continue

            stored_norm = float(np.linalg.norm(stored_arr))
            if stored_norm == 0.0:
                log.warning(
                    "Skipping embedding row with zero-norm vector",
                    extra={"ctx_embedding_id": row.id, "ctx_student_id": row.student_id},
                )
                continue

            similarity = float(np.dot(query_arr, stored_arr) / (query_norm * stored_norm))
            scored.append((similarity, row))

        if not scored:
            log.debug("find_nearest: no comparable embeddings after validation")
            return []

        scored.sort(key=lambda pair: pair[0], reverse=True)
        top = scored[:top_k]

        matches = [
            EmbeddingMatch(embedding=row, similarity=similarity)
            for similarity, row in top
        ]
        log.debug(
            "Nearest-neighbour search complete",
            extra={"ctx_top_k": top_k, "ctx_candidates": len(rows), "ctx_results": len(matches)},
        )
        return matches

    async def get_mean_embedding_for_student(
        self, student_id: int
    ) -> list[float] | None:
        """
        Compute the per-student mean embedding in NumPy.

        This mirrors the desktop app's `EmbeddingStore.get_mean_embeddings()`.
        Returns None if the student has no stored embeddings, or if none of
        the stored rows have a usable (non-null, correctly-dimensioned)
        vector.

        Note: The result is NOT L2-normalised. Callers that need a unit
        vector (e.g. for cosine similarity) should normalise using
        `numpy.linalg.norm`.
        """
        rows = await self.list_for_student(student_id)
        vectors = [
            np.asarray(row.embedding, dtype=np.float64)
            for row in rows
            if row.embedding is not None and len(row.embedding) == EMBEDDING_DIM
        ]
        if not vectors:
            return None
        mean = np.mean(np.stack(vectors), axis=0)
        return mean.tolist()

    # ── Write ─────────────────────────────────────────────────────────────

    async def create(
        self,
        *,
        student_id: int,
        embedding: list[float],
        source_image_path: str | None = None,
    ) -> FaceEmbedding:
        """
        Persist a new face embedding for a student.

        Args:
            student_id:        ID of the owning Student row.
            embedding:         512-D float vector from FaceNet.
            source_image_path: Optional path/URL to the face crop in
                               object storage (for audit/inspection).
        """
        if len(embedding) != EMBEDDING_DIM:
            raise ValueError(
                f"Embedding has {len(embedding)} dimensions; "
                f"expected {EMBEDDING_DIM}."
            )
        record = FaceEmbedding(
            student_id=student_id,
            embedding=embedding,
            source_image_path=source_image_path,
        )
        self._session.add(record)
        await self._session.flush()
        log.info(
            "FaceEmbedding created",
            extra={"ctx_embedding_id": record.id, "ctx_student_id": student_id},
        )
        return record

    async def delete(self, embedding: FaceEmbedding) -> None:
        """Remove a single embedding row. The student's other samples are unaffected."""
        await self._session.delete(embedding)
        await self._session.flush()
        log.info(
            "FaceEmbedding deleted",
            extra={"ctx_embedding_id": embedding.id, "ctx_student_id": embedding.student_id},
        )

    async def delete_all_for_student(self, student_id: int) -> int:
        """
        Remove all embeddings for a student (e.g. on re-registration).

        Returns the number of rows deleted.
        """
        embeddings = await self.list_for_student(student_id)
        count = len(embeddings)
        for emb in embeddings:
            await self._session.delete(emb)
        await self._session.flush()
        log.info(
            "All embeddings deleted for student",
            extra={"ctx_student_id": student_id, "ctx_count": count},
        )
        return count
