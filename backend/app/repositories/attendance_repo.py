"""
app/repositories/attendance_repo.py
───────────────────────────────────────────────────────────────────────────────
Repository for AttendanceRecord CRUD and analytics queries.

Duplicate-attendance prevention is enforced at two levels:
  1. Database: UNIQUE(student_id, date) constraint on `attendance_records`.
  2. Application: `has_record_for_date` check before attempting an insert,
     so the service layer can return a clean "already marked" response
     without relying on catching an IntegrityError (though callers SHOULD
     still handle that as a final safety net).

Analytics methods mirror the desktop app's dashboard.py stats:
  - daily attendance counts
  - per-student frequency
  - monthly totals
  - unknown-detection summaries (retired; always returns 0 — UNKNOWN status
    was removed from AttendanceStatus and unknown faces are no longer stored)
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from datetime import date as date_
from typing import Sequence

from sqlalchemy import Date, String, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.attendance import AttendanceRecord, AttendanceStatus, ConfidenceBand
from app.models.student import Student

log = get_logger(__name__)


class AttendanceRepository:
    """Data-access layer for the `attendance_records` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Duplicate-prevention helpers ──────────────────────────────────────

    async def has_record_for_date(
        self,
        student_id: int,
        *,
        on_date: date_ | None = None,
    ) -> bool:
        """
        Return True if any attendance record already exists for `student_id`
        on `on_date` (defaults to today).

        This is the application-level guard that mirrors the desktop app's
        `_AttendanceManager._marked` cooldown set. The DB-level
        UNIQUE(student_id, date) remains the authoritative enforcer.
        """
        check_date = on_date or date_.today()
        stmt = select(func.count()).select_from(AttendanceRecord).where(
            AttendanceRecord.student_id == student_id,
            AttendanceRecord.date == check_date,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one() > 0

    async def is_present_today(self, student_id: int, *, on_date: date_ | None = None) -> bool:
        """
        Backward-compatible alias for the old duplicate guard name.

        The method now checks for any status, not only PRESENT, because a
        student can have at most one record per attendance date.
        """
        return await self.has_record_for_date(student_id, on_date=on_date)

    async def get_for_student_on_date(
        self,
        student_id: int,
        on_date: date_,
    ) -> AttendanceRecord | None:
        """Fetch the attendance record for a student on a specific date, if any."""
        stmt = select(AttendanceRecord).where(
            AttendanceRecord.student_id == student_id,
            AttendanceRecord.date == on_date,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    # ── Read ──────────────────────────────────────────────────────────────

    async def get_by_id(self, record_id: int) -> AttendanceRecord | None:
        """Fetch an AttendanceRecord by primary key."""
        return await self._session.get(AttendanceRecord, record_id)

    async def list(
        self,
        *,
        student_id: int | None = None,
        on_date: date_ | None = None,
        start_date: date_ | None = None,
        end_date: date_ | None = None,
        status: AttendanceStatus | None = None,
        load_student: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[AttendanceRecord]:
        """
        Flexible listing of attendance records with optional filters.

        Args:
            student_id:   Filter to one student.
            on_date:      Exact date match (takes priority over start/end range).
            start_date:   Range start (inclusive).
            end_date:     Range end (inclusive).
            status:       Filter by AttendanceStatus.
            load_student: Eagerly load the `student` relationship (avoids
                          N+1 when rendering names in list responses).
            skip, limit:  Pagination.
        """
        stmt = select(AttendanceRecord)
        if load_student:
            stmt = stmt.options(selectinload(AttendanceRecord.student))
        if student_id is not None:
            stmt = stmt.where(AttendanceRecord.student_id == student_id)
        if on_date is not None:
            stmt = stmt.where(AttendanceRecord.date == on_date)
        else:
            if start_date is not None:
                stmt = stmt.where(AttendanceRecord.date >= start_date)
            if end_date is not None:
                stmt = stmt.where(AttendanceRecord.date <= end_date)
        if status is not None:
            stmt = stmt.where(AttendanceRecord.status == status)
        stmt = stmt.order_by(AttendanceRecord.date.desc(), AttendanceRecord.time.desc())
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def count(
        self,
        *,
        student_id: int | None = None,
        on_date: date_ | None = None,
        start_date: date_ | None = None,
        end_date: date_ | None = None,
        status: AttendanceStatus | None = None,
    ) -> int:
        """
        Count attendance records matching the given filters.

        Args:
            student_id:  Filter to one student.
            on_date:     Exact date match (takes priority over start/end range).
            start_date:  Range start (inclusive).
            end_date:    Range end (inclusive).
            status:      Filter by AttendanceStatus.
        """
        stmt = select(func.count()).select_from(AttendanceRecord)
        if student_id is not None:
            stmt = stmt.where(AttendanceRecord.student_id == student_id)
        if on_date is not None:
            # Exact-date filter: supersedes any start/end range
            stmt = stmt.where(AttendanceRecord.date == on_date)
        else:
            if start_date is not None:
                stmt = stmt.where(AttendanceRecord.date >= start_date)
            if end_date is not None:
                stmt = stmt.where(AttendanceRecord.date <= end_date)
        if status is not None:
            stmt = stmt.where(AttendanceRecord.status == status)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def count_today(self) -> int:
        """Count today's PRESENT records (for the dashboard summary card)."""
        return await self.count(on_date=date_.today(), status=AttendanceStatus.PRESENT)

    async def count_unknown_detections(self) -> int:
        """
        Return the count of unknown-face detections (dashboard card).

        Always returns 0: AttendanceStatus.UNKNOWN was removed from the enum
        and unknown faces are no longer written to `attendance_records`.
        Kept for backward compatibility with analytics_service.py callers.
        """
        return 0

    # ── Write ─────────────────────────────────────────────────────────────

    async def create(
        self,
        *,
        student_id: int | None,
        on_date: date_,
        at_time,
        similarity_score: float,
        confidence_band: ConfidenceBand,
        status: AttendanceStatus,
        device_id: str | None = None,
    ) -> AttendanceRecord:
        """
        Insert a new attendance record.

        Does NOT check for duplicates — callers should call
        `has_record_for_date` first, or handle sqlalchemy.exc.IntegrityError.
        """
        record = AttendanceRecord(
            student_id=student_id,
            date=on_date,
            time=at_time,
            similarity_score=similarity_score,
            confidence_band=confidence_band,
            status=status,
            device_id=device_id,
        )
        self._session.add(record)
        await self._session.flush()
        log.info(
            "AttendanceRecord created",
            extra={
                "ctx_record_id": record.id,
                "ctx_student_id": student_id,
                "ctx_date": str(on_date),
                "ctx_status": status.value,
            },
        )
        return record

    async def delete(self, record: AttendanceRecord) -> None:
        """Remove an attendance record (admin correction)."""
        await self._session.delete(record)
        await self._session.flush()
        log.warning(
            "AttendanceRecord deleted",
            extra={"ctx_record_id": record.id, "ctx_student_id": record.student_id},
        )

    # ── Analytics queries ─────────────────────────────────────────────────

    async def daily_counts(
        self,
        start_date: date_,
        end_date: date_,
    ) -> list[dict]:
        """
        Return per-day attendance totals for the given date range.

        Result schema (maps to DailyAttendancePoint):
            [{"date": date, "unique_students": int, "total_entries": int}, ...]
        """
        stmt = (
            select(
                AttendanceRecord.date,
                func.count(AttendanceRecord.student_id.distinct()).label("unique_students"),
                func.count(AttendanceRecord.id).label("total_entries"),
            )
            .where(
                AttendanceRecord.date >= start_date,
                AttendanceRecord.date <= end_date,
                AttendanceRecord.status == AttendanceStatus.PRESENT,
            )
            .group_by(AttendanceRecord.date)
            .order_by(AttendanceRecord.date)
        )
        result = await self._session.execute(stmt)
        return [
            {"date": row.date, "unique_students": row.unique_students, "total_entries": row.total_entries}
            for row in result
        ]

    async def frequency_by_student(
        self,
        *,
        start_date: date_ | None = None,
        end_date: date_ | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """
        Return per-student attendance frequency.

        Result schema (maps to StudentAttendanceFrequency):
            [{"student_id": int, "days_present": int, "total_entries": int,
              "first_seen": date, "last_seen": date, "avg_similarity": float}, ...]
        """
        stmt = (
            select(
                AttendanceRecord.student_id,
                func.count(AttendanceRecord.date.distinct()).label("days_present"),
                func.count(AttendanceRecord.id).label("total_entries"),
                func.min(AttendanceRecord.date).label("first_seen"),
                func.max(AttendanceRecord.date).label("last_seen"),
                func.avg(AttendanceRecord.similarity_score).label("avg_similarity"),
            )
            .where(
                AttendanceRecord.student_id.is_not(None),
                AttendanceRecord.status == AttendanceStatus.PRESENT,
            )
        )
        if start_date:
            stmt = stmt.where(AttendanceRecord.date >= start_date)
        if end_date:
            stmt = stmt.where(AttendanceRecord.date <= end_date)
        stmt = (
            stmt.group_by(AttendanceRecord.student_id)
            .order_by(func.count(AttendanceRecord.id).desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [
            {
                "student_id": row.student_id,
                "days_present": row.days_present,
                "total_entries": row.total_entries,
                "first_seen": row.first_seen,
                "last_seen": row.last_seen,
                "avg_similarity": float(row.avg_similarity) if row.avg_similarity else None,
            }
            for row in result
        ]

    async def monthly_counts(self, *, year: int | None = None) -> list[dict]:
        """
        Return monthly attendance totals.

        Result schema (maps to MonthlyAttendancePoint):
            [{"month": "YYYY-MM", "total_entries": int}, ...]
        """
        month_label = func.to_char(AttendanceRecord.date, "YYYY-MM").label("month")
        stmt = (
            select(month_label, func.count(AttendanceRecord.id).label("total_entries"))
            .where(AttendanceRecord.status == AttendanceStatus.PRESENT)
        )
        if year is not None:
            stmt = stmt.where(func.extract("year", AttendanceRecord.date) == year)
        stmt = stmt.group_by(month_label).order_by(month_label)
        result = await self._session.execute(stmt)
        return [{"month": row.month, "total_entries": row.total_entries} for row in result]
