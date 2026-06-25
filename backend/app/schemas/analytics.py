"""
app/schemas/analytics.py
───────────────────────────────────────────────────────────────────────────────
Pydantic schemas for dashboard and analytics endpoints.

Correspond to the future `/analytics/*` router and mirror the desktop
dashboard's stat cards and matplotlib charts (dashboard.py):
  • Summary cards: registered people, today's count, total records,
    unknown detections.
  • Daily attendance (bar chart)
  • Attendance frequency by person (bar chart)
  • Monthly attendance (bar chart)

No endpoint logic here — response shapes only.
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from datetime import date as date_

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════════════
# Summary cards — GET /analytics/summary
# ═══════════════════════════════════════════════════════════════════════════════

class AnalyticsSummary(BaseModel):
    """
    Top-level dashboard statistics, mirroring dashboard.py's stat cards:
    Registered People, Today's Attendance, Total Records, Unknown Detections.
    """
    total_students: int = Field(..., description="Total active registered students")
    today_attendance_count: int = Field(..., description="Attendance records for today")
    total_attendance_records: int = Field(..., description="All-time attendance record count")
    unknown_detections_count: int = Field(..., description="Total 'Unknown' status records")
    attendance_date: date_ = Field(..., description="Hostel attendance date used for status counts")
    present_count: int = Field(..., description="Present records for attendance_date")
    late_count: int = Field(..., description="Late records for attendance_date")
    absent_count: int = Field(..., description="Absent records for attendance_date")


# ═══════════════════════════════════════════════════════════════════════════════
# Daily attendance — GET /analytics/daily
# ═══════════════════════════════════════════════════════════════════════════════

class DailyAttendancePoint(BaseModel):
    """One bar in the 'Daily Attendance' chart."""
    date: date_
    unique_students: int = Field(..., description="Distinct students present on this date")
    total_entries: int = Field(..., description="Total attendance rows on this date")


class DailyAttendanceResponse(BaseModel):
    """Response for GET /analytics/daily?start_date=...&end_date=..."""
    start_date: date_
    end_date: date_
    points: list[DailyAttendancePoint]


# ═══════════════════════════════════════════════════════════════════════════════
# Attendance by student — GET /analytics/by-student
# ═══════════════════════════════════════════════════════════════════════════════

class StudentAttendanceFrequency(BaseModel):
    """One bar in the 'Attendance by Person' chart."""
    student_id: int
    student_name: str
    student_code: str
    days_present: int
    total_entries: int
    first_seen: date_ | None = None
    last_seen: date_ | None = None
    avg_similarity: float | None = None


class StudentAttendanceFrequencyResponse(BaseModel):
    """Response for GET /analytics/by-student."""
    items: list[StudentAttendanceFrequency]


# ═══════════════════════════════════════════════════════════════════════════════
# Monthly attendance — GET /analytics/monthly
# ═══════════════════════════════════════════════════════════════════════════════

class MonthlyAttendancePoint(BaseModel):
    """One bar in the 'Monthly Attendance' chart."""
    month: str = Field(..., description="YYYY-MM", examples=["2026-06"])
    total_entries: int


class MonthlyAttendanceResponse(BaseModel):
    """Response for GET /analytics/monthly."""
    points: list[MonthlyAttendancePoint]


# ═══════════════════════════════════════════════════════════════════════════════
# Unknown detections — GET /analytics/unknown-detections
# ═══════════════════════════════════════════════════════════════════════════════

class UnknownDetectionPoint(BaseModel):
    """
    One unknown-detection event.

    Note: persisted unknown-face logging (with captured_image_path) is
    modeled by a future `unknown_detections` table per the architecture;
    this schema anticipates that table's shape so the analytics router can
    be implemented without revisiting this file.
    """
    id: int
    similarity_score: float
    detected_at: date_


class UnknownDetectionsResponse(BaseModel):
    """Response for GET /analytics/unknown-detections."""
    total: int
    items: list[UnknownDetectionPoint]
