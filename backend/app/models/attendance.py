"""
app/models/attendance.py
───────────────────────────────────────────────────────────────────────────────
ORM model for attendance records.

Maps to the `attendance_records` table from the architecture's schema.

Replaces the desktop app's per-session in-memory cooldown dict
(`_AttendanceManager._marked`) with a database-enforced
UNIQUE(student_id, date) constraint: a student can have at most one
attendance row per calendar date. The recognition service catches the
resulting IntegrityError / pre-checks via `has_record_for_date` queries and
responds with "Attendance already marked" rather than inserting a duplicate.

Status semantics (all derived automatically by the service layer):
  PRESENT — student recognised from CHECKIN_START through CHECKIN_LATE.
  LATE    — student recognised from CHECKIN_LATE through CHECKIN_CLOSE.
  ABSENT  — generated at end-of-day for every active student who has no
             recognition record for that date.

`student_id` is nullable and uses ON DELETE SET NULL so that hard-deleting
a student preserves attendance history (the FK becomes NULL but
`student_name` and `student_code` remain populated for display).
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import enum
from datetime import date as date_, time as time_
from typing import TYPE_CHECKING

from sqlalchemy import Date, Enum, Float, ForeignKey, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.student import Student


class AttendanceStatus(str, enum.Enum):
    """
    Attendance status values.

    All values are derived automatically by the service layer — no API
    caller or UI component should set these directly.

    PRESENT : Student recognised from CHECKIN_START through CHECKIN_LATE.
    LATE    : Student recognised from CHECKIN_LATE through CHECKIN_CLOSE.
    ABSENT  : Generated at end-of-day for active students with no record.
    """
    PRESENT = "Present"
    LATE    = "Late"
    ABSENT  = "Absent"


class ConfidenceBand(str, enum.Enum):
    """
    Mirrors RecognitionResult.confidence_band from the desktop app's
    utils/similarity.py: 'high' (>=0.85), 'medium' (>=threshold), 'low' (<threshold).
    """
    HIGH   = "high"
    MEDIUM = "medium"
    LOW    = "low"


class AttendanceRecord(Base, TimestampMixin):
    """
    A single attendance entry for a student on a given date.

    Columns
    ───────
    id                : Primary key.
    student_id        : FK → students.id. SET NULL on student hard-delete;
                         NULL means the student no longer exists but the
                         record is preserved via student_name / student_code.
    student_name      : Denormalized display name (copied at record creation).
    student_code      : Denormalized institutional code (copied at record
                         creation). Indexed for history queries by code.
    date              : Calendar date of the attendance event.
    time              : Time-of-day the event was recorded.
    similarity_score  : Cosine similarity score [0, 1] from the recognition
                         engine.  Set to 0.0 for ABSENT records (no scan).
    confidence_band   : 'high' | 'medium' | 'low'.  LOW for ABSENT records.
    status            : 'Present' | 'Late' | 'Absent'.
    device_id         : Optional identifier for the camera/kiosk that
                         recorded the event (multi-device deployments).

    Constraints
    ───────────
    UNIQUE(student_id, date) — at most one attendance row per student per
    day.  The service's `generate_absent_records_for_date` checks this
    before inserting to avoid duplicates.

    Relationships
    ─────────────
    student : back-reference to the owning Student.

    created_at / updated_at are provided by TimestampMixin.
    """

    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint("student_id", "date", name="uq_attendance_student_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    student_id: Mapped[int | None] = mapped_column(
        ForeignKey("students.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Denormalized identity fields — populated when the record is created
    # and retained permanently so history remains readable even after the
    # student row is deleted (student_id becomes NULL at that point).
    student_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    student_code: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    date: Mapped[date_] = mapped_column(Date, nullable=False, index=True)
    time: Mapped[time_] = mapped_column(Time, nullable=False)

    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)

    confidence_band: Mapped[ConfidenceBand] = mapped_column(
        Enum(ConfidenceBand, name="confidence_band", native_enum=False, length=10),
        nullable=False,
        default=ConfidenceBand.MEDIUM,
    )

    status: Mapped[AttendanceStatus] = mapped_column(
        Enum(AttendanceStatus, name="attendance_status", native_enum=False, length=10),
        nullable=False,
        default=AttendanceStatus.PRESENT,
    )

    device_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ── Relationships ────────────────────────────────────────────────────
    student: Mapped["Student | None"] = relationship(back_populates="attendance_records")

    def __repr__(self) -> str:
        return (
            f"<AttendanceRecord id={self.id} student_id={self.student_id} "
            f"date={self.date} status={self.status}>"
        )
