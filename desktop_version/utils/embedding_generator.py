"""
utils/embedding_generator.py
───────────────────────────────────────────────────────────────────────────────
FaceNet Embedding Generator using facenet-pytorch's InceptionResnetV1.

What is a FaceNet Embedding?
─────────────────────────────
FaceNet maps a 160×160 face image → a 512-dimensional L2-normalised vector.
Faces of the SAME person cluster close together in this 512-D space.
Faces of DIFFERENT people are far apart.

We exploit this property directly using cosine similarity — NO classifier needed.

Architecture: InceptionResnetV1
 Input  : (B, 3, 160, 160) float32 tensor, pixel values in [-1, 1]
 Output : (B, 512) L2-normalised embedding vector

Pre-trained on:
  'vggface2'       – ~3.3 M images, 9131 identities  (recommended)
  'casia-webface'  – ~494 K images, 10575 identities
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import numpy as np
import torch
from PIL import Image
from torchvision import transforms
from typing import List, Union

from utils.logger import get_logger
from utils.config import Config

log = get_logger(__name__)


# ── Image pre-processing pipeline (matches FaceNet training) ─────────────────
#   1. Resize to 160×160  (should already be done by face_detector, but safe)
#   2. ToTensor → [0, 1] float
#   3. Normalize → [-1, 1] using mean=0.5, std=0.5
_TRANSFORM = transforms.Compose([
    transforms.Resize((Config.FACENET_IMAGE_SIZE, Config.FACENET_IMAGE_SIZE)),
    transforms.ToTensor(),                          # HWC uint8 → CHW float [0,1]
    transforms.Normalize(mean=[0.5, 0.5, 0.5],
                         std=[0.5, 0.5, 0.5]),      # → [-1, 1]
])


class FaceNetEmbedder:
    """
    Wraps InceptionResnetV1 (FaceNet) for producing 512-D face embeddings.

    Parameters
    ----------
    pretrained : str    – 'vggface2' or 'casia-webface'
    device     : str    – 'cuda' | 'cpu' | 'auto'
    """

    def __init__(
        self,
        pretrained: str = Config.FACENET_PRETRAINED,
        device:     str = "auto",
    ) -> None:
        # ── Device selection ──────────────────────────────────────────────
        if device == "auto":
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        log.info(f"FaceNetEmbedder initialising on device: {self.device}")

        # ── Load FaceNet model ────────────────────────────────────────────
        try:
            from facenet_pytorch import InceptionResnetV1  # type: ignore
        except ImportError:
            raise ImportError(
                "facenet-pytorch is not installed.\n"
                "Run:  pip install facenet-pytorch"
            )

        self.model = InceptionResnetV1(pretrained=pretrained).eval().to(self.device)
        log.info(f"InceptionResnetV1 loaded with '{pretrained}' weights.")

    # ── Single image → embedding ──────────────────────────────────────────────
    def get_embedding(self, face_rgb: np.ndarray) -> np.ndarray:
        """
        Generate a 512-D embedding for one face.

        Parameters
        ----------
        face_rgb : np.ndarray  shape (160, 160, 3) uint8, RGB order.

        Returns
        -------
        np.ndarray  shape (512,)  – L2-normalised embedding.
        """
        tensor = self._preprocess_single(face_rgb)           # (1, 3, 160, 160)
        with torch.no_grad():
            embedding = self.model(tensor)                    # (1, 512)
        return embedding.squeeze(0).cpu().numpy()             # (512,)

    # ── Batch images → embeddings ─────────────────────────────────────────────
    def get_embeddings_batch(
        self,
        faces_rgb: List[np.ndarray],
        batch_size: int = 32,
    ) -> np.ndarray:
        """
        Generate embeddings for a list of face images efficiently.

        Parameters
        ----------
        faces_rgb  : List of (160,160,3) uint8 RGB arrays.
        batch_size : Process this many images per forward pass.

        Returns
        -------
        np.ndarray  shape (N, 512)
        """
        if not faces_rgb:
            return np.empty((0, Config.EMBEDDING_DIM), dtype=np.float32)

        all_embeddings = []
        for i in range(0, len(faces_rgb), batch_size):
            batch = faces_rgb[i : i + batch_size]
            tensors = torch.stack([
                self._preprocess_single(f).squeeze(0) for f in batch
            ]).to(self.device)                                # (B, 3, 160, 160)

            with torch.no_grad():
                embs = self.model(tensors)                    # (B, 512)
            all_embeddings.append(embs.cpu().numpy())

        return np.vstack(all_embeddings)                      # (N, 512)

    # ── Internal helpers ──────────────────────────────────────────────────────
    def _preprocess_single(self, face_rgb: np.ndarray) -> torch.Tensor:
        """
        Convert a (H, W, 3) uint8 RGB array → (1, 3, 160, 160) float32 tensor.
        """
        pil_img = Image.fromarray(face_rgb.astype(np.uint8))
        tensor  = _TRANSFORM(pil_img).unsqueeze(0).to(self.device)
        return tensor

    @staticmethod
    def l2_normalise(embeddings: np.ndarray) -> np.ndarray:
        """
        L2-normalise a (N, D) or (D,) embedding array.

        FaceNet already returns unit-normalised vectors, but this is useful
        for re-normalising after averaging multiple embeddings.
        """
        if embeddings.ndim == 1:
            norm = np.linalg.norm(embeddings)
            return embeddings / (norm + 1e-10)
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        return embeddings / (norms + 1e-10)
