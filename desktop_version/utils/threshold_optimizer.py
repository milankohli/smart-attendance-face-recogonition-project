"""
utils/threshold_optimizer.py
───────────────────────────────────────────────────────────────────────────────
Smart Attendance System — Cosine Threshold Optimizer

PURPOSE
───────
Finding the right cosine similarity threshold is critical:
  • Too low  (e.g. 0.50) → strangers get recognised as known people
  • Too high (e.g. 0.95) → even the registered person is rejected

This module uses the stored embeddings themselves (the only ground-truth data
we have at registration time) to suggest a threshold by computing:

  1. INTRA-PERSON similarities  (same identity, different images)
       → these should all be ABOVE the threshold
  2. INTER-PERSON similarities  (different identities)
       → these should all be BELOW the threshold

The optimal threshold sits in the gap between the two distributions.
We pick: max_intra × (1 - margin) to stay safely below intra-class minimum.

USAGE (programmatic)
────────────────────
    from utils.threshold_optimizer import ThresholdOptimizer
    opt = ThresholdOptimizer()
    result = opt.analyze()
    print(result.suggested_threshold)

USAGE (CLI)
───────────
    python -m utils.threshold_optimizer
    python -m utils.threshold_optimizer --margin 0.05 --plot
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from colorama import init as colorama_init, Fore, Style

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.config          import Config
from utils.embedding_store import EmbeddingStore
from utils.logger          import get_logger

colorama_init(autoreset=True)
log = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ThresholdAnalysis:
    """
    Full statistical analysis of intra-/inter-person similarity distributions.

    Attributes
    ──────────
    intra_stats : per-person {min, max, mean, std} of same-person similarities
    inter_min   : minimum similarity between ANY two different people
                  (a low value = good separation between identities)
    inter_max   : maximum similarity between ANY two different people
                  (a high value = risk zone — these two people look alike)
    gap         : inter_min - intra_max_global  (positive = clean separation)
    suggested_threshold : recommended operating point
    confidence  : "high" | "medium" | "low" based on gap size
    warnings    : list of human-readable warning strings
    """
    intra_stats:          Dict[str, Dict[str, float]]
    intra_min_global:     float
    intra_max_global:     float
    inter_min:            float
    inter_max:            float
    gap:                  float
    suggested_threshold:  float
    confidence:           str
    warnings:             List[str] = field(default_factory=list)
    n_persons:            int = 0
    n_embeddings:         int = 0


# ═══════════════════════════════════════════════════════════════════════════════
# OPTIMIZER CLASS
# ═══════════════════════════════════════════════════════════════════════════════

class ThresholdOptimizer:
    """
    Analyses the embedding store to recommend a cosine similarity threshold.

    Parameters
    ----------
    store  : EmbeddingStore to analyse.  If None, loads the default store.
    margin : Safety margin subtracted from intra-class minimum to set
             the threshold.  E.g. 0.05 means "5 % below the hardest
             same-person pair we've seen".
    """

    def __init__(
        self,
        store:  Optional[EmbeddingStore] = None,
        margin: float                    = 0.05,
    ) -> None:
        self.store  = store or EmbeddingStore()
        self.margin = margin

    # ── Public API ────────────────────────────────────────────────────────────
    def analyze(self) -> ThresholdAnalysis:
        """
        Run the full intra/inter-person similarity analysis.

        Returns a ThresholdAnalysis with a suggested threshold and
        statistical diagnostics.

        Raises
        ------
        ValueError : If fewer than 2 people are registered (inter-person
                     analysis requires at least 2 identities).
        """
        people = self.store.list_people()

        if len(people) < 1:
            raise ValueError("No registered persons found in embedding store.")

        # ── Step 1: Compute mean embeddings (same as live recognition) ────
        mean_embs, names = self.store.get_mean_embeddings()  # (P, 512)

        # ── Step 2: Intra-person similarities ─────────────────────────────
        intra_stats: Dict[str, Dict[str, float]] = {}
        all_intra: List[float] = []

        for name in people:
            person_embs = self.store.get_embeddings_for(name)  # (K, 512)
            k = len(person_embs)

            if k < 2:
                # Only one embedding — cannot compute intra similarity.
                # Use similarity of the single embedding with itself (= 1.0)
                # as a placeholder so we don't crash.
                intra_stats[name] = {
                    "min": 1.0, "max": 1.0, "mean": 1.0, "std": 0.0, "n": k
                }
                continue

            # Normalise
            norms = np.linalg.norm(person_embs, axis=1, keepdims=True)
            normed = person_embs / (norms + 1e-10)

            # All pairwise cosine similarities for this person
            sim_matrix = normed @ normed.T  # (K, K)
            # Extract upper triangle (excluding diagonal self-similarities)
            triu_indices = np.triu_indices(k, k=1)
            pair_sims = sim_matrix[triu_indices]

            intra_stats[name] = {
                "min":  float(pair_sims.min()),
                "max":  float(pair_sims.max()),
                "mean": float(pair_sims.mean()),
                "std":  float(pair_sims.std()),
                "n":    k,
            }
            all_intra.extend(pair_sims.tolist())

        intra_min_global = float(min(all_intra)) if all_intra else 1.0
        intra_max_global = float(max(all_intra)) if all_intra else 1.0

        # ── Step 3: Inter-person similarities ─────────────────────────────
        warnings: List[str] = []
        inter_min = 1.0
        inter_max = 0.0

        if len(people) >= 2:
            p = len(names)
            # Normalise mean embeddings
            norms = np.linalg.norm(mean_embs, axis=1, keepdims=True)
            normed_means = mean_embs / (norms + 1e-10)
            sim_matrix   = normed_means @ normed_means.T  # (P, P)

            triu_idx  = np.triu_indices(p, k=1)
            inter_sim = sim_matrix[triu_idx]

            inter_min = float(inter_sim.min())
            inter_max = float(inter_sim.max())

            # Flag look-alike pairs
            LOOKALIKE_THRESH = 0.70
            for (i, j) in zip(*triu_idx):
                s = sim_matrix[i, j]
                if s >= LOOKALIKE_THRESH:
                    warnings.append(
                        f"⚠ Look-alike pair: '{names[i]}' ↔ '{names[j]}'  "
                        f"(inter-similarity={s:.4f}).  "
                        "Consider registering more diverse photos."
                    )
        else:
            inter_min = 0.0
            inter_max = 0.0
            warnings.append(
                "Only 1 person registered — inter-person analysis skipped. "
                "Register at least 2 people for a meaningful threshold analysis."
            )

        # ── Step 4: Suggest threshold ──────────────────────────────────────
        # Threshold = intra_min − margin
        # Clamped to [0.50, 0.95] to stay in a sane operating range.
        raw_threshold = intra_min_global - self.margin
        suggested     = float(np.clip(raw_threshold, 0.50, 0.95))

        # ── Step 5: Compute separation gap + confidence ────────────────────
        # gap > 0 means the worst same-person pair is still above the best
        # different-person pair → perfect separation.
        gap = inter_min - intra_min_global  # negative = overlap!

        if gap > 0.10:
            confidence = "high"
        elif gap > 0.00:
            confidence = "medium"
        else:
            confidence = "low"
            warnings.append(
                f"Intra/inter distributions OVERLAP (gap={gap:.4f}).  "
                "Some people may be confused with each other at any threshold.  "
                "Register more images with varied lighting and angles."
            )

        # Warn if suggested threshold would reject too many valid faces
        if suggested > 0.85:
            warnings.append(
                f"Suggested threshold ({suggested:.3f}) is very strict.  "
                "This may cause false rejections.  "
                "Consider registering more images per person."
            )

        return ThresholdAnalysis(
            intra_stats         = intra_stats,
            intra_min_global    = intra_min_global,
            intra_max_global    = intra_max_global,
            inter_min           = inter_min,
            inter_max           = inter_max,
            gap                 = gap,
            suggested_threshold = suggested,
            confidence          = confidence,
            warnings            = warnings,
            n_persons           = len(people),
            n_embeddings        = len(self.store),
        )

    def suggest_threshold(self) -> float:
        """
        Quick helper — returns just the float threshold.

        Useful when you only need the number and not the full report.
        """
        return self.analyze().suggested_threshold


# ═══════════════════════════════════════════════════════════════════════════════
# REPORT PRINTER
# ═══════════════════════════════════════════════════════════════════════════════

def print_analysis(result: ThresholdAnalysis) -> None:
    """Pretty-print a ThresholdAnalysis to the terminal."""
    try:
        from tabulate import tabulate
        _has_tabulate = True
    except ImportError:
        _has_tabulate = False

    print(Fore.CYAN + Style.BRIGHT + """
╔══════════════════════════════════════════════════════════════╗
║         THRESHOLD OPTIMIZER — Similarity Analysis            ║
╚══════════════════════════════════════════════════════════════╝
""" + Style.RESET_ALL)

    # ── Overview ──────────────────────────────────────────────────────────
    print(f"  Registered persons : {result.n_persons}")
    print(f"  Total embeddings   : {result.n_embeddings}")
    print()

    # ── Intra-person table ────────────────────────────────────────────────
    print(Fore.CYAN + "  ── Intra-Person Similarity (same identity, different images)" + Style.RESET_ALL)
    rows = [
        [name, stats["n"], f"{stats['min']:.4f}", f"{stats['max']:.4f}",
         f"{stats['mean']:.4f}", f"{stats['std']:.4f}"]
        for name, stats in result.intra_stats.items()
    ]
    headers = ["Name", "Images", "Min Sim", "Max Sim", "Mean Sim", "Std Dev"]
    if _has_tabulate:
        print(tabulate(rows, headers=headers, tablefmt="rounded_outline"))
    else:
        print("  " + "  ".join(headers))
        for row in rows:
            print("  " + "  ".join(str(c) for c in row))

    print()
    print(f"  Global intra-min : {result.intra_min_global:.4f}")
    print(f"  Global intra-max : {result.intra_max_global:.4f}")

    # ── Inter-person stats ────────────────────────────────────────────────
    if result.n_persons >= 2:
        print()
        print(Fore.CYAN + "  ── Inter-Person Similarity (different identities)" + Style.RESET_ALL)
        print(f"  Min inter-sim : {result.inter_min:.4f}  (lower = better separation)")
        print(f"  Max inter-sim : {result.inter_max:.4f}  (higher = more confusion risk)")

    # ── Gap & confidence ──────────────────────────────────────────────────
    print()
    gap_colour = Fore.GREEN if result.gap > 0.05 else (Fore.YELLOW if result.gap > 0 else Fore.RED)
    print(f"  Separation gap : {gap_colour}{result.gap:+.4f}{Style.RESET_ALL}  "
          f"({'positive = clean separation' if result.gap > 0 else 'NEGATIVE = overlap!'})")
    print(f"  Confidence     : {result.confidence.upper()}")

    # ── Suggested threshold ───────────────────────────────────────────────
    print()
    current = Config.COSINE_THRESHOLD
    t = result.suggested_threshold
    delta_str = f"({t - current:+.3f} vs current {current:.3f})"
    thresh_colour = Fore.GREEN if result.confidence == "high" else (
        Fore.YELLOW if result.confidence == "medium" else Fore.RED
    )
    print(Fore.CYAN + Style.BRIGHT +
          f"  ► Suggested threshold : {thresh_colour}{t:.3f}{Style.RESET_ALL}  "
          f"{delta_str}")

    # ── Warnings ──────────────────────────────────────────────────────────
    if result.warnings:
        print()
        for w in result.warnings:
            print(Fore.YELLOW + f"  {w}" + Style.RESET_ALL)

    print()


# ═══════════════════════════════════════════════════════════════════════════════
# CLI  (python -m utils.threshold_optimizer)
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Analyse embedding similarities and suggest a cosine threshold."
    )
    p.add_argument(
        "--margin", type=float, default=0.05,
        help="Safety margin below intra-class minimum (default: 0.05)"
    )
    p.add_argument(
        "--apply", action="store_true",
        help="Print the export line to update Config.COSINE_THRESHOLD"
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    opt    = ThresholdOptimizer(margin=args.margin)

    try:
        result = opt.analyze()
    except ValueError as exc:
        print(Fore.RED + f"\n  Error: {exc}" + Style.RESET_ALL)
        sys.exit(1)

    print_analysis(result)

    if args.apply:
        t = result.suggested_threshold
        print(Fore.GREEN +
              f"\n  To apply, update config.py:\n"
              f"      COSINE_THRESHOLD: float = {t:.3f}\n" + Style.RESET_ALL)
