"""
app/api/v1/analytics.py
───────────────────────────────────────────────────────────────────────────────
Dashboard analytics endpoints — mirrors the desktop app's stat cards and
matplotlib charts.
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_async_session
from app.models.user import User
from app.schemas.analytics import (
    AnalyticsSummary,
    DailyAttendanceResponse,
    MonthlyAttendanceResponse,
    StudentAttendanceFrequencyResponse,
)
from app.services.attendance_service import AttendanceService

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def _get_service(session: AsyncSession = Depends(get_async_session)) -> AttendanceService:
    return AttendanceService(session)


@router.get("/summary", response_model=AnalyticsSummary)
async def get_summary(
    svc: AttendanceService = Depends(_get_service),
    _: User = Depends(get_current_user),
) -> AnalyticsSummary:
    """
    Top-level dashboard stats: registered students, today's attendance,
    all-time records, unknown detections.
    """
    return await svc.get_summary()


@router.get("/daily", response_model=DailyAttendanceResponse)
async def get_daily(
    start_date: date = Query(default_factory=lambda: date.today() - timedelta(days=29)),
    end_date: date = Query(default_factory=date.today),
    svc: AttendanceService = Depends(_get_service),
    _: User = Depends(get_current_user),
) -> DailyAttendanceResponse:
    """
    Per-day unique-student and total-entry counts for the given date range.
    Defaults to the last 30 days.
    """
    return await svc.get_daily(start_date, end_date)


@router.get("/by-student", response_model=StudentAttendanceFrequencyResponse)
async def get_by_student(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    svc: AttendanceService = Depends(_get_service),
    _: User = Depends(get_current_user),
) -> StudentAttendanceFrequencyResponse:
    """
    Per-student attendance frequency: days present, total entries, first/last
    seen dates, and average similarity score.
    """
    return await svc.get_by_student(
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


@router.get("/monthly", response_model=MonthlyAttendanceResponse)
async def get_monthly(
    year: int | None = Query(default=None, description="Filter to a specific year (e.g. 2026)"),
    svc: AttendanceService = Depends(_get_service),
    _: User = Depends(get_current_user),
) -> MonthlyAttendanceResponse:
    """Monthly attendance totals, optionally filtered to a single year."""
    return await svc.get_monthly(year=year)
