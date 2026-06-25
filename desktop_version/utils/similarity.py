"""
utils/similarity.py
───────────────────────────────────────────────────────────────────────────────
Cosine Similarity–based Face Recognition Engine.

Why Cosine Similarity (not Euclidean distance)?
────────────────────────────────────────────────
FaceNet outputs L2-normalised vectors.  For unit vectors:
    cosine_similarity(a, b) = dot(a, b)

Cosine similarity is invariant to vector magnitude (relevant when we average
multiple embeddings per person), and empirically more stable than Euclidean
distance for comparing face embeddings.

Decision Logic
──────────────
1. Compute cosine similarity between the query embedding and EVERY stored
   mean embedding.
2. Pick the argmax (best match).
3. If max_similarity >= COSINE_THRESHOLD  → recognised person
   Else                                   → "Unknown"

CHANGELOG
─────────
v2 — Added confidence_band field to RecognitionResult.
     Added top_k parameter to recognise() / batch_recognise().
     all_scores now capped to RECOGNITION_TOP_K by default.
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from utils.config import Config
from utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class RecognitionResult:
    """
    Result object returned by FaceRecogniser.recognise().

    Fields
    ──────
    name            : Predicted identity (or "Unknown")
    similarity      : Best cosine similarity score [0, 1]
    is_known        : True if similarity >= threshold
    threshold       : Threshold used for decision
    all_scores      : Top-K [(name, score), ...] sorted descending
    confidence_band : "high" (≥0.85) | "medium" (≥threshold) | "low" (<threshold)
                      Useful for colour-coding the overlay and logging.
    """
    name:            str
    similarity:      float
    is_known:        bool
    threshold:       float
    all_scores:      List[Tuple[str, float]]
    confidence_band: str = field(default="low")


class FaceRecogniser:
    """
    Pure cosine-similarity face recogniser.  No classifier, no SVM, no KNN.

    Parameters
    ----------
    threshold : float
        Minimum cosine similarity to accept a match.  Default from Config.
    """

    def __init__(self, threshold: float = Config.COSINE_THRESHOLD) -> None:
        self.threshold = threshold
        log.info(f"FaceRecogniser initialised (cosine threshold={threshold:.2f})")

    def recognise(
        self,
        query_embedding:      np.ndarray,
        reference_embeddings: np.ndarray,
        reference_names:      List[str],
        top_k:                int = Config.RECOGNITION_TOP_K,
    ) -> RecognitionResult:
        """
        Identify a person by comparing their embedding against all references.

        Parameters
        ----------
        query_embedding      : shape (512,) – embedding of the detected face.
        reference_embeddings : shape (P, 512) – one mean embedding per person.
        reference_names      : List[str] length P – name for each row.
        top_k                : Number of candidates to include in all_scores.

        Returns
        -------
        RecognitionResult
        """
        if len(reference_names) == 0:
            log.warning("Reference database is empty — cannot recognise anyone.")
            return RecognitionResult(
                name="Unknown", similarity=0.0, is_known=False,
                threshold=self.threshold, all_scores=[],
                confidence_band="low",
            )

        # ── L2-normalise the query (should already be normalised by FaceNet) ─
        q = query_embedding.flatten()
        q = q / (np.linalg.norm(q) + 1e-10)

        # ── Ensure reference matrix is L2-normalised ──────────────────────
        norms = np.linalg.norm(reference_embeddings, axis=1, keepdims=True)
        ref   = reference_embeddings / (norms + 1e-10)

        # ── Vectorised cosine similarity: dot(q, ref.T) ───────────────────
        # Shape: (P,)  — one score per person
        similarities: np.ndarray = ref @ q   # equivalent to cosine_sim for unit vecs

        # ── Build ranked top-K score list ──────────────────────────────────
        ranked_idx = np.argsort(similarities)[::-1]
        all_scores = [
            (reference_names[i], float(similarities[i]))
            for i in ranked_idx[:top_k]
        ]

        best_idx   = int(ranked_idx[0])
        best_score = float(similarities[best_idx])
        best_name  = reference_names[best_idx]

        is_known   = best_score >= self.threshold
        label      = best_name if is_known else "Unknown"

        # ── Confidence band ───────────────────────────────────────────────
        if best_score >= 0.85:
            confidence_band = "high"
        elif is_known:
            confidence_band = "medium"
        else:
            confidence_band = "low"

        log.debug(
            f"Top match: '{best_name}'  score={best_score:.4f}  "
            f"band={confidence_band}  "
            f"{'✓ KNOWN' if is_known else '✗ UNKNOWN'}"
        )

        return RecognitionResult(
            name            = label,
            similarity      = best_score,
            is_known        = is_known,
            threshold       = self.threshold,
            all_scores      = all_scores,
            confidence_band = confidence_band,
        )

    def batch_recognise(
        self,
        query_embeddings:     np.ndarray,
        reference_embeddings: np.ndarray,
        reference_names:      List[str],
        top_k:                int = Config.RECOGNITION_TOP_K,
    ) -> List[RecognitionResult]:
        """
        Recognise multiple faces in one call.

        Parameters
        ----------
        query_embeddings : shape (Q, 512)
        top_k            : Candidates to include in each result's all_scores.

        Returns
        -------
        List of RecognitionResult, length Q.
        """
        return [
            self.recognise(query_embeddings[i], reference_embeddings,
                           reference_names, top_k=top_k)
            for i in range(len(query_embeddings))
        ]

    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Utility: scalar cosine similarity between two 1-D vectors."""
        a = a.flatten()
        b = b.flatten()
        denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-10
        return float(np.dot(a, b) / denom)
