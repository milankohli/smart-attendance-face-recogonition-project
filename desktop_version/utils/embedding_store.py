"""
utils/embedding_store.py
───────────────────────────────────────────────────────────────────────────────
Persistent storage layer for FaceNet embeddings and identity labels.

Storage Format
──────────────
embeddings/face_embeddings.pkl  – np.ndarray  shape (N, 512)
embeddings/labels.pkl           – List[str]   length N
embeddings/metadata.json        – Dict        {name: {count, registered_at}}

The two .pkl files are parallel arrays:
  face_embeddings[i]  ↔  labels[i]

When we add a new person we APPEND to both arrays.
When we delete a person we filter both arrays by label.

Why not SQLite for embeddings?
──────────────────────────────
Cosine similarity requires vectorised NumPy operations over the full embedding
matrix.  Keeping the matrix in a contiguous NumPy array and memory-mapping it
via pickle is faster than fetching rows from SQLite for O(100–1000) identities.
For >10 000 identities consider FAISS instead.
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import pickle
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from utils.config import Config
from utils.logger import get_logger

log = get_logger(__name__)


class EmbeddingStore:
    """
    CRUD interface for the face embedding database.

    Attributes (in-memory mirrors of the pickle files)
    ──────────────────────────────────────────────────
    embeddings : np.ndarray  shape (N, 512)
    labels     : List[str]   length N
    metadata   : dict        {name: {"count": int, "registered_at": str}}
    """

    def __init__(self) -> None:
        Config.ensure_dirs()
        self._emb_path  = Config.EMBEDDINGS_FILE
        self._lbl_path  = Config.LABELS_FILE
        self._meta_path = Config.METADATA_FILE

        self.embeddings: np.ndarray = np.empty((0, Config.EMBEDDING_DIM), dtype=np.float32)
        self.labels:     List[str]  = []
        self.metadata:   Dict       = {}

        self._load()

    # ── Persistence ───────────────────────────────────────────────────────────
    def _load(self) -> None:
        """Load embeddings + labels + metadata from disk (if they exist)."""
        loaded_emb = False
        if self._emb_path.exists() and self._lbl_path.exists():
            try:
                with open(self._emb_path, "rb") as f:
                    self.embeddings = pickle.load(f)
                with open(self._lbl_path, "rb") as f:
                    self.labels = pickle.load(f)
                log.info(
                    f"Loaded {len(self.labels)} embedding(s) for "
                    f"{len(set(self.labels))} identity/identities."
                )
                loaded_emb = True
            except (pickle.UnpicklingError, EOFError, Exception) as exc:
                log.error(f"Corrupt embedding files — resetting store. ({exc})")
                self.embeddings = np.empty((0, Config.EMBEDDING_DIM), dtype=np.float32)
                self.labels     = []

        if self._meta_path.exists():
            try:
                with open(self._meta_path, "r", encoding="utf-8") as f:
                    self.metadata = json.load(f)
            except json.JSONDecodeError:
                self.metadata = {}

        if not loaded_emb:
            log.info("No existing embeddings found — starting fresh store.")

    def save(self) -> None:
        """Persist in-memory state to disk (atomic write via temp file)."""
        # ── Embeddings ────────────────────────────────────────────────────
        tmp_emb = self._emb_path.with_suffix(".pkl.tmp")
        with open(tmp_emb, "wb") as f:
            pickle.dump(self.embeddings, f, protocol=pickle.HIGHEST_PROTOCOL)
        tmp_emb.replace(self._emb_path)

        # ── Labels ────────────────────────────────────────────────────────
        tmp_lbl = self._lbl_path.with_suffix(".pkl.tmp")
        with open(tmp_lbl, "wb") as f:
            pickle.dump(self.labels, f, protocol=pickle.HIGHEST_PROTOCOL)
        tmp_lbl.replace(self._lbl_path)

        # ── Metadata ──────────────────────────────────────────────────────
        with open(self._meta_path, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, indent=2, ensure_ascii=False)

        log.info(f"Saved {len(self.labels)} embedding(s) to disk.")

    # ── Write operations ──────────────────────────────────────────────────────
    def add_person(self, name: str, embeddings: np.ndarray) -> int:
        """
        Append one or more embeddings for `name`.

        Parameters
        ----------
        name       : Person's display name (e.g. "Alice Smith").
        embeddings : np.ndarray  shape (K, 512) where K ≥ 1.

        Returns
        -------
        int – total number of embeddings now stored for this person.
        """
        if embeddings.ndim == 1:
            embeddings = embeddings[np.newaxis, :]   # (512,) → (1, 512)

        if embeddings.shape[1] != Config.EMBEDDING_DIM:
            raise ValueError(
                f"Expected embedding dim {Config.EMBEDDING_DIM}, "
                f"got {embeddings.shape[1]}"
            )

        # ── Append to parallel arrays ─────────────────────────────────────
        self.embeddings = (
            embeddings
            if len(self.labels) == 0
            else np.vstack([self.embeddings, embeddings])
        )
        self.labels.extend([name] * len(embeddings))

        # ── Update metadata ───────────────────────────────────────────────
        if name not in self.metadata:
            self.metadata[name] = {
                "count":         len(embeddings),
                "registered_at": datetime.now().isoformat(timespec="seconds"),
                "updated_at":    datetime.now().isoformat(timespec="seconds"),
            }
        else:
            self.metadata[name]["count"]      += len(embeddings)
            self.metadata[name]["updated_at"]  = datetime.now().isoformat(timespec="seconds")

        total = self.metadata[name]["count"]
        log.info(f"Added {len(embeddings)} embedding(s) for '{name}' (total: {total}).")
        self.save()
        return total

    def remove_person(self, name: str) -> bool:
        """
        Remove ALL embeddings for `name`.

        Returns True if person was found and removed, False otherwise.
        """
        mask = np.array([lbl != name for lbl in self.labels])
        if mask.all():
            log.warning(f"Person '{name}' not found in store.")
            return False

        self.embeddings = self.embeddings[mask] if mask.any() else np.empty(
            (0, Config.EMBEDDING_DIM), dtype=np.float32
        )
        self.labels     = [lbl for lbl in self.labels if lbl != name]
        self.metadata.pop(name, None)
        log.info(f"Removed all embeddings for '{name}'.")
        self.save()
        return True

    # ── Read operations ───────────────────────────────────────────────────────
    def get_embeddings_for(self, name: str) -> np.ndarray:
        """Return all stored embeddings for `name` as shape (K, 512)."""
        idxs = [i for i, lbl in enumerate(self.labels) if lbl == name]
        if not idxs:
            return np.empty((0, Config.EMBEDDING_DIM), dtype=np.float32)
        return self.embeddings[idxs]

    def get_mean_embeddings(self) -> Tuple[np.ndarray, List[str]]:
        """
        Compute one representative (mean + L2-normalised) embedding per person.

        Returns
        -------
        mean_embs : np.ndarray  shape (P, 512)  – one row per unique person
        names     : List[str]   length P
        """
        unique_names = list(dict.fromkeys(self.labels))  # preserve insertion order
        means, names = [], []
        for name in unique_names:
            person_embs = self.get_embeddings_for(name)   # (K, 512)
            mean_emb    = person_embs.mean(axis=0)         # (512,)
            norm        = np.linalg.norm(mean_emb)
            mean_emb    = mean_emb / (norm + 1e-10)        # L2 normalise
            means.append(mean_emb)
            names.append(name)

        if not means:
            return np.empty((0, Config.EMBEDDING_DIM), dtype=np.float32), []

        return np.vstack(means), names                    # (P, 512), [P]

    def list_people(self) -> List[str]:
        """Return sorted list of registered names."""
        return sorted(set(self.labels))

    def is_empty(self) -> bool:
        return len(self.labels) == 0

    def __len__(self) -> int:
        return len(self.labels)

    def __repr__(self) -> str:
        people = self.list_people()
        return (
            f"<EmbeddingStore: {len(people)} person(s), "
            f"{len(self.labels)} total embedding(s)>"
        )
