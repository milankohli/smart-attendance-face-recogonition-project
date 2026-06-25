"""
app/api/v1/attendance.py
───────────────────────────────────────────────────────────────────────────────
Attendance CRUD endpoints: list, retrieve, manual mark, delete.
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.db.session import get_async_session
from app.models.attendance import AttendanceStatus
from app.models.user import User, UserRole
from app.repositories.attendance_repo import AttendanceRepository
from app.schemas.attendance import (
    AttendanceListResponse,
    AttendanceMarkRequest,
    AttendanceMarkResponse,
    AttendanceQueryParams,
    AttendanceRead,
)
from app.services.attendance_service import (
    AttendanceService,
    AttendanceWindowNotStartedError,
)

router = APIRouter(prefix="/attendance", tags=["Attendance"])


def _get_service(session: AsyncSession = Depends(get_async_session)) -> AttendanceService:
    return AttendanceService(session)


@router.get("", response_model=AttendanceListResponse)
async def list_attendance(
    student_id: int | None = Query(default=None),
    date_on: date | None = Query(default=None, alias="date"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    status_filter: AttendanceStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    svc: AttendanceService = Depends(_get_service),
    _: User = Depends(get_current_user),
) -> AttendanceListResponse:
    """
    List attendance records with optional filters. Results are paginated and
    include the student's name and code for display convenience.

    The `status` filter accepts: Present, Late, Absent.
    """
    params = AttendanceQueryParams(
        student_id=student_id,
        date=date_on,
        start_date=start_date,
        end_date=end_date,
        status=status_filter,
        page=page,
        page_size=page_size,
    )
    return await svc.list_records(params)


@router.get("/me", response_model=AttendanceListResponse)
async def list_my_attendance(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=500),
    svc: AttendanceService = Depends(_get_service),
    current_user: User = Depends(get_current_user),
) -> AttendanceListResponse:
    """
    Return attendance records for the authenticated viewer only.

    The student_id is read exclusively from the JWT claim — no client-supplied
    value is accepted.  This ensures a viewer can never query another student's
    records, regardless of what parameters are sent.

    Requires the User account to have an associated student_id (set during
    viewer registration).  Returns HTTP 403 if the link is missing.
    """
    if current_user.student_id is None:
        from fastapi import HTTPException, status as http_status
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Your account is not linked to a student record.",
        )
    return await svc.list_my_attendance(
        current_user.student_id,
        page=page,
        page_size=page_size,
    )


@router.get("/{record_id}", response_model=AttendanceRead)
async def get_attendance_record(
    record_id: int,
    session: AsyncSession = Depends(get_async_session),
    _: User = Depends(get_current_user),
) -> AttendanceRead:
    """Fetch a single attendance record by ID."""
    repo = AttendanceRepository(session)
    record = await repo.get_by_id(record_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Attendance record id={record_id} not found.",
        )
    return AttendanceRead.model_validate(record)


@router.post("/mark", response_model=AttendanceMarkResponse, status_code=status.HTTP_200_OK)
async def mark_attendance(
    payload: AttendanceMarkRequest,
    svc: AttendanceService = Depends(_get_service),
    session: AsyncSession = Depends(get_async_session),
    _: User = Depends(get_current_user),
) -> AttendanceMarkResponse:
    """
    Manually mark attendance for a student (admin override or backdating).

    Attendance status (Present / Late) is derived automatically from the
    supplied `time` field (or the current server time if omitted) — it is
    not accepted as a request parameter.

    Returns `already_marked=True` if a record already exists for the
    student on the given date — no duplicate is created.
    """
    try:
        result = await svc.mark_manual(
            student_id=payload.student_id,
            on_date=payload.date,
            at_time=payload.time,
            similarity_score=payload.similarity_score,
            confidence_band=payload.confidence_band,
            device_id=payload.device_id,
        )
    except AttendanceWindowNotStartedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if not result.already_marked:
        await session.commit()
    return result


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attendance_record(
    record_id: int,
    session: AsyncSession = Depends(get_async_session),
    _: User = Depends(require_role(UserRole.ADMIN)),
) -> None:
    """Delete an attendance record. Admin-only (for corrections)."""
    repo = AttendanceRepository(session)
    record = await repo.get_by_id(record_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Attendance record id={record_id} not found.",
        )
    await repo.delete(record)
    await session.commit()
