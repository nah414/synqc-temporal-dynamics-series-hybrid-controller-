import math
import random

from synqc_backend.kpi_estimators import fidelity_dist_ci95_from_counts, fidelity_dist_from_counts

def _sample_counts(expected_q, shots, seed=0):
    rnd = random.Random(seed)
    outcomes = list(expected_q.keys())
    weights = [expected_q[o] for o in outcomes]
    draws = rnd.choices(outcomes, weights=weights, k=shots)
    counts = {o: 0 for o in outcomes}
    for d in draws:
        counts[d] += 1
    return counts

def _linreg_slope(xs, ys):
    # simple least squares slope
    n = len(xs)
    xbar = sum(xs)/n
    ybar = sum(ys)/n
    num = sum((xs[i]-xbar)*(ys[i]-ybar) for i in range(n))
    den = sum((xs[i]-xbar)**2 for i in range(n))
    return num/den if den else 0.0

def test_fidelity_ci_scales_like_inv_sqrt_N():
    # Bell-pair ideal distribution (00 and 11)
    expected_q = {"00": 0.5, "11": 0.5}

    Ns = [200, 800, 3200]
    widths = []
    for i, N in enumerate(Ns):
        counts = _sample_counts(expected_q, shots=N, seed=1234 + i)
        # sanity: point estimate should be close-ish to 1.0
        f = fidelity_dist_from_counts(counts, expected_q)
        assert 0.90 <= f <= 1.0

        lo, hi = fidelity_dist_ci95_from_counts(counts, expected_q, n_boot=200, seed=999)
        widths.append(max(1e-12, hi - lo))

    # Fit log(width) = a + b log(N); for shot-noise-limited metrics b ~ -0.5
    xs = [math.log(n) for n in Ns]
    ys = [math.log(w) for w in widths]
    slope = _linreg_slope(xs, ys)

    # Allow slack: bootstrap + finite-sample effects.
    assert -0.85 < slope < -0.20, f"slope was {slope}, widths={widths}"
