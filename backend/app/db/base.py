"""
app/db/base.py
───────────────────────────────────────────────────────────────────────────────
SQLAlchemy declarative base.

All ORM models (students, users, attendance_records, face_embeddings, etc.)
defined in `app/models/` will inherit from `Base`. Centralising the base
class here ensures:

  • Alembic's `env.py` can import a single `Base.metadata` for autogenerate
    migrations.
  • No circular imports between individual model modules.

This file intentionally contains NO model definitions — those belong to
`app/models/*.py` in a later phase. It also defines a small mixin with
common timestamp columns that future models can reuse for consistency.
───────────────────────────────────────────────────────────────────────────────
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
    Shared declarative base for all ORM models.

    Usage (future phase):
        from app.db.base import Base

        class Student(Base):
            __tablename__ = "students"
            id: Mapped[int] = mapped_column(primary_key=True)
            ...
    """
    pass


class TimestampMixin:
    """
    Optional mixin providing `created_at` / `updated_at` columns.

    Future models can opt in via multiple inheritance:
        class Student(Base, TimestampMixin):
            ...
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
