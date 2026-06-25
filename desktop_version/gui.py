"""
gui.py
───────────────────────────────────────────────────────────────────────────────
Smart Attendance System — Tkinter GUI Launcher

A simple control-panel GUI that calls the EXISTING backend scripts/modules
instead of duplicating any logic:

  • Register Person   → register_face.py   (main())          [subprocess]
  • Start Attendance  → attendance_system.py run_attendance_system()  [thread]
  • Stop Attendance   → signals the running attendance thread to stop
  • View Attendance   → attendance_viewer.py launch_viewer()
  • Export Attendance → export_attendance.py (CSV / Excel)
  • Exit              → cleanly stops attendance loop (if running) and closes

WHY SUBPROCESS FOR register_face.py?
─────────────────────────────────────
register_face.py opens its own OpenCV window with a blocking capture loop
and interactive console prompts (input()). Running it as a subprocess keeps
the Tkinter main loop responsive and avoids OpenCV/Tk window-thread conflicts.

WHY THREAD FOR attendance_system.py?
─────────────────────────────────────
run_attendance_system() also has its own OpenCV window + while-loop, but it
doesn't use input(), so a background thread + an external "stop flag" works.
attendance_system.py is NOT modified — instead, gui.py reimplements a tiny
copy of its main loop here using the SAME underlying components
(EmbeddingStore, HaarFaceDetector, FaceNetEmbedder, FaceRecogniser, DBManager,
AttendanceManager) so it can be interrupted from the GUI. All heavy lifting
still comes from utils/ — no recognition or storage logic is duplicated.

USAGE
─────
  python gui.py
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import date, datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import cv2

from utils.config               import Config
from utils.logger                import get_logger
from utils.face_detector         import HaarFaceDetector, BBox
from utils.embedding_generator   import FaceNetEmbedder
from utils.embedding_store       import EmbeddingStore
from utils.similarity            import FaceRecogniser, RecognitionResult
from utils.db_manager            import DBManager

log = get_logger(__name__)
Config.ensure_dirs()


# ═══════════════════════════════════════════════════════════════════════════════
# ATTENDANCE WORKER (mirrors attendance_system.py's loop, but interruptible)
# ═══════════════════════════════════════════════════════════════════════════════

class AttendanceWorker:
    """
    Runs the live recognition loop in a background thread.

    Reuses the exact same components as attendance_system.py:
      EmbeddingStore, HaarFaceDetector, FaceNetEmbedder, FaceRecogniser,
      DBManager, and a small CSV-writing helper compatible with the
      attendance_<date>.csv format used elsewhere in the project.

    The OpenCV window runs inside this thread. Call stop() to signal the
    loop to exit; the OpenCV window will close on the next frame iteration.
    """

    def __init__(self, camera_index: int, threshold: float, on_status=None) -> None:
        self.camera_index = camera_index
        self.threshold    = threshold
        self.on_status    = on_status or (lambda msg: None)
        self._stop_event  = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ── Public control ──────────────────────────────────────────────────────
    def start(self) -> bool:
        if self.is_running():
            return False
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop_event.set()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── Worker body ──────────────────────────────────────────────────────────
    def _run(self) -> None:
        import csv

        try:
            store = EmbeddingStore()
        except Exception as exc:
            self.on_status(f"Error loading embedding store: {exc}")
            return

        if store.is_empty():
            self.on_status(
                "No registered faces found. Use 'Register Person' first."
            )
            return

        try:
            ref_embeddings, ref_names = store.get_mean_embeddings()
            db         = DBManager()
            detector   = HaarFaceDetector()
            embedder   = FaceNetEmbedder()
            recogniser = FaceRecogniser(threshold=self.threshold)
        except Exception as exc:
            self.on_status(f"Error initialising recognition components: {exc}")
            return

        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            self.on_status(
                f"Camera unavailable (index={self.camera_index}). "
                "Check the device or try a different camera index."
            )
            try:
                db.close()
            except Exception:
                pass
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  Config.WEBCAM_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, Config.WEBCAM_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS,          Config.WEBCAM_FPS)

        self.on_status("Attendance system running. Press 'q' or click Stop to end.")

        cooldowns: Dict[str, datetime] = {}
        today_str = date.today().isoformat()
        csv_path  = (
            Config.ATTENDANCE_DIR /
            f"{Config.ATTENDANCE_CSV_PREFIX}_{today_str}.csv"
        )
        self._ensure_csv(csv_path)

        frame_count   = 0
        process_every = 3
        last_bboxes:  List[BBox]              = []
        last_results: List[RecognitionResult] = []
        session_marked: Dict[str, bool] = {}

        try:
            while not self._stop_event.is_set():
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.05)
                    continue

                # ── Midnight rollover ───────────────────────────────────────
                today_now = date.today().isoformat()
                if today_now != today_str:
                    today_str = today_now
                    csv_path  = (
                        Config.ATTENDANCE_DIR /
                        f"{Config.ATTENDANCE_CSV_PREFIX}_{today_str}.csv"
                    )
                    self._ensure_csv(csv_path)

                frame_count += 1
                bboxes = detector.detect_bboxes(frame)

                if bboxes and (frame_count % process_every == 0):
                    crops, valid_bboxes = [], []
                    h_f, w_f = frame.shape[:2]
                    for (x, y, w, h) in bboxes:
                        pad_w, pad_h = int(w * 0.15), int(h * 0.15)
                        x1, y1 = max(0, x - pad_w), max(0, y - pad_h)
                        x2, y2 = min(w_f, x + w + pad_w), min(h_f, y + h + pad_h)
                        crop_bgr = frame[y1:y2, x1:x2]
                        crop_rgb = cv2.cvtColor(
                            cv2.resize(crop_bgr, (160, 160),
                                       interpolation=cv2.INTER_LANCZOS4),
                            cv2.COLOR_BGR2RGB,
                        )
                        crops.append(crop_rgb)
                        valid_bboxes.append((x, y, w, h))

                    if crops:
                        embs = embedder.get_embeddings_batch(crops)
                        results = recogniser.batch_recognise(embs, ref_embeddings, ref_names)

                        for result in results:
                            if result.is_known:
                                now = datetime.now()
                                last = cooldowns.get(result.name)
                                if last is None or (now - last).total_seconds() >= Config.ATTENDANCE_COOLDOWN_SECONDS:
                                    cooldowns[result.name] = now
                                    self._mark(csv_path, db, result, now)
                                    session_marked[result.name] = True

                        last_bboxes  = valid_bboxes
                        last_results = results
                elif not bboxes:
                    last_bboxes  = []
                    last_results = []

                display_bboxes  = bboxes if (frame_count % process_every == 0) else last_bboxes
                display_results = last_results

                if display_bboxes and not display_results:
                    display_results = [
                        RecognitionResult(
                            name="…", similarity=0.0, is_known=False,
                            threshold=self.threshold, all_scores=[],
                            confidence_band="low",
                        )
                    ] * len(display_bboxes)

                annotated = self._draw_overlay(frame, display_bboxes, display_results, session_marked)
                cv2.imshow("Smart Attendance System", annotated)

                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
        except Exception as exc:
            log.error(f"AttendanceWorker loop error: {exc}")
            self.on_status(f"Attendance loop error: {exc}")
        finally:
            cap.release()
            cv2.destroyAllWindows()
            try:
                db.close()
            except Exception:
                pass
            self.on_status("Attendance system stopped.")

    # ── Helpers ──────────────────────────────────────────────────────────────
    @staticmethod
    def _ensure_csv(csv_path: Path) -> None:
        import csv as _csv
        if not csv_path.exists():
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                _csv.writer(f).writerow(
                    ["Name", "Date", "Time", "Similarity", "Confidence", "Status"]
                )

    @staticmethod
    def _mark(csv_path: Path, db: DBManager, result: RecognitionResult, now: datetime) -> None:
        import csv as _csv
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")
        try:
            with open(csv_path, "a", newline="", encoding="utf-8") as f:
                _csv.writer(f).writerow(
                    [result.name, date_str, time_str,
                     f"{result.similarity:.4f}", result.confidence_band, "Present"]
                )
        except OSError as exc:
            log.error(f"CSV write failed for {result.name}: {exc}")

        db.insert_attendance(result.name, date_str, time_str, result.similarity)
        log.info(f"Attendance marked: {result.name} @ {time_str} sim={result.similarity:.4f}")

    @staticmethod
    def _draw_overlay(frame, bboxes, results, marked) -> "cv2.Mat":
        out = frame.copy()
        for (x, y, w, h), result in zip(bboxes, results):
            already = marked.get(result.name, False)
            if result.is_known:
                if result.confidence_band == "high":
                    color = (0, 255, 0) if already else (0, 200, 50)
                else:
                    color = (0, 165, 255) if already else (255, 200, 0)
            else:
                color = Config.BOX_COLOR_UNKNOWN

            cv2.rectangle(out, (x, y), (x + w, y + h), color, 2)
            label   = f"{result.name}  ({result.similarity:.2f})"
            label_y = y - 10 if y > 30 else y + h + 20
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
            cv2.rectangle(out, (x, label_y - th - 4), (x + tw, label_y + 4), color, cv2.FILLED)
            cv2.putText(out, label, (x, label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                        (0, 0, 0), 2, cv2.LINE_AA)

        h_frame = out.shape[0]
        cv2.rectangle(out, (0, h_frame - 30), (out.shape[1], h_frame), (0, 0, 0), cv2.FILLED)
        ts = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        cv2.putText(out, f"  {ts}  |  Press 'q' to quit", (5, h_frame - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA)
        return out


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN GUI WINDOW
# ═══════════════════════════════════════════════════════════════════════════════

class AttendanceGUI(tk.Tk):
    """Main control-panel window."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Smart Attendance System")
        self.geometry("420x420")
        self.resizable(False, False)

        self.worker: Optional[AttendanceWorker] = None

        self._build_widgets()

    # ── UI construction ─────────────────────────────────────────────────────
    def _build_widgets(self) -> None:
        ttk.Label(
            self, text="Smart Attendance System",
            font=("Segoe UI", 16, "bold")
        ).pack(pady=(20, 4))

        ttk.Label(
            self, text="FaceNet + Haar Cascade + Cosine Similarity",
            font=("Segoe UI", 9)
        ).pack(pady=(0, 16))

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=4)

        buttons = [
            ("Register Person",   self.on_register),
            ("Start Attendance",  self.on_start_attendance),
            ("Stop Attendance",   self.on_stop_attendance),
            ("View Attendance",   self.on_view_attendance),
            ("Dashboard",         self.on_dashboard),
            ("Export Attendance", self.on_export_attendance),
            ("Exit",              self.on_exit),
        ]

        for text, cmd in buttons:
            ttk.Button(btn_frame, text=text, command=cmd, width=28)\
                .pack(pady=6)

        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(self, textvariable=self.status_var, wraplength=380,
                  foreground="#444", anchor="center", justify="center")\
            .pack(side="bottom", fill="x", padx=10, pady=10)

    # ── Status helper (thread-safe via Tk's after()) ─────────────────────────
    def _set_status(self, msg: str) -> None:
        self.after(0, lambda: self.status_var.set(msg))

    # ── Button: Register Person ──────────────────────────────────────────────
    def on_register(self) -> None:
        """
        Launch register_face.py as a subprocess.

        register_face.py opens its own webcam window and uses interactive
        console input(), so it runs in a separate process/console.
        """
        script = PROJECT_ROOT / "register_face.py"
        if not script.exists():
            messagebox.showerror("Error", f"register_face.py not found at {script}")
            return

        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(
                    [sys.executable, str(script)],
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
            else:
                subprocess.Popen([sys.executable, str(script)])
            self._set_status(
                "Register Person launched in a separate window/terminal. "
                "Follow the on-screen prompts there."
            )
        except OSError as exc:
            messagebox.showerror("Error", f"Could not launch register_face.py:\n{exc}")

    # ── Button: Start Attendance ─────────────────────────────────────────────
    def on_start_attendance(self) -> None:
        if not Config.EMBEDDINGS_FILE.exists() or not Config.LABELS_FILE.exists():
            messagebox.showwarning(
                "No Registered Faces",
                "No embeddings found. Please register at least one person "
                "before starting attendance."
            )
            return

        if self.worker and self.worker.is_running():
            messagebox.showinfo("Already Running", "Attendance system is already running.")
            return

        self.worker = AttendanceWorker(
            camera_index = Config.WEBCAM_INDEX,
            threshold    = Config.COSINE_THRESHOLD,
            on_status    = self._set_status,
        )
        if self.worker.start():
            self._set_status("Starting attendance system…")
        else:
            messagebox.showinfo("Already Running", "Attendance system is already running.")

    # ── Button: Stop Attendance ──────────────────────────────────────────────
    def on_stop_attendance(self) -> None:
        if not self.worker or not self.worker.is_running():
            self._set_status("Attendance system is not running.")
            return
        self.worker.stop()
        self._set_status("Stopping attendance system…")

    # ── Button: View Attendance ──────────────────────────────────────────────
    def on_view_attendance(self) -> None:
        try:
            from attendance_viewer import launch_viewer
            launch_viewer(parent=self)
        except ImportError as exc:
            messagebox.showerror("Error", f"attendance_viewer.py not found:\n{exc}")
        except Exception as exc:
            messagebox.showerror("Error", f"Could not open Attendance Viewer:\n{exc}")

    # ── Button: Dashboard ─────────────────────────────────────────────────────
    def on_dashboard(self) -> None:
        try:
            from dashboard import launch_dashboard
            launch_dashboard(parent=self)
        except ImportError as exc:
            messagebox.showerror("Error", f"dashboard.py not found:\n{exc}")
        except Exception as exc:
            messagebox.showerror("Error", f"Could not open Dashboard:\n{exc}")

    # ── Button: Export Attendance ────────────────────────────────────────────
    def on_export_attendance(self) -> None:
        if not Config.DB_FILE.exists():
            messagebox.showwarning(
                "No Database",
                f"Attendance database not found at:\n{Config.DB_FILE}\n\n"
                "Run attendance at least once before exporting."
            )
            return

        win = tk.Toplevel(self)
        win.title("Export Attendance")
        win.geometry("320x150")
        win.resizable(False, False)

        ttk.Label(win, text="Choose export format:", font=("Segoe UI", 11))\
            .pack(pady=(16, 8))

        status_var = tk.StringVar(value="")
        ttk.Label(win, textvariable=status_var, wraplength=280, foreground="#444")\
            .pack(pady=(0, 8))

        def do_export(fmt: str) -> None:
            try:
                from export_attendance import export_to_csv, export_to_excel
                if fmt == "csv":
                    path = export_to_csv()
                else:
                    path = export_to_excel()
                status_var.set(f"Exported:\n{path}")
            except FileNotFoundError as exc:
                status_var.set(str(exc))
            except ImportError as exc:
                status_var.set(f"export_attendance.py not found:\n{exc}")
            except Exception as exc:
                status_var.set(f"Export failed:\n{exc}")

        btns = ttk.Frame(win)
        btns.pack(pady=4)
        ttk.Button(btns, text="CSV (.csv)",   command=lambda: do_export("csv")).pack(side="left", padx=8)
        ttk.Button(btns, text="Excel (.xlsx)", command=lambda: do_export("excel")).pack(side="left", padx=8)

    # ── Button: Exit ──────────────────────────────────────────────────────────
    def on_exit(self) -> None:
        if self.worker and self.worker.is_running():
            self.worker.stop()
            # Give the worker a brief moment to release the camera/window
            self.after(300, self.destroy)
        else:
            self.destroy()


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = AttendanceGUI()
    app.mainloop()
