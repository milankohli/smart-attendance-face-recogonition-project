"""
app/ml/embedding_generator.py
───────────────────────────────────────────────────────────────────────────────
FaceNet embedding generator using facenet-pytorch's InceptionResnetV1.

Mirrors the desktop application's utils/embeddings.py. Key differences:
  • Singleton pattern with lazy model loading (model is loaded on first call
    to `generate`, not at import time) to keep startup fast and avoid
    GPU allocation in worker processes that don't need it.
  • Thread-safe model loading via threading.Lock.
  • Returns plain Python `list[float]` (EMBEDDING_DIM=512 values) so the
    result can be stored directly in the pgvector column without extra
    conversion in the repository layer.
  • Batch support via `generate_batch` for efficiency during registration
    (avoids loading the model N times for N frames).

The model weights are downloaded from PyTorch Hub on first use and cached
in `~/.cache/torch/hub/` (or TORCH_HOME if set). In production, pre-bake
the weights into the Docker image to avoid runtime downloads.

GPU / CPU selection:
  • Uses CUDA if available and `force_cpu=False` (the default).
  • Falls back to CPU automatically if CUDA is unavailable.
  • Can be forced to CPU via `EmbeddingGenerator(force_cpu=True)` or by
    setting the environment variable FORCE_CPU_INFERENCE=1.
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import os
import threading
from typing import Optional

import numpy as np
import torch
from facenet_pytorch import InceptionResnetV1
from PIL import Image
from torchvision import transforms

from app.core.logging import get_logger
from app.models.embedding import EMBEDDING_DIM

log = get_logger(__name__)

# Pre-processing pipeline that matches InceptionResnetV1's training transform:
#   • Resize to 160×160 (FaceDetector already does this, kept here for safety)
#   • Convert to float32 and scale to [-1, 1]
_PREPROCESS = transforms.Compose(
    [
        transforms.Resize((160, 160)),
        transforms.ToTensor(),            # HWC uint8 → CHW float32 in [0,1]
        transforms.Normalize(             # → [-1, 1], matching facenet-pytorch norms
            mean=[0.5, 0.5, 0.5],
            std=[0.5, 0.5, 0.5],
        ),
    ]
)


class EmbeddingGenerator:
    """
    Generates L2-normalised 512-D face embeddings using FaceNet
    (InceptionResnetV1 pretrained on `vggface2`).

    Thread-safe lazy loading: the PyTorch model is loaded on the first call
    to `generate` or `generate_batch`, then reused for all subsequent calls.

    Usage:
        generator = EmbeddingGenerator()
        embedding: list[float] = generator.generate(face_crop_bgr)
    """

    def __init__(
        self,
        *,
        pretrained: str = "vggface2",
        force_cpu: bool = False,
    ) -> None:
        """
        Args:
            pretrained: FaceNet weights variant — "vggface2" (general faces)
                        or "casia-webface". "vggface2" gives better accuracy
                        on diverse demographics and matches the desktop app.
            force_cpu:  If True, always use CPU even when CUDA is available.
                        Also honoured via the FORCE_CPU_INFERENCE env var.
        """
        self._pretrained = pretrained
        self._force_cpu = force_cpu or bool(int(os.getenv("FORCE_CPU_INFERENCE", "0")))
        self._device: torch.device | None = None
        self._model: InceptionResnetV1 | None = None
        self._lock = threading.Lock()

    # ── Public API ─────────────────────────────────────────────────────────

    def generate(self, face_crop: np.ndarray) -> list[float]:
        """
        Generate a 512-D L2-normalised embedding for a single face crop.

        Args:
            face_crop: BGR numpy array, ideally 160×160 (the size output by
                       FaceDetector). Will be resized if different.

        Returns:
            A list of 512 float values representing the face in embedding
            space. L2-normalised, so ||embedding|| ≈ 1.0.
        """
        model, device = self._load_model()
        tensor = self._preprocess_frame(face_crop, device)  # (1, 3, 160, 160)

        with torch.no_grad():
            embedding: torch.Tensor = model(tensor)  # (1, 512)

        vector = embedding.squeeze(0).cpu().numpy()  # (512,)
        return vector.tolist()

    def generate_batch(self, face_crops: list[np.ndarray]) -> list[list[float]]:
        """
        Generate embeddings for a list of face crops in a single forward pass.

        Significantly faster than calling `generate` in a loop for large
        batches (e.g. during bulk registration from a video clip).

        Args:
            face_crops: List of BGR numpy arrays (each ideally 160×160).

        Returns:
            List of 512-D float lists, one per input frame, in the same order.
        """
        if not face_crops:
            return []

        model, device = self._load_model()
        tensors = torch.stack(
            [self._preprocess_frame(c, device).squeeze(0) for c in face_crops]
        )  # (N, 3, 160, 160)

        with torch.no_grad():
            embeddings: torch.Tensor = model(tensors)  # (N, 512)

        return [embeddings[i].cpu().numpy().tolist() for i in range(embeddings.shape[0])]

    @property
    def embedding_dim(self) -> int:
        """Return the embedding dimension (always 512 for InceptionResnetV1)."""
        return EMBEDDING_DIM

    @property
    def device(self) -> torch.device:
        """Return the torch device in use (cuda or cpu), loading model if needed."""
        _, dev = self._load_model()
        return dev

    # ── Internals ──────────────────────────────────────────────────────────

    def _load_model(self) -> tuple[InceptionResnetV1, torch.device]:
        """
        Lazy-load the FaceNet model with thread-safe double-checked locking.

        Returns:
            Tuple of (model, device) ready for inference.
        """
        if self._model is not None:
            return self._model, self._device  # type: ignore[return-value]

        with self._lock:
            if self._model is None:  # re-check inside lock
                device = self._select_device()
                log.info(
                    "Loading FaceNet InceptionResnetV1",
                    extra={"ctx_pretrained": self._pretrained, "ctx_device": str(device)},
                )
                model = (
                    InceptionResnetV1(pretrained=self._pretrained)
                    .eval()
                    .to(device)
                )
                self._model = model
                self._device = device
                log.info(
                    "FaceNet model loaded",
                    extra={"ctx_device": str(device), "ctx_pretrained": self._pretrained},
                )

        return self._model, self._device  # type: ignore[return-value]

    def _select_device(self) -> torch.device:
        """Pick the best available compute device."""
        if not self._force_cpu and torch.cuda.is_available():
            device = torch.device("cuda")
            log.info("Using CUDA for inference", extra={"ctx_device": str(device)})
        else:
            device = torch.device("cpu")
            if not self._force_cpu:
                log.info("CUDA unavailable — falling back to CPU")
        return device

    @staticmethod
    def _preprocess_frame(bgr_frame: np.ndarray, device: torch.device) -> torch.Tensor:
        """
        Convert a BGR numpy array to a normalised RGB tensor on `device`.

        Steps:
          1. BGR → RGB (OpenCV stores in BGR by default).
          2. numpy → PIL Image (required by torchvision transforms).
          3. Apply _PREPROCESS (resize, ToTensor, Normalize).
          4. Add batch dimension: (3, 160, 160) → (1, 3, 160, 160).
          5. Move to target device.
        """
        # BGR → RGB
        rgb = bgr_frame[:, :, ::-1].copy()  # copy to make contiguous after flip
        pil_image = Image.fromarray(rgb.astype(np.uint8))
        tensor = _PREPROCESS(pil_image)  # (3, 160, 160)
        return tensor.unsqueeze(0).to(device)  # (1, 3, 160, 160)
