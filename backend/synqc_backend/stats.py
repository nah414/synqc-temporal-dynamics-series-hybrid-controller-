"""Small statistics helpers for SynQc KPIs.

No heavy dependencies required. If NumPy is present, you can optionally
swap in numpy.random.multinomial for speed, but this module works without it.
"""

from __future__ import annotations

import math
import random
from typing import Callable, Dict, Iterable, List, Sequence, Tuple

Counts = Dict[str, int]

def _normalize_counts(counts: Counts) -> Tuple[List[str], List[float], int]:
    if not counts:
        raise ValueError("counts is empty")
    outcomes = list(counts.keys())
    total = sum(int(counts[o]) for o in outcomes)
    if total <= 0:
        raise ValueError("counts total must be > 0")
    probs = [counts[o] / total for o in outcomes]
    return outcomes, probs, total

def multinomial_resample(counts: Counts, n: int | None = None, seed: int | None = None) -> Counts:
    """Resample counts under a multinomial model using the plug-in distribution.

    Args:
        counts: observed outcome counts
        n: number of shots to resample; defaults to sum(counts)
        seed: optional RNG seed for reproducibility

    Returns:
        resampled counts dict (same support as input counts)
    """
    if seed is not None:
        rnd = random.Random(seed)
    else:
        rnd = random

    outcomes, probs, total = _normalize_counts(counts)
    n = total if n is None else int(n)
    if n <= 0:
        raise ValueError("n must be > 0")

    # Pure python multinomial sampling via categorical draws.
    # For typical consumer-scale shot budgets this is fine.
    draws = rnd.choices(outcomes, weights=probs, k=n)
    out: Counts = {o: 0 for o in outcomes}
    for d in draws:
        out[d] += 1
    return out

def percentile_ci(samples: Sequence[float], alpha: float = 0.05) -> Tuple[float, float]:
    if not samples:
        raise ValueError("samples is empty")
    s = sorted(float(x) for x in samples)
    lo_idx = max(0, int(math.floor((alpha/2) * (len(s)-1))))
    hi_idx = min(len(s)-1, int(math.ceil((1 - alpha/2) * (len(s)-1))))
    return s[lo_idx], s[hi_idx]

def bootstrap_ci(
    metric_fn: Callable[[Counts], float],
    counts: Counts,
    n_boot: int = 200,
    alpha: float = 0.05,
    seed: int = 0,
) -> Tuple[float, float]:
    r"""Bootstrap CI under multinomial resampling.

    This is appropriate for metrics that are functions of the empirical
    distribution \hat p derived from counts.

    NOTE: CI width should scale roughly like N^{-1/2} when sampling noise dominates.
    """
    if n_boot < 50:
        raise ValueError("n_boot should be >= 50 for a minimally stable CI")
    base_seed = int(seed)
    samples: List[float] = []
    for i in range(n_boot):
        res = multinomial_resample(counts, seed=base_seed + i)
        samples.append(float(metric_fn(res)))
    return percentile_ci(samples, alpha=alpha)
