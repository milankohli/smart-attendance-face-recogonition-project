"""
dashboard.py
───────────────────────────────────────────────────────────────────────────────
Smart Attendance System — Dashboard (Tkinter + Matplotlib)

Displays summary statistics as "cards" plus charts:

Stats cards
───────────
  • Total registered people     (EmbeddingStore.list_people)
  • Today's attendance count    (DBManager.fetch_by_date)
  • Total attendance records    (DBManager.fetch_all)
  • Unknown detections           (logs/attendance_system.log — count of
                                   "✗ UNKNOWN" / "UNKNOWN" recognitions)

Charts (matplotlib, embedded via FigureCanvasTkAgg)
────────────────────────────────────────────────────
  • Daily attendance (last 14 days) — bar chart
  • Attendance frequency by person  — bar chart
  • Monthly attendance              — bar chart

This module reuses EmbeddingStore and DBManager — no new storage formats,
no duplicated query logic.

USAGE
─────
  python dashboard.py        # standalone window
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import re
import sys
import tkinter as tk
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.config          import Config
from utils.logger           import get_logger
from utils.db_manager       import DBManager
from utils.embedding_store  import EmbeddingStore

log = get_logger(__name__)
Config.ensure_dirs()

try:
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════════════════════
# DATA HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def get_registered_people_count() -> int:
    """Total number of registered people in the embedding store."""
    try:
        store = EmbeddingStore()
        return len(store.list_people())
    except Exception as exc:
        log.error(f"Could not read embedding store: {exc}")
        return 0


def get_today_attendance_count() -> int:
    """Number of attendance records for today's date."""
    if not Config.DB_FILE.exists():
        return 0
    try:
        db   = DBManager()
        rows = db.fetch_by_date(date.today().isoformat())
        return len(rows)
    except Exception as exc:
        log.error(f"Could not read today's attendance: {exc}")
        return 0


def get_total_attendance_count() -> int:
    """Total number of attendance records ever recorded."""
    if not Config.DB_FILE.exists():
        return 0
    try:
        db = DBManager()
        return len(db.fetch_all())
    except Exception as exc:
        log.error(f"Could not read attendance totals: {exc}")
        return 0


def get_unknown_detections_count() -> int:
    """
    Count "Unknown" face detections by scanning the rotating log file.

    The recognition engine logs lines like:
        "Top match: 'X'  score=0.41  band=low  ✗ UNKNOWN"

    Returns 0 if the log file does not exist yet.
    """
    log_file = Config.LOGS_DIR / "attendance_system.log"
    if not log_file.exists():
        return 0

    count = 0
    try:
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "UNKNOWN" in line:
                    count += 1
    except OSError as exc:
        log.error(f"Could not read log file: {exc}")
    return count


def get_daily_attendance(last_n_days: int = 14) -> Dict[str, int]:
    """
    Unique-person attendance counts per day for the last `last_n_days`.

    Returns
    -------
    Ordered dict {date_str: count}, oldest first. Empty if no DB.
    """
    if not Config.DB_FILE.exists():
        return {}
    try:
        db   = DBManager()
        rows = db.fetch_daily_counts()  # [{date, unique_persons, total_entries}]
    except Exception as exc:
        log.error(f"Could not read daily counts: {exc}")
        return {}

    data = {r["date"]: r["unique_persons"] for r in rows}
    # Keep only the most recent N dates, sorted ascending
    sorted_dates = sorted(data.keys())[-last_n_days:]
    return {d: data[d] for d in sorted_dates}


def get_attendance_by_person() -> Dict[str, int]:
    """Total attendance entry count per person (descending)."""
    if not Config.DB_FILE.exists():
        return {}
    try:
        db   = DBManager()
        rows = db.fetch_summary()  # [{name, days_present, total_entries, ...}]
    except Exception as exc:
        log.error(f"Could not read attendance summary: {exc}")
        return {}

    data = {r["name"]: r["total_entries"] for r in rows}
    return dict(sorted(data.items(), key=lambda kv: kv[1], reverse=True))


def get_monthly_attendance() -> Dict[str, int]:
    """Total attendance entry count grouped by YYYY-MM (chronological)."""
    if not Config.DB_FILE.exists():
        return {}
    try:
        db   = DBManager()
        rows = db.fetch_all()  # [{name, date, time, similarity, status}]
    except Exception as exc:
        log.error(f"Could not read attendance records: {exc}")
        return {}

    counter: Counter = Counter()
    for r in rows:
        try:
            month_key = r["date"][:7]  # 'YYYY-MM'
        except (TypeError, IndexError):
            continue
        counter[month_key] += 1

    return dict(sorted(counter.items()))


# ═══════════════════════════════════════════════════════════════════════════════
# DASHBOARD FRAME
# ═══════════════════════════════════════════════════════════════════════════════

class DashboardFrame(ttk.Frame):
    """
    Self-contained Tkinter Frame showing stats cards + charts.

    Can be embedded in gui.py or run standalone via launch_dashboard().
    """

    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent)
        self._canvases: List = []
        self._build_widgets()
        self.refresh()

    # ── UI construction ─────────────────────────────────────────────────────
    def _build_widgets(self) -> None:
        # ── Top bar ─────────────────────────────────────────────────────────
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=8)
        ttk.Label(top, text="Dashboard", font=("Segoe UI", 14, "bold")).pack(side="left")
        ttk.Button(top, text="Refresh", command=self.refresh).pack(side="right")

        # ── Stat cards row ──────────────────────────────────────────────────
        self.cards_frame = ttk.Frame(self)
        self.cards_frame.pack(fill="x", padx=8, pady=(0, 8))

        self.card_vars = {
            "people":  tk.StringVar(value="—"),
            "today":   tk.StringVar(value="—"),
            "total":   tk.StringVar(value="—"),
            "unknown": tk.StringVar(value="—"),
        }
        card_labels = {
            "people":  "Registered People",
            "today":   "Today's Attendance",
            "total":   "Total Records",
            "unknown": "Unknown Detections",
        }

        for i, key in enumerate(["people", "today", "total", "unknown"]):
            card = ttk.LabelFrame(self.cards_frame, text=card_labels[key])
            card.grid(row=0, column=i, padx=6, sticky="nsew")
            self.cards_frame.columnconfigure(i, weight=1)
            ttk.Label(
                card, textvariable=self.card_vars[key],
                font=("Segoe UI", 22, "bold"), anchor="center"
            ).pack(padx=12, pady=12, fill="x")

        # ── Charts area ──────────────────────────────────────────────────────
        self.charts_frame = ttk.Frame(self)
        self.charts_frame.pack(fill="both", expand=True, padx=8, pady=8)

        if not MATPLOTLIB_AVAILABLE:
            ttk.Label(
                self.charts_frame,
                text="matplotlib is not installed — charts unavailable.\n"
                     "Install with: pip install matplotlib",
                foreground="red",
            ).pack(pady=20)

    # ── Refresh ──────────────────────────────────────────────────────────────
    def refresh(self) -> None:
        """Reload stats and redraw charts."""
        try:
            self.card_vars["people"].set(str(get_registered_people_count()))
            self.card_vars["today"].set(str(get_today_attendance_count()))
            self.card_vars["total"].set(str(get_total_attendance_count()))
            self.card_vars["unknown"].set(str(get_unknown_detections_count()))
        except Exception as exc:
            log.error(f"Dashboard stats refresh failed: {exc}")
            messagebox.showerror("Dashboard Error", f"Could not load statistics:\n{exc}")

        if MATPLOTLIB_AVAILABLE:
            self._draw_charts()

    # ── Chart rendering ─────────────────────────────────────────────────────
    def _draw_charts(self) -> None:
        # Clear previous canvases/figures to avoid memory leaks on refresh
        for canvas in self._canvases:
            canvas.get_tk_widget().destroy()
        self._canvases = []
        for child in self.charts_frame.winfo_children():
            child.destroy()

        daily   = get_daily_attendance()
        by_person = get_attendance_by_person()
        monthly = get_monthly_attendance()

        fig, axes = plt.subplots(1, 3, figsize=(12, 3.5))
        fig.subplots_adjust(wspace=0.4, bottom=0.3)

        # ── Daily attendance ────────────────────────────────────────────────
        ax = axes[0]
        if daily:
            ax.bar(list(daily.keys()), list(daily.values()), color="#4C72B0")
            ax.set_title("Daily Attendance (last 14 days)")
            ax.tick_params(axis="x", rotation=70, labelsize=7)
        else:
            ax.set_title("Daily Attendance")
            ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
        ax.set_ylabel("Unique people")

        # ── Attendance frequency by person ─────────────────────────────────
        ax = axes[1]
        if by_person:
            names = list(by_person.keys())[:10]
            vals  = [by_person[n] for n in names]
            ax.bar(names, vals, color="#55A868")
            ax.set_title("Attendance by Person (top 10)")
            ax.tick_params(axis="x", rotation=70, labelsize=7)
        else:
            ax.set_title("Attendance by Person")
            ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
        ax.set_ylabel("Total entries")

        # ── Monthly attendance ───────────────────────────────────────────────
        ax = axes[2]
        if monthly:
            ax.bar(list(monthly.keys()), list(monthly.values()), color="#C44E52")
            ax.set_title("Monthly Attendance")
            ax.tick_params(axis="x", rotation=70, labelsize=7)
        else:
            ax.set_title("Monthly Attendance")
            ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
        ax.set_ylabel("Total entries")

        canvas = FigureCanvasTkAgg(fig, master=self.charts_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        self._canvases.append(canvas)


# ═══════════════════════════════════════════════════════════════════════════════
# STANDALONE WINDOW
# ═══════════════════════════════════════════════════════════════════════════════

def launch_dashboard(parent: tk.Widget = None):
    """
    Launch the dashboard in its own window.

    If `parent` is provided, opens as a Toplevel (used by gui.py).
    Otherwise creates a standalone root Tk window.
    """
    if parent is not None:
        win = tk.Toplevel(parent)
    else:
        win = tk.Tk()

    win.title("Smart Attendance System — Dashboard")
    win.geometry("980x600")

    frame = DashboardFrame(win)
    frame.pack(fill="both", expand=True)

    return win


if __name__ == "__main__":
    root = launch_dashboard()
    root.mainloop()
