"""
utils/face_detector.py
───────────────────────────────────────────────────────────────────────────────
Haar Cascade Face Detector — wraps OpenCV's CascadeClassifier with sensible
defaults and production-grade error handling.

Responsibilities
────────────────
1. Load the Haar Cascade XML file (bundled with OpenCV — no download needed).
2. Detect faces in a BGR or grayscale image.
3. Return cropped, resized face regions ready for FaceNet (160×160 RGB).

Why Haar Cascade here?
──────────────────────
FaceNet's MTCNN is more accurate but slower on CPU.  For the *registration*
pipeline (offline, one-time) we use Haar Cascade to keep things fast and
dependency-light.  The live webcam loop also uses Haar for real-time speed.
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import cv2
import numpy as np
from pathlib import Path
from typing import List, Tuple, Optional

from utils.logger import get_logger
from utils.config import Config

log = get_logger(__name__)


# ── Type alias ─────────────────────────────────────────────────────────────────
BBox   = Tuple[int, int, int, int]           # (x, y, w, h)
FaceRGB = np.ndarray                          # shape (160,160,3) uint8


class HaarFaceDetector:
    """
    OpenCV Haar Cascade face detector.

    Parameters
    ----------
    cascade_path : str | None
        Path to the Haar XML file.  If None, the OpenCV built-in path is used.
    scale_factor  : float  – see cv2.CascadeClassifier.detectMultiScale
    min_neighbors : int    – minimum neighbour rectangles to keep a detection
    min_size      : tuple  – (w, h) minimum face size in pixels
    """

    def __init__(
        self,
        cascade_path:  Optional[str] = None,
        scale_factor:  float         = Config.HAAR_SCALE_FACTOR,
        min_neighbors: int           = Config.HAAR_MIN_NEIGHBORS,
        min_size:      Tuple[int,int]= Config.HAAR_MIN_FACE_SIZE,
    ) -> None:
        # ── Resolve cascade path ──────────────────────────────────────────
        if cascade_path is None:
            # OpenCV ships this file; cv2.data.haarcascades is the folder.
            cascade_path = str(
                Path(cv2.data.haarcascades) /
                "haarcascade_frontalface_default.xml"
            )

        if not Path(cascade_path).exists():
            raise FileNotFoundError(
                f"Haar Cascade XML not found at: {cascade_path}\n"
                "Make sure opencv-python is installed correctly."
            )

        self._detector    = cv2.CascadeClassifier(cascade_path)
        self._scale       = scale_factor
        self._min_nbrs    = min_neighbors
        self._min_size    = min_size

        log.info(f"HaarFaceDetector loaded: {cascade_path}")

    # ── Core detection ────────────────────────────────────────────────────────
    def detect_bboxes(self, image_bgr: np.ndarray) -> List[BBox]:
        """
        Detect face bounding boxes in a BGR image.

        Returns a list of (x, y, w, h) tuples sorted by face area (largest first).
        """
        # Convert to grayscale — Haar Cascade works on intensity, not colour
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        # Histogram equalisation improves detection under poor lighting
        gray = cv2.equalizeHist(gray)

        faces = self._detector.detectMultiScale(
            gray,
            scaleFactor  = self._scale,
            minNeighbors = self._min_nbrs,
            minSize      = self._min_size,
            flags        = cv2.CASCADE_SCALE_IMAGE,
        )

        if len(faces) == 0:
            return []

        # Sort by area descending so index-0 is always the most prominent face
        bboxes: List[BBox] = sorted(
            [(x, y, w, h) for (x, y, w, h) in faces],
            key=lambda b: b[2] * b[3],
            reverse=True,
        )
        log.debug(f"Detected {len(bboxes)} face(s)")
        return bboxes

    def detect_and_crop(
        self,
        image_bgr: np.ndarray,
        target_size: int = Config.FACENET_IMAGE_SIZE,
        padding: float   = 0.15,
    ) -> List[FaceRGB]:
        """
        Detect faces, add padding, crop, and resize to `target_size` × `target_size`.

        Parameters
        ----------
        image_bgr   : BGR image as NumPy array (H×W×3 uint8).
        target_size : Output face size (160 for FaceNet).
        padding     : Fractional padding around bounding box (0.15 = 15 %).

        Returns
        -------
        List of RGB face arrays, each shaped (target_size, target_size, 3).
        """
        bboxes = self.detect_bboxes(image_bgr)
        if not bboxes:
            log.warning("No faces detected in image.")
            return []

        h_img, w_img = image_bgr.shape[:2]
        crops: List[FaceRGB] = []

        for (x, y, w, h) in bboxes:
            # ── Add padding ───────────────────────────────────────────────
            pad_w = int(w * padding)
            pad_h = int(h * padding)
            x1 = max(0, x - pad_w)
            y1 = max(0, y - pad_h)
            x2 = min(w_img, x + w + pad_w)
            y2 = min(h_img, y + h + pad_h)

            # ── Crop & resize ─────────────────────────────────────────────
            face_bgr  = image_bgr[y1:y2, x1:x2]
            face_bgr  = cv2.resize(face_bgr, (target_size, target_size),
                                   interpolation=cv2.INTER_LANCZOS4)
            # FaceNet expects RGB, not BGR
            face_rgb  = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)
            crops.append(face_rgb)

        log.info(f"Cropped {len(crops)} face(s) to {target_size}×{target_size}")
        return crops

    def draw_boxes(
        self,
        image_bgr: np.ndarray,
        bboxes:    List[BBox],
        labels:    Optional[List[str]] = None,
        color:     Tuple[int,int,int]  = (0, 255, 0),
    ) -> np.ndarray:
        """
        Draw bounding boxes (and optional labels) on a BGR image.

        Returns a copy of the image with annotations drawn.
        """
        out = image_bgr.copy()
        for idx, (x, y, w, h) in enumerate(bboxes):
            cv2.rectangle(out, (x, y), (x + w, y + h), color, 2)
            if labels and idx < len(labels):
                cv2.putText(
                    out,
                    labels[idx],
                    (x, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    color,
                    2,
                    cv2.LINE_AA,
                )
        return out
