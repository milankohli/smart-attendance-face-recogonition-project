"""
app/models/embedding.py
───────────────────────────────────────────────────────────────────────────────
ORM model for FaceNet face embeddings.

Maps to the `face_embeddings` table. Each row represents ONE captured face
sample for a student (mirroring the desktop app's per-sample embeddings in
`embeddings/face_embeddings.pkl` / `labels.pkl`).

Storage format
──────────────
The 512-D embedding is stored as a PostgreSQL JSON column (list of floats).
This requires no PostgreSQL extensions and works with a plain PostgreSQL
installation out of the box.

The pgvector `Vector(512)` type used previously required:
    CREATE EXTENSION IF NOT EXISTS vector;
which is not available on all PostgreSQL deployments. JSON storage is fully
portable and sufficient for the service-layer cosine-similarity search that
loads all embeddings into memory (matching the desktop app's approach).

When/if pgvector becomes available in the target environment, the column
type can be migrated to Vector(512) via a single Alembic migration — no
service-layer code changes are needed because the serialise/deserialise
helpers below maintain the same list[float] Python interface.

EMBEDDING_DIM = 512 matches FaceNet's InceptionResnetV1 output dimension,
consistent with Config.EMBEDDING_DIM in the desktop application.
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, String, Text, TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.student import Student

EMBEDDING_DIM = 512


class _FloatListJSON(TypeDecorator):
    """
    Custom SQLAlchemy type that persists a list[float] as a JSON TEXT column.

    • Python side : list[float]  (e.g. [0.123, -0.456, ...])
    • Database side: TEXT containing a JSON array (e.g. "[0.123, -0.456, ...]")

    This avoids the pgvector extension while keeping the Python interface
    identical to what the service layer expects.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: list[float] | None, dialect: Any) -> str | None:
        """Serialise list[float] → JSON string before INSERT/UPDATE."""
        if value is None:
            return None
        return json.dumps(value)

    def process_result_value(self, value: str | None, dialect: Any) -> list[float] | None:
        """Deserialise JSON string → list[float] after SELECT."""
        if value is None:
            return None
        return json.loads(value)


class FaceEmbedding(Base, TimestampMixin):
    """
    A single 512-D FaceNet embedding for a student, plus a reference to the
    cropped source image used to generate it (for audit/inspection,
    mirroring `registered_faces/<name>/photo_face_0.jpg` in the desktop app).

    Columns
    ───────
    id                 : Primary key.
    student_id         : FK → students.id. ON DELETE CASCADE — embeddings
                          are removed automatically if the student is
                          hard-deleted.
    embedding          : 512-D float vector stored as JSON TEXT.
                          Python type is list[float]; no pgvector required.
    source_image_path  : Path/URL to the saved face crop in object storage.

    Relationships
    ─────────────
    student : back-reference to the owning Student.

    created_at / updated_at are provided by TimestampMixin.

    Note on "mean embedding":
    The desktop app's `EmbeddingStore.get_mean_embeddings()` computed one
    L2-normalised mean vector per person at load time. In this schema that
    can be reproduced in the service layer by loading all embeddings into
    memory and computing the mean with numpy — no SQL aggregate needed
    since all embeddings for a student are fetched together anyway.
    """

    __tablename__ = "face_embeddings"

    id: Mapped[int] = mapped_column(primary_key=True)

    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Stored as JSON TEXT; no pgvector extension required.
    # The _FloatListJSON TypeDecorator handles serialisation transparently.
    embedding: Mapped[list[float]] = mapped_column(
        _FloatListJSON,
        nullable=False,
        comment="512-D FaceNet embedding serialised as a JSON float array",
    )

    source_image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ── Relationships ────────────────────────────────────────────────────
    student: Mapped["Student"] = relationship(back_populates="embeddings")

    def __repr__(self) -> str:
        return f"<FaceEmbedding id={self.id} student_id={self.student_id}>"
