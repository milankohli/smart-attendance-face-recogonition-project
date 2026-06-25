"""
app/ml/similarity.py
───────────────────────────────────────────────────────────────────────────────
Cosine similarity evaluation and confidence-band classification.

Mirrors the desktop application's utils/similarity.py (FaceRecogniser,
RecognitionResult, confidence_band logic) but separated from the database
query (which is handled by EmbeddingRepository.find_nearest) to keep this
module pure and easily testable without a database.

Provides:
  • SimilarityThresholds   — dataclass holding the recognition threshold and
                             band boundaries (configurable at injection time)
  • EvaluationResult       — outcome of a single similarity evaluation
  • SimilarityService      — evaluates a similarity score against thresholds
                             and classifies it into a ConfidenceBand
  • cosine_similarity()    — pure-function cosine similarity between two
                             numpy vectors (used in unit tests and when the
                             database is unavailable)

Architecture note:
  The actual nearest-neighbour search is performed at the database level by
  pgvector (via EmbeddingRepository.find_nearest) using the `<=>` cosine-
  distance operator. SimilarityService only evaluates the resulting score —
  it does NOT recompute similarity in Python for the recognition pipeline.
  The `cosine_similarity` function is provided for registration-time
  deduplication checks and offline testing.
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.core.logging import get_logger
from app.models.attendance import ConfidenceBand

log = get_logger(__name__)


@dataclass(frozen=True)
class SimilarityThresholds:
    """
    Configurable threshold values for face recognition.

    Mirrors the desktop app's Config class:
      SIMILARITY_THRESHOLD     → recognition
      HIGH_CONFIDENCE_THRESHOLD → high
      MEDIUM_CONFIDENCE_THRESHOLD → medium

    Defaults reproduce the desktop application's values.
    All values are cosine similarities in [0, 1].
    """

    # Below this → UNKNOWN (face not recognised)
    recognition: float = 0.70

    # >= this → "high" confidence band
    high: float = 0.85

    # >= recognition and < high → "medium" confidence band
    # < recognition → "low" confidence band (recognition rejected)
    medium: float = 0.70  # same as recognition threshold floor

    def __post_init__(self) -> None:
        if not (0.0 <= self.recognition <= 1.0):
            raise ValueError(f"recognition threshold must be in [0, 1], got {self.recognition}")
        if not (0.0 <= self.high <= 1.0):
            raise ValueError(f"high threshold must be in [0, 1], got {self.high}")
        if self.high < self.recognition:
            raise ValueError(
                f"high threshold ({self.high}) must be >= recognition threshold ({self.recognition})"
            )


@dataclass
class EvaluationResult:
    """
    Outcome of evaluating a similarity score against the thresholds.

    Attributes:
        similarity:      The raw cosine similarity score (from pgvector or
                         the `cosine_similarity` function).
        above_threshold: True if the score meets the recognition threshold.
        confidence_band: 'high', 'medium', or 'low'.
        label:           Human-readable outcome label.
    """

    similarity: float
    above_threshold: bool
    confidence_band: ConfidenceBand
    label: str


class SimilarityService:
    """
    Evaluates a cosine similarity score against configurable thresholds and
    returns a structured EvaluationResult.

    Designed for dependency injection:
        svc = SimilarityService(thresholds=SimilarityThresholds(recognition=0.75))
        result = svc.evaluate(0.82)
        # result.above_threshold == True, result.confidence_band == ConfidenceBand.MEDIUM

    Usage in AttendanceService:
        # EmbeddingRepository.find_nearest returns (embedding, similarity)
        best_similarity = matches[0].similarity
        result = similarity_service.evaluate(best_similarity)
        if result.above_threshold:
            # mark attendance
    """

    def __init__(
        self,
        *,
        thresholds: SimilarityThresholds | None = None,
    ) -> None:
        self.thresholds = thresholds or SimilarityThresholds()
        log.info(
            "SimilarityService initialised",
            extra={
                "ctx_recognition_threshold": self.thresholds.recognition,
                "ctx_high_threshold": self.thresholds.high,
            },
        )

    def evaluate(self, similarity: float) -> EvaluationResult:
        """
        Classify a cosine similarity score.

        Args:
            similarity: Cosine similarity in [0, 1]. Typically the value
                        returned by EmbeddingRepository.find_nearest
                        (which converts pgvector's cosine distance via
                        `1 - distance`).

        Returns:
            EvaluationResult with:
              - above_threshold: True if similarity >= recognition threshold
              - confidence_band: ConfidenceBand.HIGH / MEDIUM / LOW
              - label: human-readable outcome string
        """
        t = self.thresholds

        if similarity >= t.high:
            band = ConfidenceBand.HIGH
            above = True
            label = f"High confidence match (similarity={similarity:.3f})"
        elif similarity >= t.recognition:
            band = ConfidenceBand.MEDIUM
            above = True
            label = f"Medium confidence match (similarity={similarity:.3f})"
        else:
            band = ConfidenceBand.LOW
            above = False
            label = (
                f"Below recognition threshold "
                f"(similarity={similarity:.3f} < threshold={t.recognition:.2f})"
            )

        log.debug(
            "Similarity evaluated",
            extra={
                "ctx_similarity": round(similarity, 4),
                "ctx_band": band.value,
                "ctx_above_threshold": above,
            },
        )
        return EvaluationResult(
            similarity=similarity,
            above_threshold=above,
            confidence_band=band,
            label=label,
        )

    def classify_band(self, similarity: float) -> ConfidenceBand:
        """Shortcut returning only the ConfidenceBand (no full EvaluationResult)."""
        return self.evaluate(similarity).confidence_band

    def is_match(self, similarity: float) -> bool:
        """Return True if the similarity meets the recognition threshold."""
        return similarity >= self.thresholds.recognition


# ── Pure utility functions ─────────────────────────────────────────────────


def cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """
    Compute cosine similarity between two 1-D numpy vectors.

    Returns a value in [-1, 1]; for L2-normalised FaceNet embeddings the
    range is effectively [0, 1].

    Used:
      • In offline registration checks (is this face a duplicate of an
        existing student's mean embedding?).
      • In unit tests to verify the pgvector search results match the
        Python reference implementation.
      • As a fallback when pgvector is unavailable (e.g. SQLite in tests).

    Args:
        vec_a: First embedding vector (must be non-zero).
        vec_b: Second embedding vector (must be non-zero).

    Returns:
        Cosine similarity in [0, 1] for normalised FaceNet vectors.

    Raises:
        ValueError: if either vector is all-zeros.
    """
    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)
    if norm_a == 0.0 or norm_b == 0.0:
        raise ValueError("Cannot compute cosine similarity for zero-norm vectors.")
    return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))


def l2_normalize(vec: np.ndarray) -> np.ndarray:
    """
    L2-normalise a vector in place and return it.

    FaceNet produces embeddings that should already be unit vectors;
    this function provides an explicit normalisation step for cases where
    embeddings are averaged (e.g. computing a per-student mean from multiple
    samples) and the result needs to be renormalised before similarity search.
    """
    norm = np.linalg.norm(vec)
    if norm == 0.0:
        return vec
    return vec / norm


def top_k_matches(
    query: np.ndarray,
    candidates: list[tuple[int, np.ndarray]],
    *,
    k: int = 5,
) -> list[tuple[int, float]]:
    """
    Pure-Python nearest-neighbour search over a list of (id, embedding) pairs.

    This is the in-process fallback used in unit tests and the CLI
    registration tool — NOT used in the production web API (which relies on
    pgvector for efficiency).

    Args:
        query:      512-D query embedding (need not be L2-normalised).
        candidates: List of (student_id, embedding_vector) pairs.
        k:          Number of top matches to return.

    Returns:
        List of (student_id, similarity) sorted by similarity descending,
        up to k items.
    """
    q = l2_normalize(query)
    scored = [
        (student_id, cosine_similarity(q, l2_normalize(np.asarray(emb))))
        for student_id, emb in candidates
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:k]
