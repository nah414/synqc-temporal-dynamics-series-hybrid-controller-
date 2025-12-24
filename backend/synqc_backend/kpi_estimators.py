"""KPI estimators that are explicitly tethered to data + models.

Philosophy:
  - If we report a KPI, we must be able to name:
      * the definition (math)
      * the estimator (how computed from data)
      * the uncertainty method (if sampling-based)
  - Prefer distribution-based metrics for hardware portability.
"""

from __future__ import annotations

import math
from typing import Dict, Mapping, Optional, Tuple

from .stats import Counts, bootstrap_ci

def distribution_from_counts(counts: Counts, support: Optional[Tuple[str, ...]] = None) -> Dict[str, float]:
    """Convert outcome counts into an empirical distribution \hat p(x)."""
    if not counts:
        raise ValueError("counts is empty")
    total = sum(int(v) for v in counts.values())
    if total <= 0:
        raise ValueError("counts total must be > 0")
    if support is None:
        support = tuple(counts.keys())
    return {k: counts.get(k, 0) / total for k in support}

def distribution_fidelity(p: Mapping[str, float], q: Mapping[str, float]) -> float:
    """Classical fidelity between two discrete distributions.

    F(p,q) = (sum_x sqrt(p_x q_x))^2
    """
    # Use the union of supports so missing outcomes are treated as 0.
    keys = set(p.keys()) | set(q.keys())
    if not keys:
        raise ValueError("distributions must have at least one outcome")
    s = 0.0
    for k in keys:
        pk = float(p.get(k, 0.0))
        qk = float(q.get(k, 0.0))
        if pk < 0 or qk < 0:
            raise ValueError("probabilities must be nonnegative")
        s += math.sqrt(pk * qk)
    # numerical guard
    s = max(0.0, min(1.0, s))
    return float(s * s)

def fidelity_dist_from_counts(counts: Counts, expected_q: Mapping[str, float]) -> float:
    support = tuple(set(counts.keys()) | set(expected_q.keys()))
    p_hat = distribution_from_counts(counts, support=support)
    return distribution_fidelity(p_hat, expected_q)

def fidelity_dist_ci95_from_counts(
    counts: Counts,
    expected_q: Mapping[str, float],
    n_boot: int = 200,
    seed: int = 0,
) -> Tuple[float, float]:
    def metric_fn(resampled_counts: Counts) -> float:
        return fidelity_dist_from_counts(resampled_counts, expected_q)
    return bootstrap_ci(metric_fn, counts=counts, n_boot=n_boot, alpha=0.05, seed=seed)
