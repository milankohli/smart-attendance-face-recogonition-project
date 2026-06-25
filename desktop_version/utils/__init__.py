"""
utils/__init__.py
─────────────────────────────────────────────────────────────────────────────
Package marker for the Smart Attendance System utility modules.

Convenience re-exports so callers can write:
    from utils import Config, get_logger
instead of the full dotted path.
─────────────────────────────────────────────────────────────────────────────
"""

from utils.config              import Config          # noqa: F401
from utils.logger              import get_logger      # noqa: F401
from utils.face_detector       import HaarFaceDetector, BBox, FaceRGB  # noqa: F401
from utils.embedding_generator import FaceNetEmbedder # noqa: F401
from utils.embedding_store     import EmbeddingStore  # noqa: F401
from utils.similarity          import FaceRecogniser, RecognitionResult  # noqa: F401
from utils.db_manager          import DBManager       # noqa: F401

__all__ = [
    "Config",
    "get_logger",
    "HaarFaceDetector",
    "BBox",
    "FaceRGB",
    "FaceNetEmbedder",
    "EmbeddingStore",
    "FaceRecogniser",
    "RecognitionResult",
    "DBManager",
]
