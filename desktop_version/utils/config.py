"""
utils/config.py
───────────────────────────────────────────────────────────────────────────────
Centralised configuration for the Smart Attendance System.

Every tunable constant lives here so that no magic numbers are scattered
across the codebase.  Import with:
    from utils.config import Config

CHANGELOG
─────────
v2 — Added LOGS_DIR, EXPORTS_DIR, DB_SCHEMA_VERSION, RECOGNITION_TOP_K,
         HAAR_FLAGS, and updated ensure_dirs() to create all directories.
───────────────────────────────────────────────────────────────────────────────
"""

import os
from pathlib import Path


class Config:
    # ── Project root (resolves to Smart_Attendance_System/) ──────────────────
    BASE_DIR: Path = Path(__file__).resolve().parent.parent

    # ── Directory paths ───────────────────────────────────────────────────────
    REGISTERED_FACES_DIR: Path = BASE_DIR / "registered_faces"
    EMBEDDINGS_DIR:        Path = BASE_DIR / "embeddings"
    ATTENDANCE_DIR:        Path = BASE_DIR / "attendance"
    DATABASE_DIR:          Path = BASE_DIR / "database"
    LOGS_DIR:              Path = BASE_DIR / "logs"      # rotating log files
    EXPORTS_DIR:           Path = BASE_DIR / "exports"   # Excel / CSV exports

    # ── Embedding storage files ───────────────────────────────────────────────
    EMBEDDINGS_FILE:  Path = EMBEDDINGS_DIR / "face_embeddings.pkl"
    LABELS_FILE:      Path = EMBEDDINGS_DIR / "labels.pkl"
    METADATA_FILE:    Path = EMBEDDINGS_DIR / "metadata.json"   # registration timestamps

    # ── Attendance CSV file (one per day is created automatically) ────────────
    ATTENDANCE_CSV_PREFIX: str = "attendance"    # e.g. attendance_2024-06-12.csv

    # ── SQLite database (optional – used by attendance_manager) ──────────────
    DB_FILE: Path = DATABASE_DIR / "attendance.db"

    # ── Haar Cascade ─────────────────────────────────────────────────────────
    #   OpenCV ships haarcascade_frontalface_default.xml inside its data dir.
    #   We resolve it automatically so the user never needs to set a path.
    HAAR_CASCADE_PATH: str = str(
        Path(os.path.dirname(__file__)).parent
        / "haarcascades"
        / "haarcascade_frontalface_default.xml"
    )

    # Haar Cascade detection parameters
    HAAR_SCALE_FACTOR:    float = 1.1    # How much the image is reduced each scale
    HAAR_MIN_NEIGHBORS:   int   = 5      # Minimum neighbours for a rectangle to be retained
    HAAR_MIN_FACE_SIZE:   tuple = (60, 60)  # Ignore faces smaller than this (pixels)

    # ── FaceNet / InceptionResnetV1 ───────────────────────────────────────────
    FACENET_IMAGE_SIZE:   int  = 160     # FaceNet expects exactly 160×160 RGB
    FACENET_PRETRAINED:   str  = "vggface2"   # Pre-trained weights: 'vggface2' | 'casia-webface'
    EMBEDDING_DIM:        int  = 512     # Output embedding dimension from FaceNet

    # ── Cosine Similarity ─────────────────────────────────────────────────────
    #   Cosine similarity ranges from -1 (opposite) to +1 (identical).
    #   A threshold of 0.70–0.80 works well for FaceNet embeddings.
    COSINE_THRESHOLD:     float = 0.75   # Below this → "Unknown"
    #   When multiple embeddings exist for one person, we use the MEAN embedding.
    USE_MEAN_EMBEDDING:   bool  = True
    #   Number of top candidates to return in recognition result (for logging)
    RECOGNITION_TOP_K:    int   = 3      # Returned in RecognitionResult.all_scores

    # ── Database ──────────────────────────────────────────────────────────────
    DB_SCHEMA_VERSION:    int   = 2      # Increment when schema changes

    # ── Webcam ────────────────────────────────────────────────────────────────
    WEBCAM_INDEX:         int   = 0      # 0 = default webcam; change for USB cam
    WEBCAM_WIDTH:         int   = 640
    WEBCAM_HEIGHT:        int   = 480
    WEBCAM_FPS:           int   = 30

    # ── Attendance logic ──────────────────────────────────────────────────────
    #   Prevent marking the same person twice within this many seconds.
    ATTENDANCE_COOLDOWN_SECONDS: int = 30

    # ── Display / UI ──────────────────────────────────────────────────────────
    FONT                  = None        # cv2.FONT_HERSHEY_SIMPLEX (set at runtime)
    BOX_COLOR_KNOWN:  tuple = (0, 255, 0)    # Green  – recognised face
    BOX_COLOR_UNKNOWN: tuple = (0, 0, 255)   # Red    – unknown face
    TEXT_COLOR:       tuple = (255, 255, 255) # White text
    BOX_THICKNESS:    int   = 2

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"    # DEBUG | INFO | WARNING | ERROR

    # ── Ensure all directories exist on import ────────────────────────────────
    @classmethod
    def ensure_dirs(cls) -> None:
        """Create all required directories if they don't already exist."""
        for d in [
            cls.REGISTERED_FACES_DIR,
            cls.EMBEDDINGS_DIR,
            cls.ATTENDANCE_DIR,
            cls.DATABASE_DIR,
            cls.LOGS_DIR,
            cls.EXPORTS_DIR,
        ]:
            d.mkdir(parents=True, exist_ok=True)
