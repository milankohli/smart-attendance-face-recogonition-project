"""
register_face.py
───────────────────────────────────────────────────────────────────────────────
Smart Attendance System — Live Webcam Face Registration Pipeline

WORKFLOW
────────
  1. Prompt user for person's name
  2. Open webcam (OpenCV VideoCapture)
  3. Detect faces in each frame using Haar Cascade
  4. Automatically capture 30 face samples (with on-screen progress)
  5. Crop + resize each captured face to 160×160 RGB
  6. Save crops to registered_faces/<person_name>/
  7. Generate 512-D FaceNet embeddings for all captured faces
  8. Append new embeddings to the persistent store (never overwrites existing)
  9. Press 'q' at any time to cancel registration

USAGE
─────
  python register_face.py
  python register_face.py --name "Alice Smith"
  python register_face.py --camera 1 --samples 30 --padding 0.15
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from typing import List

import cv2
import numpy as np
from colorama import init as colorama_init, Fore, Style

# ── Bootstrap: ensure the project root is on sys.path ────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── Internal imports ──────────────────────────────────────────────────────────
from utils.config               import Config
from utils.logger                import get_logger
from utils.face_detector         import HaarFaceDetector
from utils.embedding_generator   import FaceNetEmbedder
from utils.embedding_store       import EmbeddingStore

# ── Initialise ────────────────────────────────────────────────────────────────
colorama_init(autoreset=True)          # Windows-safe colour reset
log = get_logger(__name__)
Config.ensure_dirs()


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — BANNER / PRINT HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _print_banner() -> None:
    print(Fore.CYAN + Style.BRIGHT + """
╔══════════════════════════════════════════════════════╗
║        SMART ATTENDANCE SYSTEM — Face Registration   ║
║        FaceNet + Haar Cascade + Cosine Similarity    ║
╚══════════════════════════════════════════════════════╝
""" + Style.RESET_ALL)


def _print_success(msg: str) -> None:
    print(Fore.GREEN + f"  ✓  {msg}" + Style.RESET_ALL)


def _print_warning(msg: str) -> None:
    print(Fore.YELLOW + f"  ⚠  {msg}" + Style.RESET_ALL)


def _print_error(msg: str) -> None:
    print(Fore.RED + f"  ✗  {msg}" + Style.RESET_ALL)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — ARGUMENT PARSING
# ═══════════════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    """
    Parse CLI arguments.

    --name     : Person's display name (spaces allowed). If omitted, prompted.
    --camera   : Webcam device index (default from Config.WEBCAM_INDEX).
    --samples  : Number of face samples to capture (default 30).
    --padding  : Bounding-box padding fraction (default 0.15).
    --interval : Minimum seconds between captures (default 0.2).
    --no-confirm : Skip confirmation prompt before saving embeddings.
    """
    parser = argparse.ArgumentParser(
        prog="register_face.py",
        description="Register a new person's face into the attendance system via webcam.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python register_face.py
  python register_face.py --name "Alice Smith"
  python register_face.py --camera 1 --samples 30
        """,
    )
    parser.add_argument(
        "--name", "-n", type=str, default=None,
        help="Person's full name (e.g. 'Alice Smith')"
    )
    parser.add_argument(
        "--camera", type=int, default=Config.WEBCAM_INDEX,
        help=f"Webcam device index (default: {Config.WEBCAM_INDEX})"
    )
    parser.add_argument(
        "--samples", type=int, default=30,
        help="Number of face samples to automatically capture (default: 30)"
    )
    parser.add_argument(
        "--padding", type=float, default=0.15,
        help="Bounding-box padding fraction (default: 0.15)"
    )
    parser.add_argument(
        "--interval", type=float, default=0.2,
        help="Minimum seconds between consecutive captures (default: 0.2)"
    )
    parser.add_argument(
        "--no-confirm", action="store_true",
        help="Skip confirmation prompt before saving embeddings"
    )
    return parser.parse_args()


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — INTERACTIVE NAME INPUT
# ═══════════════════════════════════════════════════════════════════════════════

def _get_name_interactive(store: EmbeddingStore) -> str:
    """
    Prompt the user for a person's name.

    • Validates non-empty input.
    • Sanitises to letters, spaces, hyphens, apostrophes, dots.
    • Warns if the name already exists (allows update / new images).
    """
    while True:
        name = input(
            Fore.CYAN + "\n  Enter person's name: " + Style.RESET_ALL
        ).strip()

        if not name:
            _print_error("Name cannot be empty.  Please try again.")
            continue

        if not re.match(r"^[A-Za-z\s'\-\.]+$", name):
            _print_warning(
                "Name contains unusual characters.  "
                "Only letters, spaces, hyphens, dots, and apostrophes are allowed."
            )
            continue

        if name in store.list_people():
            _print_warning(
                f"'{name}' already has {store.metadata[name]['count']} embedding(s) "
                "in the database.  New images will be APPENDED (no data lost)."
            )

        return name


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — SAVE CROPS
# ═══════════════════════════════════════════════════════════════════════════════

def save_cropped_faces(name: str, crops: List[np.ndarray]) -> List[Path]:
    """
    Save 160×160 RGB face crops to registered_faces/<name>/.

    File naming convention: capture_<timestamp>_<idx>.jpg

    Returns
    -------
    List of saved file paths.
    """
    person_dir = Config.REGISTERED_FACES_DIR / name.replace(" ", "_")
    person_dir.mkdir(parents=True, exist_ok=True)

    ts = int(time.time())
    saved_paths: List[Path] = []

    for idx, crop_rgb in enumerate(crops):
        crop_bgr  = cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2BGR)
        out_path  = person_dir / f"capture_{ts}_{idx}.jpg"
        cv2.imwrite(str(out_path), crop_bgr)
        saved_paths.append(out_path)
        log.debug(f"Saved crop: {out_path}")

    log.info(f"Saved {len(saved_paths)} crop(s) to {person_dir}")
    return saved_paths


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — LIVE WEBCAM CAPTURE
# ═══════════════════════════════════════════════════════════════════════════════

def capture_face_samples(
    detector:     HaarFaceDetector,
    name:         str,
    target_count: int,
    camera_index: int,
    padding:      float,
    capture_interval: float,
) -> List[np.ndarray]:
    """
    Open the webcam, detect faces, and automatically capture `target_count`
    160×160 RGB face crops.

    Controls
    ────────
    • Capture happens automatically whenever exactly one face is detected
      and `capture_interval` seconds have elapsed since the last capture.
    • Press 'q' at any time to cancel registration.

    Returns
    -------
    List of (160, 160, 3) uint8 RGB face crops, length <= target_count.
    Returns an empty list if cancelled before any captures, or webcam
    could not be opened.
    """
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        _print_error(f"Could not open webcam (index={camera_index}).")
        return []

    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  Config.WEBCAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, Config.WEBCAM_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS,          Config.WEBCAM_FPS)

    window_name = f"Register Face - {name}  (press 'q' to cancel)"
    captured_crops: List[np.ndarray] = []
    last_capture_time = 0.0
    no_face_streak = 0

    _print_success("Webcam opened. Look at the camera. Press 'q' to cancel.")
    log.info(f"Starting webcam capture for '{name}' (target={target_count})")

    try:
        while len(captured_crops) < target_count:
            ok, frame_bgr = cap.read()
            if not ok or frame_bgr is None:
                _print_error("Failed to read frame from webcam.")
                break

            bboxes = detector.detect_bboxes(frame_bgr)
            display = frame_bgr.copy()

            if len(bboxes) == 0:
                no_face_streak += 1
                status_text  = "No face detected"
                status_color = Config.BOX_COLOR_UNKNOWN
            elif len(bboxes) > 1:
                no_face_streak = 0
                status_text  = "Multiple faces — show only ONE face"
                status_color = Config.BOX_COLOR_UNKNOWN
                for (x, y, w, h) in bboxes:
                    cv2.rectangle(display, (x, y), (x + w, y + h),
                                  Config.BOX_COLOR_UNKNOWN, Config.BOX_THICKNESS)
            else:
                no_face_streak = 0
                x, y, w, h = bboxes[0]
                cv2.rectangle(display, (x, y), (x + w, y + h),
                              Config.BOX_COLOR_KNOWN, Config.BOX_THICKNESS)

                now = time.time()
                if (now - last_capture_time) >= capture_interval:
                    crops = detector.detect_and_crop(
                        frame_bgr, padding=padding
                    )
                    if crops:
                        captured_crops.append(crops[0])
                        last_capture_time = now
                        log.info(
                            f"Captured sample {len(captured_crops)}/{target_count}"
                        )

                status_text  = "Face detected"
                status_color = Config.BOX_COLOR_KNOWN

            # ── On-screen progress overlay ────────────────────────────────
            progress = f"Samples: {len(captured_crops)} / {target_count}"
            cv2.putText(display, progress, (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                        Config.TEXT_COLOR, 2, cv2.LINE_AA)
            cv2.putText(display, status_text, (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        status_color, 2, cv2.LINE_AA)
            cv2.putText(display, "Press 'q' to cancel", (10, display.shape[0] - 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        Config.TEXT_COLOR, 1, cv2.LINE_AA)

            # Progress bar
            bar_w = display.shape[1] - 20
            filled = int(bar_w * (len(captured_crops) / target_count))
            cv2.rectangle(display, (10, 70), (10 + bar_w, 85), (80, 80, 80), -1)
            cv2.rectangle(display, (10, 70), (10 + filled, 85),
                          Config.BOX_COLOR_KNOWN, -1)

            cv2.imshow(window_name, display)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                _print_warning("Registration cancelled by user.")
                log.info("Webcam capture cancelled by user ('q' pressed).")
                captured_crops = []
                break

            if no_face_streak == 1 or no_face_streak % 60 == 0:
                if no_face_streak > 0:
                    log.debug("No face detected in current frame.")

    finally:
        cap.release()
        cv2.destroyAllWindows()

    return captured_crops


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — CORE REGISTRATION PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

def register_person(
    name:         str,
    detector:     HaarFaceDetector,
    embedder:     FaceNetEmbedder,
    store:        EmbeddingStore,
    target_count: int,
    camera_index: int,
    padding:      float,
    capture_interval: float,
) -> int:
    """
    Full webcam registration pipeline for ONE person.

    Steps
    ─────
      1. Capture `target_count` 160×160 RGB face crops from the webcam.
      2. Save crops to registered_faces/<name>/ for inspection.
      3. Generate FaceNet embeddings for all captured crops (batch).
      4. Append embeddings to the persistent EmbeddingStore.

    Returns
    -------
    int – number of embeddings successfully generated and stored.
          0 if cancelled or no faces were captured.
    """
    crops = capture_face_samples(
        detector          = detector,
        name              = name,
        target_count      = target_count,
        camera_index      = camera_index,
        padding           = padding,
        capture_interval  = capture_interval,
    )

    if not crops:
        _print_error(
            "No face samples captured — registration aborted.\n"
            "  Tip: ensure good lighting and face the camera directly."
        )
        return 0

    _print_success(f"Captured {len(crops)} face sample(s).")

    # ── Save crops for inspection ─────────────────────────────────────────
    save_cropped_faces(name, crops)

    # ── Generate FaceNet Embeddings ────────────────────────────────────────
    print(Fore.CYAN + "  Generating FaceNet embeddings …" + Style.RESET_ALL)

    embeddings_matrix = embedder.get_embeddings_batch(crops)
    # embeddings_matrix  shape: (N, 512)  float32

    _print_success(
        f"Embeddings generated: {embeddings_matrix.shape[0]} × "
        f"{embeddings_matrix.shape[1]}-D"
    )

    # ── Append to Persistent Store (never overwrites) ─────────────────────
    total_stored = store.add_person(name, embeddings_matrix)

    _print_success(
        f"Saved {len(embeddings_matrix)} new embedding(s) for '{name}'.\n"
        f"  Total embeddings for '{name}': {total_stored}\n"
        f"  Store location: {Config.EMBEDDINGS_FILE}"
    )

    return len(embeddings_matrix)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — REGISTRATION SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════

def _print_summary(store: EmbeddingStore, name: str) -> None:
    """Print a formatted registration summary table."""
    try:
        from tabulate import tabulate   # installed via requirements.txt
    except ImportError:
        _print_success(
            f"Registration complete for '{name}'. "
            f"Total identities: {len(store.list_people())}."
        )
        return

    people = store.list_people()
    rows = []
    for p in people:
        meta = store.metadata.get(p, {})
        rows.append([
            ("→ " if p == name else "  ") + p,
            meta.get("count", "?"),
            meta.get("registered_at", "?"),
            meta.get("updated_at", "?"),
        ])

    print("\n" + Fore.CYAN + Style.BRIGHT + "  ═══ Embedding Database Summary ═══" + Style.RESET_ALL)
    print(tabulate(
        rows,
        headers=["  Name", "Embeddings", "First Registered", "Last Updated"],
        tablefmt="rounded_outline",
    ))
    print(f"\n  Total identities: {len(people)}  |  Total embeddings: {len(store)}\n")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 8 — MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    _print_banner()

    args = parse_args()

    if args.samples <= 0:
        _print_error("--samples must be a positive integer.")
        sys.exit(1)

    # ── Initialise shared components (loaded ONCE) ────────────────────────
    log.info("Loading Haar Cascade face detector …")
    detector = HaarFaceDetector()

    log.info("Loading FaceNet model (InceptionResnetV1) …")
    embedder = FaceNetEmbedder()

    log.info("Loading embedding store …")
    store    = EmbeddingStore()

    print(Fore.CYAN + f"  Current store: {store}" + Style.RESET_ALL)

    # ── Get name ──────────────────────────────────────────────────────────
    if args.name:
        name = args.name.strip()
        if not re.match(r"^[A-Za-z\s'\-\.]+$", name):
            _print_error(
                "Name contains unusual characters. "
                "Only letters, spaces, hyphens, dots, and apostrophes are allowed."
            )
            sys.exit(1)
        if name in store.list_people():
            _print_warning(
                f"'{name}' already registered "
                f"({store.metadata[name]['count']} embedding(s)).  "
                "New samples will be appended."
            )
    else:
        name = _get_name_interactive(store)

    # ── Confirmation ──────────────────────────────────────────────────────
    if not args.no_confirm:
        confirm = input(
            Fore.YELLOW +
            f"\n  Start webcam capture of {args.samples} sample(s) for '{name}'? [Y/n]: " +
            Style.RESET_ALL
        ).strip().lower()
        if confirm not in ("", "y", "yes"):
            print("  Cancelled.")
            sys.exit(0)

    # ── Run registration pipeline ─────────────────────────────────────────
    n_new = register_person(
        name             = name,
        detector         = detector,
        embedder         = embedder,
        store            = store,
        target_count     = args.samples,
        camera_index     = args.camera,
        padding          = args.padding,
        capture_interval = args.interval,
    )

    if n_new == 0:
        _print_error("Registration failed — no embeddings were generated.")
        sys.exit(1)

    # ── Print summary ─────────────────────────────────────────────────────
    _print_summary(store, name)

    print(Fore.GREEN + Style.BRIGHT +
          "  Registration successful!  Run attendance_system.py to start recognition.\n" +
          Style.RESET_ALL)


if __name__ == "__main__":
    main()
