"""
app/models/user.py
───────────────────────────────────────────────────────────────────────────────
ORM model for authentication accounts.

Maps to the `users` table. Two roles only:
  • ADMIN  — full system access (dashboard, students, attendance, analytics,
             export, user management).
             Admin accounts are created manually in the database or by an
             existing admin via POST /api/v1/users.  They are NOT publicly
             creatable.
  • VIEWER — a self-registered student.  Created via the public
             POST /auth/register endpoint, where the viewer supplies their
             own username and password.  Role is always forced to VIEWER
             by the registration endpoint — it cannot be escalated.

Changes from previous version
──────────────────────────────
• Added `student_id` FK column (Integer, nullable, FK → students.id).

  WHY a migration IS required
  ───────────────────────────
  The previous architecture resolved the viewer→student link by assuming
  student_code == username (a fragile convention, not a schema constraint).
  Because username and student_code are independent free-text fields chosen
  by the user at registration, no reliable join was possible without a proper
  FK.  Adding `users.student_id → students.id` is the only correct fix.

  Migration summary
  ─────────────────
  ALTER TABLE users
      ADD COLUMN student_id INTEGER NULL
          REFERENCES students(id) ON DELETE SET NULL;
  CREATE INDEX ix_users_student_id ON users(student_id);

  The column is nullable so that:
    • Existing admin accounts (which have no linked student) are unaffected.
    • If a student record is deleted the viewer account survives with
      student_id = NULL (same ON DELETE SET NULL behaviour as attendance rows).

  No data migration script is required for existing rows because:
    • Existing viewer accounts were broken by the username==student_code
      assumption anyway — they need to be re-linked manually or re-registered.
    • Admin accounts simply remain NULL.
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class UserRole(str, enum.Enum):
    """Role-based access control levels."""
    ADMIN  = "admin"
    VIEWER = "viewer"


class User(Base, TimestampMixin):
    """
    Authentication account used to log in to the system.

    Columns
    ───────
    id              : Primary key.
    username        : Unique login identifier chosen by the user on registration.
    email           : Contact email (required for viewers; optional for admins).
    hashed_password : bcrypt hash (see app.core.security.hash_password).
    role            : 'admin' or 'viewer' — enforced via RBAC dependencies.
    is_active       : Soft-disable flag; inactive users cannot log in.
    last_login      : Updated by the auth service on successful login.
    student_id      : FK → students.id.  Set on viewer self-registration;
                      NULL for admin accounts and for viewers whose student
                      record has been deleted.

    created_at / updated_at are provided by TimestampMixin.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    username:        Mapped[str]           = mapped_column(String(50),  unique=True, index=True, nullable=False)
    email:           Mapped[str | None]    = mapped_column(String(255), unique=True, index=True, nullable=True)
    hashed_password: Mapped[str]           = mapped_column(String(255), nullable=False)

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=False, length=20),
        default=UserRole.VIEWER,
        nullable=False,
    )

    is_active:  Mapped[bool]           = mapped_column(Boolean,              default=True,  nullable=False)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),            nullable=True)

    # ── Viewer → Student link ──────────────────────────────────────────────
    # Nullable: admin accounts have no linked student.
    # ON DELETE SET NULL: viewer account survives if admin deletes the student.
    student_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("students.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        default=None,
    )

    # Lazy relationship — only loaded when explicitly accessed.
    # back_populates is intentionally omitted here; Student does not need a
    # back-reference to User for any current feature.
    student: Mapped["Student | None"] = relationship(  # type: ignore[name-defined]
        "Student",
        foreign_keys=[student_id],
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role}>"
