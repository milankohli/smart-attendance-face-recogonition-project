"""
app/ml/__init__.py
───────────────────────────────────────────────────────────────────────────────
Machine-learning layer for face detection, embedding generation, and
cosine-similarity evaluation.

Mirrors the desktop application's utils/ modules:
  • face_detector.py      ← utils/detection.py  (Haar Cascade wrapper)
  • embedding_generator.py ← utils/embeddings.py (FaceNet InceptionResnetV1)
  • similarity.py          ← utils/similarity.py (cosine similarity + thresholds)
───────────────────────────────────────────────────────────────────────────────
"""

from app.ml.face_detector import FaceDetector
from app.ml.embedding_generator import EmbeddingGenerator
from app.ml.similarity import SimilarityService, SimilarityThresholds, EvaluationResult

__all__ = [
    "FaceDetector",
    "EmbeddingGenerator",
    "SimilarityService",
    "SimilarityThresholds",
    "EvaluationResult",
]
