"""
app/api/v1/export.py
───────────────────────────────────────────────────────────────────────────────
Attendance data export endpoints: file download (CSV/JSON) and streaming CSV.
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_async_session
from app.models.attendance import AttendanceStatus
from app.models.user import User
from app.services.export_service import ExportFormat, ExportService

router = APIRouter(prefix="/export", tags=["Export"])


def _get_service(session: AsyncSession = Depends(get_async_session)) -> ExportService:
    return ExportService(session)


@router.get("/download")
async def download_export(
    format: ExportFormat = Query(default="csv", description="Export format: csv or json"),
    student_id: int | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    status_filter: AttendanceStatus | None = Query(default=None, alias="status"),
    svc: ExportService = Depends(_get_service),
    _: User = Depends(get_current_user),
) -> FileResponse:
    """
    Export attendance records to a file and trigger a browser download.

    Writes the file to `settings.EXPORTS_DIR` and returns it as a
    `FileResponse`. Accepts optional filters matching the attendance list
    endpoint.
    """
    output_path = await svc.export(
        format=format,
        student_id=student_id,
        start_date=start_date,
        end_date=end_date,
        status=status_filter,
    )

    media_type = "text/csv" if format == "csv" else "application/json"
    return FileResponse(
        path=str(output_path),
        media_type=media_type,
        filename=output_path.name,
    )


@router.get("/stream/csv")
async def stream_csv(
    student_id: int | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    status_filter: AttendanceStatus | None = Query(default=None, alias="status"),
    svc: ExportService = Depends(_get_service),
    _: User = Depends(get_current_user),
) -> StreamingResponse:
    """
    Stream attendance data as CSV without writing to disk.

    Useful for small datasets or when the client wants to pipe the response
    directly. For large exports, prefer `/export/download`.
    """
    csv_content = await svc.export_to_csv_string(
        student_id=student_id,
        start_date=start_date,
        end_date=end_date,
        status=status_filter,
    )

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=attendance_stream.csv"},
    )
