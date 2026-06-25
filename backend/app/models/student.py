"""
app/models/student.py
───────────────────────────────────────────────────────────────────────────────
ORM model for registered students/persons.

Maps to the `students` table. A Student has:
  • many FaceEmbedding rows  (one per captured sample, 512-D vectors)
  • many AttendanceRecord rows (one per day, enforced by a unique
    constraint on the AttendanceRecord side)

Hard-delete is used for student removal. Attendance records are preserved
on delete (FK becomes NULL via ON DELETE SET NULL; student_name /
student_code remain on the attendance row for display). Face embeddings
are cascade-deleted when the student is removed.
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.attendance import AttendanceRecord
    from app.models.embedding import FaceEmbedding


class Student(Base, TimestampMixin):
    """
    A registered person tracked by the attendance system.

    Columns
    ───────
    id            : Primary key.
    name          : Full display name.
    student_code  : Unique institutional ID / roll number.
    email         : Optional contact email.
    department    : Optional department/class grouping.
    photo_path    : Path/URL to the primary reference photo in object storage.

    Relationships
    ─────────────
    embeddings  : List[FaceEmbedding] — all captured face samples.
    attendance_records : List[AttendanceRecord] — full attendance history.

    created_at / updated_at are provided by TimestampMixin.
    """

    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    student_code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    photo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ── Relationships ────────────────────────────────────────────────────
    embeddings: Mapped[list["FaceEmbedding"]] = relationship(
        back_populates="student",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    attendance_records: Mapped[list["AttendanceRecord"]] = relationship(
        back_populates="student",
        # No ORM cascade — the DB handles SET NULL via ondelete="SET NULL"
        # on the AttendanceRecord.student_id FK. This preserves attendance
        # history when a student is hard-deleted.
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Student id={self.id} code={self.student_code!r} name={self.name!r}>"
