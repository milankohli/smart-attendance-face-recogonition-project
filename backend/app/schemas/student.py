"""
app/schemas/student.py
───────────────────────────────────────────────────────────────────────────────
Pydantic schemas for students and their face embeddings.

Correspond to app.models.student.Student and app.models.embedding.FaceEmbedding.
No endpoint logic here — request/response shapes only, for the future
`/students/*` router.
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.embedding import EMBEDDING_DIM


# ═══════════════════════════════════════════════════════════════════════════════
# Requests
# ═══════════════════════════════════════════════════════════════════════════════

class StudentCreate(BaseModel):
    """Payload for POST /students."""
    name: str = Field(..., min_length=1, max_length=150, examples=["Alice Smith"])
    student_code: str = Field(..., min_length=1, max_length=50, examples=["CS-2023-001"])
    email: EmailStr | None = None
    department: str | None = Field(default=None, max_length=100)


class StudentUpdate(BaseModel):
    """
    Payload for PUT /students/{id}.

    All fields optional — only provided fields are updated (partial update).
    """
    name: str | None = Field(default=None, min_length=1, max_length=150)
    email: EmailStr | None = None
    department: str | None = Field(default=None, max_length=100)
    photo_path: str | None = Field(default=None, max_length=500)


class FaceEmbeddingCreate(BaseModel):
    """
    Internal/service-layer payload for persisting one captured embedding.

    Used by POST /students/{id}/capture once the recognition service has
    generated an embedding from an uploaded/streamed frame. Not typically
    sent directly by the frontend (which sends images, not raw vectors),
    but defined here for completeness and for internal service calls.
    """
    embedding: list[float] = Field(..., min_length=EMBEDDING_DIM, max_length=EMBEDDING_DIM)
    source_image_path: str | None = Field(default=None, max_length=500)


# ═══════════════════════════════════════════════════════════════════════════════
# Responses
# ═══════════════════════════════════════════════════════════════════════════════

class FaceEmbeddingRead(BaseModel):
    """
    Embedding metadata returned by GET /students/{id}/embeddings.

    The raw vector is intentionally excluded from API responses (large,
    not useful to the frontend) — only metadata is exposed.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    source_image_path: str | None = None
    created_at: datetime


class StudentRead(BaseModel):
    """Representation of a student returned by list/detail endpoints."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    student_code: str
    email: EmailStr | None = None
    department: str | None = None
    photo_path: str | None = None
    created_at: datetime
    updated_at: datetime


class StudentDetail(StudentRead):
    """
    Extended student representation including embedding metadata and
    a summary count — returned by GET /students/{id}.
    """
    embedding_count: int = 0
    embeddings: list[FaceEmbeddingRead] = []


class StudentListResponse(BaseModel):
    """Paginated response for GET /students."""
    total: int
    page: int
    page_size: int
    items: list[StudentRead]
