"""
app/ml/face_detector.py
───────────────────────────────────────────────────────────────────────────────
Haar Cascade face detection wrapper.

Mirrors the desktop application's utils/detection.py. The core
responsibility is identical:
  1. Convert the incoming BGR frame to greyscale.
  2. Run OpenCV's Haar Cascade (`haarcascade_frontalface_default.xml`)
     to locate face bounding boxes.
  3. Select the largest detected face (most likely to be the target person
     when multiple faces appear in frame).
  4. Crop and return the aligned face region, resized to the dimensions
     expected by FaceNet (160×160 by default).

Changes from the desktop version:
  • Stateless class rather than module-level functions, enabling
    dependency injection and easy test mocking.
  • `detect_and_crop` returns `None` when no face is found instead of
    raising, keeping error handling at the service layer.
  • `detect_all` returns bounding boxes for all detected faces (useful
    for multi-face frames in analytics / crowd counting extensions).
  • The cascade XML path falls back to OpenCV's bundled data directory
    automatically — no need to configure a path in settings.

FaceNet input size:
  The facenet-pytorch InceptionResnetV1 expects 160×160 RGB tensors.
  `detect_and_crop` resizes to (face_size, face_size) which defaults
  to 160 — the service layer MUST NOT resize again before passing the
  crop to EmbeddingGenerator.
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from app.core.logging import get_logger

log = get_logger(__name__)

# Bounding box type alias: (x, y, width, height)
BoundingBox = tuple[int, int, int, int]

# FaceNet's expected input size
_DEFAULT_FACE_SIZE = 160

# Scale factors for the Haar Cascade detector (mirrors desktop app defaults)
_SCALE_FACTOR = 1.1
_MIN_NEIGHBOURS = 5
_MIN_FACE_PX = 30  # ignore detections smaller than 30×30 px


@dataclass
class DetectionResult:
    """Metadata for one detected face region."""
    bbox: BoundingBox        # (x, y, w, h) in the original frame
    crop: np.ndarray         # resized face crop (face_size × face_size, BGR)
    area: int                # w * h in original frame pixels


class FaceDetector:
    """
    OpenCV Haar Cascade face detector with crop/resize pipeline.

    Usage:
        detector = FaceDetector()
        crop = detector.detect_and_crop(frame)  # None if no face found
        if crop is not None:
            # pass crop to EmbeddingGenerator
    """

    def __init__(
        self,
        *,
        cascade_path: str | None = None,
        face_size: int = _DEFAULT_FACE_SIZE,
        scale_factor: float = _SCALE_FACTOR,
        min_neighbours: int = _MIN_NEIGHBOURS,
        min_size: tuple[int, int] = (_MIN_FACE_PX, _MIN_FACE_PX),
    ) -> None:
        """
        Args:
            cascade_path:   Absolute path to the Haar XML file. Defaults to
                            OpenCV's bundled `haarcascade_frontalface_default.xml`.
            face_size:      Output size (square) for cropped face images.
                            Must match EmbeddingGenerator's expected input.
            scale_factor:   detectMultiScale scale factor. Higher = faster
                            but may miss smaller faces.
            min_neighbours: detectMultiScale min neighbours. Higher = stricter
                            (fewer false positives but may miss faces).
            min_size:       Minimum face size in pixels to consider.
        """
        if cascade_path is None:
            # Use OpenCV's bundled Haar cascade data
            cascade_path = os.path.join(
                cv2.data.haarcascades,
                "haarcascade_frontalface_default.xml",
            )

        self._cascade = cv2.CascadeClassifier(cascade_path)
        if self._cascade.empty():
            raise RuntimeError(
                f"Failed to load Haar Cascade from '{cascade_path}'. "
                "Check that OpenCV is installed correctly."
            )

        self._face_size = face_size
        self._scale_factor = scale_factor
        self._min_neighbours = min_neighbours
        self._min_size = min_size

        log.info(
            "FaceDetector initialised",
            extra={
                "ctx_cascade_path": cascade_path,
                "ctx_face_size": face_size,
                "ctx_scale_factor": scale_factor,
            },
        )

    # ── Public API ─────────────────────────────────────────────────────────

    def detect_and_crop(self, frame: np.ndarray) -> np.ndarray | None:
        """
        Detect the largest face in `frame` and return a resized crop.

        Args:
            frame: BGR image array (as returned by cv2.VideoCapture.read()).

        Returns:
            A (face_size × face_size × 3) BGR numpy array, or None if no
            face was detected.
        """
        results = self._detect_all_internal(frame)
        if not results:
            return None

        # Select the largest face by area (most likely to be the target)
        best = max(results, key=lambda r: r.area)
        return best.crop

    def detect_all(self, frame: np.ndarray) -> list[DetectionResult]:
        """
        Return detection results for ALL faces found in the frame.

        Useful for multi-face analytics / head-count extensions.
        Each result contains the bounding box, the resized crop, and the
        area of the detection in original frame pixels.
        """
        return self._detect_all_internal(frame)

    def detect_bboxes(self, frame: np.ndarray) -> list[BoundingBox]:
        """
        Return raw bounding boxes (x, y, w, h) for all detected faces.

        Useful when the caller needs to draw rectangles on the frame
        (e.g. live preview overlay) without generating crops.
        """
        gray = self._to_gray(frame)
        detections = self._cascade.detectMultiScale(
            gray,
            scaleFactor=self._scale_factor,
            minNeighbors=self._min_neighbours,
            minSize=self._min_size,
        )
        if len(detections) == 0:
            return []
        return [(int(x), int(y), int(w), int(h)) for x, y, w, h in detections]

    # ── Helpers ────────────────────────────────────────────────────────────

    def _detect_all_internal(self, frame: np.ndarray) -> list[DetectionResult]:
        """Run detection and return DetectionResult objects for each face."""
        gray = self._to_gray(frame)
        detections = self._cascade.detectMultiScale(
            gray,
            scaleFactor=self._scale_factor,
            minNeighbors=self._min_neighbours,
            minSize=self._min_size,
        )

        if len(detections) == 0:
            return []

        results: list[DetectionResult] = []
        h_frame, w_frame = frame.shape[:2]

        for x, y, w, h in detections:
            # Clamp bounding box to frame boundaries
            x1 = max(0, int(x))
            y1 = max(0, int(y))
            x2 = min(w_frame, int(x + w))
            y2 = min(h_frame, int(y + h))

            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                continue  # degenerate box — skip

            resized = cv2.resize(crop, (self._face_size, self._face_size))
            results.append(
                DetectionResult(
                    bbox=(x1, y1, x2 - x1, y2 - y1),
                    crop=resized,
                    area=(x2 - x1) * (y2 - y1),
                )
            )

        return results

    @staticmethod
    def _to_gray(frame: np.ndarray) -> np.ndarray:
        """Convert BGR → greyscale for the Cascade detector."""
        if frame.ndim == 2:
            return frame  # already greyscale
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
