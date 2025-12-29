"""Classical factoring fallback (toy only).

This exists so the UI still works when Qiskit isn't installed, or when the quantum
backend is unavailable.

For the bit-lengths this feature allows by default (<= 20 bits), this is plenty fast.
"""

from __future__ import annotations

import math
import random
from typing import Tuple


def _trial_division(n: int) -> Tuple[int, int] | None:
    if n % 2 == 0:
        return (2, n // 2)
    limit = int(math.isqrt(n))
    f = 3
    while f <= limit:
        if n % f == 0:
            return (f, n // f)
        f += 2
    return None


def _pollards_rho(n: int) -> int:
    """Return a non-trivial factor of n using Pollard's Rho (probabilistic)."""
    if n % 2 == 0:
        return 2
    if n % 3 == 0:
        return 3

    while True:
        c = random.randrange(1, n)
        x = random.randrange(0, n)
        y = x
        d = 1

        def f(v: int) -> int:
            return (pow(v, 2, n) + c) % n

        while d == 1:
            x = f(x)
            y = f(f(y))
            d = math.gcd(abs(x - y), n)
        if d != n:
            return d


def factor_semiprime(N: int) -> Tuple[int, int]:
    """Factor a semiprime N = p*q (toy sizes)."""
    if N <= 1:
        raise ValueError("N must be > 1")
    if N % 2 == 0:
        return (2, N // 2)

    td = _trial_division(N)
    if td is not None:
        p, q = td
        return (min(p, q), max(p, q))

    # If trial division didn't find anything, use Pollard's Rho.
    p = _pollards_rho(N)
    q = N // p
    if p * q != N:
        raise ValueError("Failed to factor N")
    return (min(p, q), max(p, q))
