"""
attendance_viewer.py
───────────────────────────────────────────────────────────────────────────────
Smart Attendance System — Attendance Record Viewer (Tkinter)

Displays attendance records from the SQLite database (via DBManager) in a
sortable, searchable Treeview table.

Features
────────
  • Table view of all attendance records (Name, Date, Time, Similarity, Status)
  • Search by person name (substring match)
  • Search by date (YYYY-MM-DD, exact match)
  • Click any column header to sort ascending/descending
  • Refresh button to reload from the database
  • Standalone-runnable, or importable as a Frame for embedding in gui.py

USAGE
─────
  python attendance_viewer.py          # standalone window
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.config     import Config
from utils.logger     import get_logger
from utils.db_manager import DBManager

log = get_logger(__name__)
Config.ensure_dirs()


COLUMNS = ("name", "date", "time", "similarity", "status")
HEADERS = {
    "name":       "Name",
    "date":       "Date",
    "time":       "Time",
    "similarity": "Similarity",
    "status":     "Status",
}


# ═══════════════════════════════════════════════════════════════════════════════
# ATTENDANCE VIEWER FRAME
# ═══════════════════════════════════════════════════════════════════════════════

class AttendanceViewerFrame(ttk.Frame):
    """
    A self-contained Tkinter Frame that displays attendance records.

    Can be used standalone (inside a Toplevel/Tk root) or embedded inside
    another window (e.g. gui.py) by instantiating it with a parent widget.
    """

    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent)
        self._all_rows: List[Tuple] = []
        self._sort_state: dict = {col: False for col in COLUMNS}  # False = ascending

        self._build_widgets()
        self.refresh()

    # ── UI construction ─────────────────────────────────────────────────────
    def _build_widgets(self) -> None:
        # ── Search / filter bar ────────────────────────────────────────────
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=8, pady=(8, 4))

        ttk.Label(bar, text="Name:").pack(side="left")
        self.name_var = tk.StringVar()
        name_entry = ttk.Entry(bar, textvariable=self.name_var, width=20)
        name_entry.pack(side="left", padx=(4, 12))
        name_entry.bind("<Return>", lambda e: self._apply_filters())

        ttk.Label(bar, text="Date (YYYY-MM-DD):").pack(side="left")
        self.date_var = tk.StringVar()
        date_entry = ttk.Entry(bar, textvariable=self.date_var, width=12)
        date_entry.pack(side="left", padx=(4, 12))
        date_entry.bind("<Return>", lambda e: self._apply_filters())

        ttk.Button(bar, text="Search", command=self._apply_filters).pack(side="left", padx=4)
        ttk.Button(bar, text="Clear",  command=self._clear_filters).pack(side="left", padx=4)
        ttk.Button(bar, text="Refresh", command=self.refresh).pack(side="right", padx=4)

        # ── Table ───────────────────────────────────────────────────────────
        table_frame = ttk.Frame(self)
        table_frame.pack(fill="both", expand=True, padx=8, pady=4)

        self.tree = ttk.Treeview(table_frame, columns=COLUMNS, show="headings")
        for col in COLUMNS:
            self.tree.heading(col, text=HEADERS[col],
                               command=lambda c=col: self._sort_by(c))
            anchor = "w" if col in ("name", "status") else "center"
            width  = 180 if col == "name" else 110
            self.tree.column(col, width=width, anchor=anchor)

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        # ── Status label ────────────────────────────────────────────────────
        self.status_var = tk.StringVar(value="Loading…")
        ttk.Label(self, textvariable=self.status_var, anchor="w").pack(
            fill="x", padx=8, pady=(0, 8)
        )

    # ── Data loading ─────────────────────────────────────────────────────────
    def refresh(self) -> None:
        """Reload all attendance records from the database."""
        try:
            if not Config.DB_FILE.exists():
                self._all_rows = []
                self.status_var.set(
                    f"No database found at {Config.DB_FILE}. "
                    "Run attendance_system.py to create attendance records."
                )
                self._populate([])
                return

            db   = DBManager()
            rows = db.fetch_all()
            self._all_rows = [
                (r["name"], r["date"], r["time"], float(r["similarity"]), r["status"])
                for r in rows
            ]
            self._apply_filters()
        except Exception as exc:
            log.error(f"AttendanceViewer refresh failed: {exc}")
            self.status_var.set(f"Error loading attendance data: {exc}")
            self._populate([])

    # ── Filtering ────────────────────────────────────────────────────────────
    def _apply_filters(self) -> None:
        name_query = self.name_var.get().strip().lower()
        date_query = self.date_var.get().strip()

        rows = self._all_rows
        if name_query:
            rows = [r for r in rows if name_query in r[0].lower()]
        if date_query:
            rows = [r for r in rows if r[1] == date_query]

        self._populate(rows)
        self.status_var.set(f"Showing {len(rows)} of {len(self._all_rows)} record(s).")

    def _clear_filters(self) -> None:
        self.name_var.set("")
        self.date_var.set("")
        self._apply_filters()

    # ── Sorting ──────────────────────────────────────────────────────────────
    def _sort_by(self, col: str) -> None:
        idx = COLUMNS.index(col)
        descending = self._sort_state[col]

        # Read current rows back from the tree (so sort applies to filtered view)
        items = [self.tree.item(i)["values"] for i in self.tree.get_children()]

        def key(row):
            val = row[idx]
            if col == "similarity":
                try:
                    return float(val)
                except (TypeError, ValueError):
                    return 0.0
            return str(val)

        items.sort(key=key, reverse=descending)
        self._sort_state[col] = not descending

        for i in self.tree.get_children():
            self.tree.delete(i)
        for row in items:
            self.tree.insert("", "end", values=row)

    # ── Table population ────────────────────────────────────────────────────
    def _populate(self, rows: List[Tuple]) -> None:
        for i in self.tree.get_children():
            self.tree.delete(i)
        for row in rows:
            display = (row[0], row[1], row[2], f"{row[3]:.4f}", row[4])
            self.tree.insert("", "end", values=display)

        if not rows and not self._all_rows:
            return
        self.status_var.set(f"Showing {len(rows)} of {len(self._all_rows)} record(s).")


# ═══════════════════════════════════════════════════════════════════════════════
# STANDALONE WINDOW
# ═══════════════════════════════════════════════════════════════════════════════

def launch_viewer(parent: tk.Widget = None) -> tk.Toplevel | tk.Tk:
    """
    Launch the attendance viewer in its own window.

    If `parent` is provided, opens as a Toplevel attached to it (used by
    gui.py). Otherwise creates a standalone root Tk window.
    """
    if parent is not None:
        win = tk.Toplevel(parent)
    else:
        win = tk.Tk()

    win.title("Smart Attendance System — Attendance Viewer")
    win.geometry("760x480")

    try:
        frame = AttendanceViewerFrame(win)
        frame.pack(fill="both", expand=True)
    except Exception as exc:
        messagebox.showerror("Attendance Viewer Error", str(exc), parent=win)

    return win


if __name__ == "__main__":
    root = launch_viewer()
    root.mainloop()
