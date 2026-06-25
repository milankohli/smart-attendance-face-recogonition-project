"""
app/schemas/attendance.py
───────────────────────────────────────────────────────────────────────────────
Pydantic schemas for attendance records.

Correspond to app.models.attendance.AttendanceRecord.

Status is NOT a user-supplied field.  It is always derived by the service
layer from the time of recognition (Present / Late) or generated at
end-of-day (Absent).  The `status` field is intentionally absent from
AttendanceMarkRequest so that no API caller can override it.
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from datetime import date as date_, datetime, time as time_

from pydantic import BaseModel, ConfigDict, Field

from app.models.attendance import AttendanceStatus, ConfidenceBand


# ═══════════════════════════════════════════════════════════════════════════════
# Requests
# ═══════════════════════════════════════════════════════════════════════════════

class AttendanceMarkRequest(BaseModel):
    """
    Payload for POST /attendance/mark — admin manual override, or the
    internal call made by the recognition service after a successful match.

    `date` and `time` default to "now" at the service layer if omitted;
    included here as optional fields to support admin backdating of records.

    `status` is intentionally omitted — it is always computed by
    AttendanceService._derive_status() based on the record time.
    """
    student_id: int
    date: date_ | None = None
    time: time_ | None = None
    similarity_score: float = Field(default=1.0, ge=0.0, le=1.0)
    confidence_band: ConfidenceBand = ConfidenceBand.HIGH
    device_id: str | None = Field(default=None, max_length=100)


class AttendanceQueryParams(BaseModel):
    """
    Common filter parameters for GET /attendance.

    `status` accepts only the three user-visible values: Present, Late, Absent.
    """
    student_id: int | None = None
    date: date_ | None = None
    start_date: date_ | None = None
    end_date: date_ | None = None
    status: AttendanceStatus | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=500)


# ═══════════════════════════════════════════════════════════════════════════════
# Responses
# ═══════════════════════════════════════════════════════════════════════════════

class AttendanceRead(BaseModel):
    """Single attendance record as returned by list/detail endpoints."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int | None
    date: date_
    time: time_
    similarity_score: float
    confidence_band: ConfidenceBand
    status: AttendanceStatus
    device_id: str | None = None
    created_at: datetime


class AttendanceReadWithStudent(AttendanceRead):
    """
    Attendance record enriched with the student's display name and code —
    avoids a second round-trip from the frontend's AttendanceTable.
    """
    student_name: str | None = None
    student_code: str | None = None


class AttendanceListResponse(BaseModel):
    """Paginated response for GET /attendance."""
    total: int
    page: int
    page_size: int
    items: list[AttendanceReadWithStudent]


class AttendanceMarkResponse(BaseModel):
    """
    Response for POST /attendance/mark and the recognition pipeline's
    internal marking step.

    `already_marked=True` corresponds to the desktop app's
    "Attendance already marked" banner — no new row was inserted.
    """
    already_marked: bool
    record: AttendanceRead | None = None
    message: str
