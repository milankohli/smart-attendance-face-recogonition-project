"""
attendance_manager.py
───────────────────────────────────────────────────────────────────────────────
Smart Attendance System — Attendance Manager

Responsibilities
────────────────
• Write attendance records to CSV (daily files) + SQLite database.
• Query attendance: by date, by person, by date range.
• Generate tabular and Excel reports.
• Command-line interface for manual queries.

USAGE
─────
  # View today's attendance
  python attendance_manager.py --today

  # View attendance for a specific date
  python attendance_manager.py --date 2024-06-10

  # View attendance for a date range
  python attendance_manager.py --range 2024-06-01 2024-06-30

  # View attendance for a specific person
  python attendance_manager.py --person "Alice Smith"

  # Export to Excel (saved to exports/)
  python attendance_manager.py --export-excel

  # List all registered people
  python attendance_manager.py --list-people

  # Run threshold optimizer
  python attendance_manager.py --optimize-threshold

CHANGELOG
─────────
v2 — Replaced embedded _get_connection() / _CREATE_TABLE_SQL with DBManager.
     Added --range CLI flag.  Export destination moved to Config.EXPORTS_DIR.
     Added --optimize-threshold CLI flag.
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from colorama import init as colorama_init, Fore, Style
from tabulate import tabulate

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.config    import Config
from utils.logger    import get_logger
from utils.db_manager import DBManager

colorama_init(autoreset=True)
log = get_logger(__name__)
Config.ensure_dirs()


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — ATTENDANCE MANAGER CLASS
# ═══════════════════════════════════════════════════════════════════════════════

class AttendanceManager:
    """
    Full-featured attendance tracker.

    Writes to:
      • Daily CSV:  attendance/attendance_YYYY-MM-DD.csv
      • SQLite DB:  database/attendance.db  (via DBManager)

    Having both formats allows:
      CSV    → easy audit trail, human-readable backup, Excel import
      SQLite → fast queries, reports, analytics
    """

    def __init__(self) -> None:
        self._db:        DBManager       = DBManager()
        self._cooldown:  Dict[str, datetime] = {}   # {name: last_marked_time}
        self._today:     str = date.today().isoformat()
        self._csv_path:  Path = (
            Config.ATTENDANCE_DIR /
            f"{Config.ATTENDANCE_CSV_PREFIX}_{self._today}.csv"
        )
        self._ensure_csv_header()
        log.info(f"AttendanceManager ready  |  CSV: {self._csv_path}")

    # ── CSV management ────────────────────────────────────────────────────────
    def _ensure_csv_header(self) -> None:
        """Create today's CSV with a header row if it doesn't exist."""
        if not self._csv_path.exists():
            with open(self._csv_path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(
                    ["Name", "Date", "Time", "Similarity", "Confidence", "Status"]
                )

    # ── Public: mark attendance ───────────────────────────────────────────────
    def mark(
        self,
        name:       str,
        similarity: float,
        status:     str = "Present",
    ) -> bool:
        """
        Record attendance for `name` with cooldown enforcement.

        Writes to BOTH the daily CSV and SQLite database via DBManager.

        Returns True if newly marked, False if within cooldown window.
        """
        now = datetime.now()

        # ── Cooldown check ────────────────────────────────────────────────
        if name in self._cooldown:
            elapsed = (now - self._cooldown[name]).total_seconds()
            if elapsed < Config.ATTENDANCE_COOLDOWN_SECONDS:
                return False

        self._cooldown[name] = now
        today_str = now.strftime("%Y-%m-%d")
        time_str  = now.strftime("%H:%M:%S")

        # ── Refresh CSV path in case date rolled over at midnight ─────────
        csv_path = (
            Config.ATTENDANCE_DIR /
            f"{Config.ATTENDANCE_CSV_PREFIX}_{today_str}.csv"
        )
        if csv_path != self._csv_path:
            self._csv_path = csv_path
            self._ensure_csv_header()

        with open(self._csv_path, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(
                [name, today_str, time_str, f"{similarity:.4f}", "medium", status]
            )

        # ── Write to SQLite via DBManager ─────────────────────────────────
        self._db.insert_attendance(name, today_str, time_str, similarity, status)

        log.info(f"Attendance marked: {name} @ {time_str}  sim={similarity:.4f}")
        return True

    # ── Query methods (delegate to DBManager then wrap in DataFrame) ──────────
    def _rows_to_df(self, rows) -> pd.DataFrame:
        if not rows:
            return pd.DataFrame(columns=["name", "date", "time", "similarity", "status"])
        return pd.DataFrame(
            [dict(r) for r in rows],
            columns=["name", "date", "time", "similarity", "status"],
        )

    def get_today(self) -> pd.DataFrame:
        """Return today's attendance as a DataFrame."""
        return self.get_by_date(date.today().isoformat())

    def get_by_date(self, date_str: str) -> pd.DataFrame:
        """Return attendance for a specific date (YYYY-MM-DD)."""
        return self._rows_to_df(self._db.fetch_by_date(date_str))

    def get_by_person(self, name: str) -> pd.DataFrame:
        """Return all attendance records for a specific person."""
        return self._rows_to_df(self._db.fetch_by_name(name))

    def get_date_range(self, start: str, end: str) -> pd.DataFrame:
        """Return attendance between start and end date (inclusive)."""
        return self._rows_to_df(self._db.fetch_range(start, end))

    def get_summary(self) -> pd.DataFrame:
        """Attendance count per person across all dates."""
        rows = self._db.fetch_summary()
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(
            [dict(r) for r in rows],
            columns=["name", "days_present", "total_entries",
                     "first_seen", "last_seen", "avg_similarity"],
        )

    # ── Export ────────────────────────────────────────────────────────────────
    def export_excel(self, output_path: Optional[Path] = None) -> Path:
        """
        Export the full attendance database to an Excel workbook.

        Saved to Config.EXPORTS_DIR by default.

        Sheets:
          • All Records    – raw data
          • Daily Summary  – pivot: dates × names
          • Person Summary – total days per person
        """
        if output_path is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = Config.EXPORTS_DIR / f"attendance_report_{ts}.xlsx"

        all_rows = self._db.fetch_all()
        if not all_rows:
            log.warning("No attendance data to export.")
            return output_path

        all_df = pd.DataFrame(
            [dict(r) for r in all_rows],
            columns=["name", "date", "time", "similarity", "status"],
        )

        with pd.ExcelWriter(str(output_path), engine="openpyxl") as writer:
            all_df.to_excel(writer, sheet_name="All Records", index=False)

            # Pivot: dates as rows, names as columns, count as values
            pivot = (
                all_df.groupby(["date", "name"])
                .size()
                .unstack(fill_value=0)
            )
            pivot.to_excel(writer, sheet_name="Daily Summary")

            summary = all_df.groupby("name").agg(
                Days_Present   = ("date",       "nunique"),
                First_Seen     = ("date",       "min"),
                Last_Seen      = ("date",       "max"),
                Avg_Similarity = ("similarity", "mean"),
            ).reset_index()
            summary.to_excel(writer, sheet_name="Person Summary", index=False)

        log.info(f"Excel report exported: {output_path}")
        return output_path


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — CLI
# ═══════════════════════════════════════════════════════════════════════════════

def _df_to_table(df: pd.DataFrame, title: str) -> None:
    print(Fore.CYAN + Style.BRIGHT + f"\n  ══ {title} ══" + Style.RESET_ALL)
    if df.empty:
        print(Fore.YELLOW + "  No records found." + Style.RESET_ALL)
    else:
        print(tabulate(df, headers="keys", tablefmt="rounded_outline",
                       showindex=False, floatfmt=".4f"))
        print(f"  Rows: {len(df)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Attendance Manager CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python attendance_manager.py --today
  python attendance_manager.py --date 2024-06-10
  python attendance_manager.py --range 2024-06-01 2024-06-30
  python attendance_manager.py --person "Alice Smith"
  python attendance_manager.py --summary
  python attendance_manager.py --export-excel
  python attendance_manager.py --list-people
  python attendance_manager.py --optimize-threshold
        """
    )
    parser.add_argument("--today",         action="store_true",
                        help="Show today's attendance")
    parser.add_argument("--date",          type=str,
                        help="Show attendance for date (YYYY-MM-DD)")
    parser.add_argument("--range",         type=str, nargs=2,
                        metavar=("START", "END"),
                        help="Show attendance for date range: START END (YYYY-MM-DD)")
    parser.add_argument("--person",        type=str,
                        help="Show attendance for a specific person")
    parser.add_argument("--summary",       action="store_true",
                        help="Show overall attendance summary")
    parser.add_argument("--export-excel",  action="store_true",
                        help="Export full database to Excel (saved to exports/)")
    parser.add_argument("--list-people",   action="store_true",
                        help="List all registered people in embeddings store")
    parser.add_argument("--optimize-threshold", action="store_true",
                        help="Run threshold optimizer and show suggested threshold")
    args = parser.parse_args()

    mgr = AttendanceManager()

    if args.today:
        _df_to_table(mgr.get_today(), f"Attendance — {date.today().isoformat()}")

    elif args.date:
        _df_to_table(mgr.get_by_date(args.date), f"Attendance — {args.date}")

    elif args.range:
        start, end = args.range
        _df_to_table(
            mgr.get_date_range(start, end),
            f"Attendance — {start} to {end}",
        )

    elif args.person:
        _df_to_table(mgr.get_by_person(args.person), f"Attendance — {args.person}")

    elif args.summary:
        _df_to_table(mgr.get_summary(), "Overall Attendance Summary")

    elif args.export_excel:
        out = mgr.export_excel()
        print(Fore.GREEN + f"\n  ✓ Excel report saved: {out}" + Style.RESET_ALL)

    elif args.list_people:
        from utils.embedding_store import EmbeddingStore
        store = EmbeddingStore()
        people = store.list_people()
        print(Fore.CYAN + f"\n  Registered people ({len(people)}):" + Style.RESET_ALL)
        for p in people:
            meta = store.metadata.get(p, {})
            print(f"    • {p}  ({meta.get('count', '?')} embeddings, "
                  f"registered: {meta.get('registered_at', '?')})")

    elif args.optimize_threshold:
        from utils.threshold_optimizer import ThresholdOptimizer, print_analysis
        opt    = ThresholdOptimizer()
        try:
            result = opt.analyze()
            print_analysis(result)
        except ValueError as exc:
            print(Fore.RED + f"\n  Error: {exc}" + Style.RESET_ALL)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
