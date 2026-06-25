# Smart Attendance System — GUI / Dashboard Addendum

This addendum documents the **new files** added on top of the existing
FaceNet + Haar Cascade + Cosine Similarity attendance pipeline. No existing
files (`attendance_system.py`, `register_face.py`, `attendance_manager.py`,
`config.py`, `db_manager.py`, `embedding_*`, `face_detector.py`, `logger.py`,
`similarity.py`, `threshold_optimizer.py`) were modified or rewritten.

---

## New Files

```
Smart_Attendance_System/
│
├── gui.py                  ← NEW: Tkinter control-panel GUI
├── attendance_viewer.py    ← NEW: Searchable/sortable attendance table
├── dashboard.py            ← NEW: Stats cards + matplotlib charts
├── export_attendance.py    ← NEW: CSV / Excel export utility
└── ... (all existing files unchanged)
```

---

## 1. `gui.py` — Main Control Panel

A single Tkinter window with the following buttons:

| Button               | Behaviour |
|----------------------|-----------|
| **Register Person**  | Launches `register_face.py` as a subprocess (its own webcam window + console prompts). |
| **Start Attendance** | Starts the live recognition loop in a background thread, using `EmbeddingStore`, `HaarFaceDetector`, `FaceNetEmbedder`, `FaceRecogniser`, and `DBManager` — the same components as `attendance_system.py`. |
| **Stop Attendance**  | Signals the background thread to stop and release the camera. |
| **View Attendance**  | Opens `attendance_viewer.py` in a new window. |
| **Dashboard**        | Opens `dashboard.py` in a new window. |
| **Export Attendance**| Opens a small dialog to export to CSV or Excel via `export_attendance.py`. |
| **Exit**             | Stops any running attendance loop, then closes the app. |

**Run:**
```bash
python gui.py
```

### Why not import `attendance_system.run_attendance_system()` directly?

That function runs an infinite `while True` loop with its own OpenCV window
and has no way to be interrupted externally. To keep `attendance_system.py`
**unmodified**, `gui.py` includes a small `AttendanceWorker` class that
re-uses the exact same backend components (`EmbeddingStore`,
`HaarFaceDetector`, `FaceNetEmbedder`, `FaceRecogniser`, `DBManager`) in a
background thread with a `stop()` flag, writing to the same
`attendance/attendance_YYYY-MM-DD.csv` and `database/attendance.db` files in
the same format. `register_face.py` (interactive, blocking) is instead run
as a subprocess.

---

## 2. `attendance_viewer.py` — Attendance Record Viewer

A Tkinter `Treeview` table reading from `database/attendance.db` via the
existing `DBManager`.

Features:
- View all attendance records (Name, Date, Time, Similarity, Status)
- Search by **person name** (substring match)
- Search by **date** (`YYYY-MM-DD`, exact match)
- Click any column header to **sort** ascending/descending
- **Refresh** button to reload from the database

**Run standalone:**
```bash
python attendance_viewer.py
```
Or open it from `gui.py` via **View Attendance**.

---

## 3. `dashboard.py` — Dashboard & Charts

Shows summary statistic cards:
- Total registered people (`EmbeddingStore.list_people()`)
- Today's attendance count (`DBManager.fetch_by_date(today)`)
- Total attendance records (`DBManager.fetch_all()`)
- Unknown detections (counted from `logs/attendance_system.log`, lines
  containing `"UNKNOWN"`)

And three matplotlib charts (embedded via `FigureCanvasTkAgg`):
- **Daily attendance** (last 14 days, unique people per day)
- **Attendance frequency by person** (top 10, total entries)
- **Monthly attendance** (entries grouped by `YYYY-MM`)

**Run standalone:**
```bash
python dashboard.py
```
Or open it from `gui.py` via **Dashboard**.

> If `matplotlib` is not installed, the stat cards still work; the chart
> area shows an install hint instead of crashing.

---

## 4. `export_attendance.py` — Export Utility

Exports `database/attendance.db` (via `DBManager`) to:
- **CSV** — `Name, Date, Time, Similarity, Status`
- **Excel (.xlsx)** — delegates to `AttendanceManager.export_excel()` from
  `attendance_manager.py` (sheets: *All Records*, *Daily Summary*,
  *Person Summary*), with a built-in fallback if that import fails.

Both export types are written to `Config.EXPORTS_DIR` (`exports/`).

**CLI usage:**
```bash
python export_attendance.py --csv
python export_attendance.py --excel
python export_attendance.py --csv --excel --output-dir custom_exports/
```

Used by `gui.py`'s **Export Attendance** dialog.

---

## 5. New Dependency

Add to `requirements.txt`:

```
matplotlib>=3.7.0   # Dashboard charts (dashboard.py)
```

`tkinter` ships with standard Python on most platforms and needs no
separate pip install (on some Linux distros: `sudo apt install python3-tk`).

---

## 6. Error Handling Added

All new modules handle the following gracefully (status messages in the GUI
instead of crashes):

| Condition                          | Handling |
|-------------------------------------|----------|
| Camera unavailable                  | `AttendanceWorker` checks `cap.isOpened()` and reports "Camera unavailable" via the status bar. |
| Missing `database/attendance.db`    | `attendance_viewer.py`, `dashboard.py`, `export_attendance.py` detect a missing DB file and show a message instead of raising. |
| Missing attendance CSV files        | `AttendanceWorker` recreates the day's CSV with headers if missing (same format as `attendance_manager.py`). |
| Missing embeddings (`embeddings/*.pkl`) | `gui.py` checks for `Config.EMBEDDINGS_FILE` / `Config.LABELS_FILE` before starting attendance and prompts the user to register a person first. |
| `matplotlib` not installed          | `dashboard.py` shows stat cards regardless and displays an install hint in place of charts. |

---

## 7. Quick Start

```bash
pip install -r requirements.txt   # now includes matplotlib
python gui.py
```

1. Click **Register Person** → follow prompts in the new console/window.
2. Click **Start Attendance** → live recognition window opens; attendance is
   written to CSV + SQLite as before.
3. Click **Stop Attendance** (or press `q` in the camera window) to end the
   session.
4. Click **View Attendance** to search/sort records.
5. Click **Dashboard** to see stats and charts.
6. Click **Export Attendance** to save CSV/Excel reports.
