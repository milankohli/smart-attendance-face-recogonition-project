"""
app/services/__init__.py
───────────────────────────────────────────────────────────────────────────────
Convenience re-exports for the service layer.
───────────────────────────────────────────────────────────────────────────────
"""

from app.services.student_service import StudentService
from app.services.attendance_service import AttendanceService
from app.services.export_service import ExportService

__all__ = [
    "StudentService",
    "AttendanceService",
    "ExportService",
]
