"""
attendance_system.py
───────────────────────────────────────────────────────────────────────────────
Smart Attendance System — Live Webcam Recognition

WORKFLOW
────────
  1. Load stored mean embeddings from EmbeddingStore
  2. Open webcam (default index 0)
  3. For each frame:
       a. Detect faces using Haar Cascade
       b. Crop + resize each face to 160×160 RGB
       c. Generate FaceNet embedding
       d. Compare with reference embeddings via cosine similarity
       e. If similarity >= threshold → person is recognised
       f. Enforce cooldown (avoid marking the same person twice in 30 s)
       g. Mark attendance via AttendanceManager
       h. Draw bounding box + name + confidence on frame
  4. Display live feed until user presses 'q'

USAGE
─────
  python attendance_system.py
  python attendance_system.py --camera 1 --threshold 0.78
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from colorama import init as colorama_init, Fore, Style

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.config              import Config
from utils.logger              import get_logger
from utils.face_detector       import HaarFaceDetector, BBox
from utils.embedding_generator import FaceNetEmbedder
from utils.embedding_store     import EmbeddingStore
from utils.similarity          import FaceRecogniser, RecognitionResult
from utils.db_manager          import DBManager

colorama_init(autoreset=True)
log = get_logger(__name__)
Config.ensure_dirs()


# ═══════════════════════════════════════════════════════════════════════════════
# INLINE AttendanceManager — Dual Storage (CSV + SQLite)
# ═══════════════════════════════════════════════════════════════════════════════

import csv
from datetime import date

class _AttendanceManager:
    """
    Lightweight attendance logger used inside the live feed loop.

    Writes each record to BOTH:
      • Daily CSV  (human-readable backup, auto-named by date)
      • SQLite DB  (structured queries, via DBManager)

    The cooldown check is local to this session only — it prevents marking
    the same person twice within ATTENDANCE_COOLDOWN_SECONDS in one run.
    For cross-session deduplication the UNIQUE(name, date, time) DB constraint
    is the authoritative guard.
    """

    def __init__(self, db: DBManager) -> None:
        self._db        = db
        self._today     = date.today().isoformat()
        self._csv_path  = (
            Config.ATTENDANCE_DIR /
            f"{Config.ATTENDANCE_CSV_PREFIX}_{self._today}.csv"
        )
        self._marked: Dict[str, datetime] = {}  # name → last marked time
        self._ensure_csv()

    def _ensure_csv(self) -> None:
        if not self._csv_path.exists():
            with open(self._csv_path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(
                    ["Name", "Date", "Time", "Similarity", "Confidence", "Status"]
                )
            log.info(f"Created attendance CSV: {self._csv_path}")

    def _refresh_date(self) -> None:
        """Handle midnight roll-over: refresh today's date + CSV path."""
        today = date.today().isoformat()
        if today != self._today:
            self._today    = today
            self._csv_path = (
                Config.ATTENDANCE_DIR /
                f"{Config.ATTENDANCE_CSV_PREFIX}_{today}.csv"
            )
            self._ensure_csv()

    def already_marked_today(self, name: str) -> bool:
        """
        Check whether `name` already has an attendance record for today
        (in this session or a previous run), via the SQLite database.
        """
        self._refresh_date()
        return self._db.person_present_today(name, self._today)

    def mark(self, name: str, similarity: float,
             confidence_band: str = "medium") -> bool:
        """
        Mark attendance for `name` if cooldown has passed.

        Writes to BOTH CSV and SQLite.

        Returns True if attendance was newly marked, False if within cooldown.
        """
        now = datetime.now()
        self._refresh_date()

        # ── Session cooldown ──────────────────────────────────────────────
        if name in self._marked:
            elapsed = (now - self._marked[name]).total_seconds()
            if elapsed < Config.ATTENDANCE_COOLDOWN_SECONDS:
                return False

        self._marked[name] = now
        date_str = self._today
        time_str = now.strftime("%H:%M:%S")

        # ── CSV write ─────────────────────────────────────────────────────
        try:
            with open(self._csv_path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(
                    [name, date_str, time_str,
                     f"{similarity:.4f}", confidence_band, "Present"]
                )
        except OSError as exc:
            log.error(f"CSV write failed for {name}: {exc}")

        # ── SQLite write ──────────────────────────────────────────────────
        self._db.insert_attendance(name, date_str, time_str, similarity)

        log.info(
            f"Attendance marked: {name} @ {time_str}  "
            f"sim={similarity:.4f}  band={confidence_band}"
        )
        return True

    def get_csv_path(self) -> Path:
        return self._csv_path


# ═══════════════════════════════════════════════════════════════════════════════
# OVERLAY DRAWING
# ═══════════════════════════════════════════════════════════════════════════════

def draw_recognition_overlay(
    frame:   np.ndarray,
    bboxes:  List[BBox],
    results: List[RecognitionResult],
    marked:  Dict[str, bool],
) -> np.ndarray:
    """
    Draw bounding boxes, names, similarity scores, and attendance status.

    Colour coding (driven by confidence_band):
      GREEN  (0,255,0)   – high confidence (sim ≥ 0.85) + marked
      CYAN   (255,200,0) – medium confidence (threshold ≤ sim < 0.85)
      ORANGE (0,165,255) – high/medium + attendance already marked (cooldown)
      RED    (0,0,255)   – unknown face
    """
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

        # ── Bounding box ──────────────────────────────────────────────────
        cv2.rectangle(out, (x, y), (x + w, y + h), color, 2)

        # ── Name + similarity label ───────────────────────────────────────
        label      = f"{result.name}  ({result.similarity:.2f})"
        label_y    = y - 10 if y > 30 else y + h + 20

        # Text background for readability
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
        cv2.rectangle(out, (x, label_y - th - 4), (x + tw, label_y + 4),
                      color, cv2.FILLED)
        cv2.putText(out, label, (x, label_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                    (0, 0, 0), 2, cv2.LINE_AA)

        # ── "Attendance Marked!" flash ────────────────────────────────────
        if result.is_known and already:
            cv2.putText(
                out, "✓ Attendance Marked",
                (x, y + h + 35),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                Config.BOX_COLOR_KNOWN, 2, cv2.LINE_AA,
            )

    # ── Status bar at bottom ──────────────────────────────────────────────
    h_frame = out.shape[0]
    cv2.rectangle(out, (0, h_frame - 30), (out.shape[1], h_frame),
                  (0, 0, 0), cv2.FILLED)
    ts = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
    cv2.putText(out, f"  {ts}  |  Press 'q' to quit",
                (5, h_frame - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA)
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIRMATION BANNER (shown for 2 s after attendance is marked / already-marked)
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_confirmation_banner(
    frame: np.ndarray,
    message: str,
    color: Tuple[int, int, int],
) -> None:
    """
    Draw a large, centred confirmation banner (e.g. "✓ Attendance Marked"
    or "Attendance already marked") in-place on `frame`.

    Used right before the program closes the webcam and exits.
    """
    h, w = frame.shape[:2]

    # Semi-transparent dark overlay for contrast
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, h), (0, 0, 0), cv2.FILLED)
    cv2.addWeighted(overlay, 0.35, frame, 0.65, 0, dst=frame)

    text = message
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 1.1
    thickness = 3

    (tw, th), _ = cv2.getTextSize(text, font, scale, thickness)
    x = max(10, (w - tw) // 2)
    y = (h + th) // 2

    cv2.putText(frame, text, (x, y), font, scale, color, thickness, cv2.LINE_AA)

    sub_text = "Closing in a moment..."
    (sw, sh), _ = cv2.getTextSize(sub_text, font, 0.6, 1)
    sx = max(10, (w - sw) // 2)
    sy = y + th + 30
    cv2.putText(frame, sub_text, (sx, sy), font, 0.6,
                (200, 200, 200), 1, cv2.LINE_AA)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN LIVE-FEED LOOP
# ═══════════════════════════════════════════════════════════════════════════════

def run_attendance_system(
    camera_index: int   = Config.WEBCAM_INDEX,
    threshold:    float = Config.COSINE_THRESHOLD,
) -> None:
    """
    Main loop: open webcam, detect → embed → recognise → mark → display.
    """
    # ── Load components ───────────────────────────────────────────────────
    log.info("Loading embedding store …")
    store = EmbeddingStore()

    if store.is_empty():
        print(Fore.RED +
              "\n  No registered faces found!  "
              "Run register_face.py first.\n" + Style.RESET_ALL)
        return

    print(Fore.CYAN + f"\n  Registered identities: {store.list_people()}" + Style.RESET_ALL)

    # Pre-compute mean reference embeddings (one per person)
    ref_embeddings, ref_names = store.get_mean_embeddings()
    log.info(f"Reference matrix: {ref_embeddings.shape}")

    db         = DBManager()
    detector   = HaarFaceDetector()
    embedder   = FaceNetEmbedder()
    recogniser = FaceRecogniser(threshold=threshold)
    att_mgr    = _AttendanceManager(db=db)

    # Track who has been marked this session (for overlay colour)
    session_marked: Dict[str, bool] = {}

    # ── Open webcam ───────────────────────────────────────────────────────
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        log.error(f"Could not open camera index {camera_index}.")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  Config.WEBCAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, Config.WEBCAM_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS,          Config.WEBCAM_FPS)

    print(Fore.GREEN + "\n  Webcam started.  Press 'q' to quit.\n" + Style.RESET_ALL)
    log.info("Attendance system running …")

    frame_count   = 0
    process_every = 3          # Run heavy FaceNet inference every N frames
    last_bboxes:  List[BBox]             = []
    last_results: List[RecognitionResult] = []

    # ── Single-shot session control ────────────────────────────────────────
    # Once attendance is successfully marked (or found already-marked-today)
    # for a person, we display a confirmation overlay for 2 seconds, then
    # close the webcam and exit cleanly. This prevents repeated marking.
    attendance_done: bool = False
    done_message:    str  = ""
    done_color:      Tuple[int, int, int] = Config.BOX_COLOR_KNOWN
    exit_at:         Optional[float] = None
    POST_MARK_DELAY_SECONDS = 2.0

    while True:
        ret, frame = cap.read()
        if not ret:
            log.warning("Failed to read frame — retrying …")
            time.sleep(0.05)
            continue

        frame_count += 1
        bboxes = detector.detect_bboxes(frame)

        # ── Only run FaceNet inference every `process_every` frames ───────
        # On non-inference frames, reuse the last known results so the overlay
        # stays stable instead of flashing "Unknown" boxes.
        if not attendance_done and bboxes and (frame_count % process_every == 0):
            crops        = []
            valid_bboxes = []
            h_f, w_f     = frame.shape[:2]

            for (x, y, w, h) in bboxes:
                pad_w = int(w * 0.15)
                pad_h = int(h * 0.15)
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
                embs = embedder.get_embeddings_batch(crops)   # (K, 512)
                results = recogniser.batch_recognise(
                    embs, ref_embeddings, ref_names
                )

                # ── Mark attendance for each recognised face ───────────────
                for result in results:
                    if result.is_known:
                        # Already marked today (this session OR a previous
                        # run, per the SQLite UNIQUE constraint) — do not
                        # add another entry, just confirm and exit.
                        if result.name in session_marked or att_mgr.already_marked_today(result.name):
                            session_marked[result.name] = True
                            attendance_done = True
                            done_message    = "Attendance already marked"
                            done_color      = (255, 165, 0)  # orange
                            print(
                                Fore.YELLOW +
                                f"  ⚠ Attendance already marked today: {result.name}" +
                                Style.RESET_ALL
                            )
                            break

                        newly_marked = att_mgr.mark(
                            result.name, result.similarity,
                            result.confidence_band,
                        )
                        if newly_marked:
                            session_marked[result.name] = True
                            attendance_done = True
                            done_message    = "Attendance Marked"
                            done_color      = Config.BOX_COLOR_KNOWN
                            print(
                                Fore.GREEN +
                                f"  ✓ Attendance marked: {result.name}  "
                                f"(sim={result.similarity:.4f}  "
                                f"band={result.confidence_band})" +
                                Style.RESET_ALL
                            )
                            break

                # Cache for non-inference frames
                last_bboxes  = valid_bboxes
                last_results = results

        elif not bboxes and not attendance_done:
            # No faces detected — clear cached state
            last_bboxes  = []
            last_results = []

        # ── Use cached results on non-inference frames ────────────────────
        # This avoids the bug where bboxes ≠ [] but results = [] on frames
        # that are skipped, which previously showed all faces as Unknown.
        display_bboxes  = bboxes if (frame_count % process_every == 0) else last_bboxes
        display_results = last_results

        if display_bboxes and not display_results:
            display_results = [
                RecognitionResult(
                    name="…", similarity=0.0, is_known=False,
                    threshold=threshold, all_scores=[],
                    confidence_band="low",
                )
            ] * len(display_bboxes)

        # ── Draw overlay ──────────────────────────────────────────────────
        annotated = draw_recognition_overlay(
            frame, display_bboxes, display_results, session_marked
        )

        # ── Confirmation overlay + auto-exit timer ─────────────────────────
        if attendance_done:
            _draw_confirmation_banner(annotated, done_message, done_color)

            if exit_at is None:
                exit_at = time.time() + POST_MARK_DELAY_SECONDS

            cv2.imshow("Smart Attendance System", annotated)
            cv2.waitKey(1)

            if time.time() >= exit_at:
                break

            continue

        cv2.imshow("Smart Attendance System", annotated)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
    db.close()

    print(Fore.CYAN + f"\n  Attendance CSV  : {att_mgr.get_csv_path()}" + Style.RESET_ALL)
    print(Fore.CYAN + f"  Attendance DB   : {Config.DB_FILE}" + Style.RESET_ALL)
    log.info("Attendance system stopped.")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Smart Attendance System — Live Mode")
    p.add_argument("--camera",    type=int,   default=Config.WEBCAM_INDEX,
                   help="Camera index (default: 0)")
    p.add_argument("--threshold", type=float, default=Config.COSINE_THRESHOLD,
                   help="Cosine similarity threshold (default: 0.75)")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_attendance_system(camera_index=args.camera, threshold=args.threshold)
