"""
app/services/export_service.py
───────────────────────────────────────────────────────────────────────────────
Business logic for attendance data export.

Mirrors the desktop app's CSV export functionality (export_to_csv in
the dashboard) and extends it with:
  • Async database queries via AttendanceRepository
  • CSV export (original desktop feature)
  • JSON export (new, for API consumers)
  • Per-student export filtering

Writes export files to settings.EXPORTS_DIR and returns the file path so
the router can stream it as a FileResponse.
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import csv
import io
import json
import os
from datetime import date as date_, datetime
from pathlib import Path
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.attendance import AttendanceStatus
from app.repositories.attendance_repo import AttendanceRepository
from app.repositories.student_repo import StudentRepository

log = get_logger(__name__)

ExportFormat = Literal["csv", "json"]


class ExportService:
    """
    Service for exporting attendance data to file.

    Writes to `settings.EXPORTS_DIR`. In production this directory should
    be backed by object storage (S3 / GCS) and the returned path replaced
    with a pre-signed URL — that migration is out of scope for this phase.
    """

    # CSV column order — matches the desktop app's export format
    CSV_HEADERS = [
        "record_id",
        "student_id",
        "student_name",
        "student_code",
        "department",
        "date",
        "time",
        "similarity_score",
        "confidence_band",
        "status",
        "device_id",
        "created_at",
    ]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._attendance_repo = AttendanceRepository(session)
        self._student_repo = StudentRepository(session)
        self._exports_dir = Path(settings.EXPORTS_DIR)
        self._exports_dir.mkdir(parents=True, exist_ok=True)

    async def export(
        self,
        *,
        format: ExportFormat = "csv",
        student_id: int | None = None,
        start_date: date_ | None = None,
        end_date: date_ | None = None,
        status: AttendanceStatus | None = None,
        filename_prefix: str = "attendance_export",
    ) -> Path:
        """
        Export attendance records matching the given filters to a file.

        Args:
            format:          "csv" or "json".
            student_id:      Filter to a single student.
            start_date:      Range start (inclusive).
            end_date:        Range end (inclusive).
            status:          Filter by attendance status.
            filename_prefix: Prefix for the generated filename.

        Returns:
            Absolute path to the written export file.
        """
        # Fetch all matching records (no pagination — export entire result set)
        records = await self._attendance_repo.list(
            student_id=student_id,
            start_date=start_date,
            end_date=end_date,
            status=status,
            load_student=True,
            skip=0,
            limit=100_000,  # sane upper bound; replace with streaming for huge datasets
        )

        # Build rows as plain dicts (format-agnostic)
        rows = [
            {
                "record_id": r.id,
                "student_id": r.student_id,
                "student_name": r.student.name if r.student else None,
                "student_code": r.student.student_code if r.student else None,
                "department": r.student.department if r.student else None,
                "date": str(r.date),
                "time": str(r.time),
                "similarity_score": round(r.similarity_score, 6),
                "confidence_band": r.confidence_band.value,
                "status": r.status.value,
                "device_id": r.device_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ]

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"{filename_prefix}_{timestamp}.{format}"
        output_path = self._exports_dir / filename

        if format == "csv":
            await self._write_csv(rows, output_path)
        elif format == "json":
            await self._write_json(rows, output_path)
        else:
            raise ValueError(f"Unsupported export format: {format!r}")

        log.info(
            "Export complete",
            extra={
                "ctx_format": format,
                "ctx_rows": len(rows),
                "ctx_path": str(output_path),
            },
        )
        return output_path

    # ── Format writers ────────────────────────────────────────────────────

    async def _write_csv(self, rows: list[dict], path: Path) -> None:
        """Write rows to a CSV file at `path`."""
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.CSV_HEADERS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        log.debug("CSV written", extra={"ctx_path": str(path), "ctx_rows": len(rows)})

    async def _write_json(self, rows: list[dict], path: Path) -> None:
        """Write rows to a JSON file at `path`."""
        export_payload = {
            "exported_at": datetime.utcnow().isoformat() + "Z",
            "total_records": len(rows),
            "records": rows,
        }
        with path.open("w", encoding="utf-8") as f:
            json.dump(export_payload, f, indent=2, default=str)
        log.debug("JSON written", extra={"ctx_path": str(path), "ctx_rows": len(rows)})

    # ── In-memory convenience ─────────────────────────────────────────────

    async def export_to_csv_string(
        self,
        *,
        student_id: int | None = None,
        start_date: date_ | None = None,
        end_date: date_ | None = None,
        status: AttendanceStatus | None = None,
    ) -> str:
        """
        Return CSV content as a string (for StreamingResponse without
        writing to disk).

        Useful in tests and for small-scale API streaming.
        """
        records = await self._attendance_repo.list(
            student_id=student_id,
            start_date=start_date,
            end_date=end_date,
            status=status,
            load_student=True,
            skip=0,
            limit=100_000,
        )

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=self.CSV_HEADERS, extrasaction="ignore")
        writer.writeheader()
        for r in records:
            writer.writerow(
                {
                    "record_id": r.id,
                    "student_id": r.student_id,
                    "student_name": r.student.name if r.student else None,
                    "student_code": r.student.student_code if r.student else None,
                    "department": r.student.department if r.student else None,
                    "date": str(r.date),
                    "time": str(r.time),
                    "similarity_score": round(r.similarity_score, 6),
                    "confidence_band": r.confidence_band.value,
                    "status": r.status.value,
                    "device_id": r.device_id,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
            )
        return output.getvalue()
