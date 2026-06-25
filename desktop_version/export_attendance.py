"""
export_attendance.py
───────────────────────────────────────────────────────────────────────────────
Smart Attendance System — Export Utility

Exports attendance records from the SQLite database (via DBManager) to:
  • CSV   (.csv)
  • Excel (.xlsx) — with All Records / Daily Summary / Person Summary sheets

This module is a thin wrapper that:
  • Reuses DBManager for all data access (no duplicate SQL).
  • Reuses AttendanceManager.export_excel() for the Excel pipeline
    when available, falling back to a local implementation otherwise.
  • Provides a simple function-based API for the GUI / dashboard, plus
    a CLI for standalone use.

USAGE
─────
  python export_attendance.py --csv
  python export_attendance.py --excel
  python export_attendance.py --csv --excel --output-dir exports/
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.config     import Config
from utils.logger     import get_logger
from utils.db_manager import DBManager

log = get_logger(__name__)
Config.ensure_dirs()


# ═══════════════════════════════════════════════════════════════════════════════
# CSV EXPORT
# ═══════════════════════════════════════════════════════════════════════════════

def export_to_csv(output_path: Optional[Path] = None) -> Path:
    """
    Export all attendance records from the SQLite database to a single CSV.

    Returns
    -------
    Path to the written CSV file.

    Raises
    ------
    FileNotFoundError if the database file does not exist yet.
    """
    if not Config.DB_FILE.exists():
        raise FileNotFoundError(
            f"Attendance database not found at {Config.DB_FILE}. "
            "Run attendance_system.py first to create records."
        )

    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Config.EXPORTS_DIR / f"attendance_export_{ts}.csv"

    db = DBManager()
    rows = db.fetch_all()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "Date", "Time", "Similarity", "Status"])
        for r in rows:
            writer.writerow([r["name"], r["date"], r["time"],
                              f"{r['similarity']:.4f}", r["status"]])

    log.info(f"CSV export written: {output_path}  ({len(rows)} row(s))")
    return output_path


# ═══════════════════════════════════════════════════════════════════════════════
# EXCEL EXPORT
# ═══════════════════════════════════════════════════════════════════════════════

def export_to_excel(output_path: Optional[Path] = None) -> Path:
    """
    Export attendance to an Excel workbook with multiple sheets.

    Delegates to AttendanceManager.export_excel() (attendance_manager.py)
    so the sheet layout (All Records / Daily Summary / Person Summary)
    stays consistent with the existing CLI tool. Falls back to a local
    implementation if AttendanceManager cannot be imported.

    Returns
    -------
    Path to the written .xlsx file.

    Raises
    ------
    FileNotFoundError if the database file does not exist yet or has no rows.
    """
    if not Config.DB_FILE.exists():
        raise FileNotFoundError(
            f"Attendance database not found at {Config.DB_FILE}. "
            "Run attendance_system.py first to create records."
        )

    try:
        from attendance_manager import AttendanceManager
        mgr = AttendanceManager()
        result_path = mgr.export_excel(output_path=output_path)
        log.info(f"Excel export written via AttendanceManager: {result_path}")
        return result_path
    except ImportError:
        log.warning("AttendanceManager unavailable — using fallback Excel export.")

    # ── Fallback implementation ────────────────────────────────────────────
    import pandas as pd

    db = DBManager()
    rows = db.fetch_all()
    if not rows:
        raise FileNotFoundError("No attendance records found to export.")

    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Config.EXPORTS_DIR / f"attendance_export_{ts}.xlsx"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(
        [dict(r) for r in rows],
        columns=["name", "date", "time", "similarity", "status"],
    )

    with pd.ExcelWriter(str(output_path), engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="All Records", index=False)

        pivot = df.groupby(["date", "name"]).size().unstack(fill_value=0)
        pivot.to_excel(writer, sheet_name="Daily Summary")

        summary = df.groupby("name").agg(
            Days_Present   = ("date",       "nunique"),
            First_Seen     = ("date",       "min"),
            Last_Seen      = ("date",       "max"),
            Avg_Similarity = ("similarity", "mean"),
        ).reset_index()
        summary.to_excel(writer, sheet_name="Person Summary", index=False)

    log.info(f"Excel export written (fallback): {output_path}")
    return output_path


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export attendance records to CSV and/or Excel."
    )
    parser.add_argument("--csv",   action="store_true", help="Export to CSV")
    parser.add_argument("--excel", action="store_true", help="Export to Excel (.xlsx)")
    parser.add_argument("--output-dir", type=str, default=None,
                         help="Directory to save exports (default: Config.EXPORTS_DIR)")
    args = parser.parse_args()

    if not args.csv and not args.excel:
        args.csv = args.excel = True  # default: export both

    out_dir = Path(args.output_dir) if args.output_dir else Config.EXPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        if args.csv:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = export_to_csv(out_dir / f"attendance_export_{ts}.csv")
            print(f"  CSV exported:   {path}")

        if args.excel:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = export_to_excel(out_dir / f"attendance_export_{ts}.xlsx")
            print(f"  Excel exported: {path}")

    except FileNotFoundError as exc:
        print(f"  Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
