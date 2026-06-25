"""
app/models/__init__.py
───────────────────────────────────────────────────────────────────────────────
Convenience re-exports and metadata registration.

Importing this package ensures all ORM models are registered against
`Base.metadata` (app/db/base.py) — required for:
  • Alembic autogenerate migrations (`target_metadata = Base.metadata`)
  • SQLAlchemy relationship resolution between Student, FaceEmbedding,
    and AttendanceRecord (string-based `Mapped["..."]` references)

Usage (Alembic env.py, later phase):
    from app.db.base import Base
    import app.models  # noqa: F401  — registers all models
    target_metadata = Base.metadata
───────────────────────────────────────────────────────────────────────────────
"""

from app.models.user import User, UserRole  # noqa: F401
from app.models.student import Student  # noqa: F401
from app.models.embedding import FaceEmbedding, EMBEDDING_DIM  # noqa: F401
from app.models.attendance import (  # noqa: F401
    AttendanceRecord,
    AttendanceStatus,
    ConfidenceBand,
)

__all__ = [
    "User",
    "UserRole",
    "Student",
    "FaceEmbedding",
    "EMBEDDING_DIM",
    "AttendanceRecord",
    "AttendanceStatus",
    "ConfidenceBand",
]
