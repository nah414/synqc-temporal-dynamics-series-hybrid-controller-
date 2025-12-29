"""Factoring façade for the Shor/RSA demo.

- method="auto": use Qiskit Shor if available, else classical fallback.
- method="qiskit": force Qiskit Shor (errors if unavailable)
- method="classical": force classical factoring

The module enforces a bit-length cap for N for safety and practicality.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal, Optional

from .classical_factor import factor_semiprime
from .config import SYNQC_SHOR_MAX_N_BITS
from .qiskit_shor import is_qiskit_available, factor_with_qiskit_shor


Method = Literal["auto", "qiskit", "classical"]

@dataclass(frozen=True)
class FactorResult:
    N: int
    p: int
    q: int
    method_used: str
    runtime_ms: float
    steps: list["StepTiming"]


@dataclass(frozen=True)
class StepTiming:
    name: str
    ms: float
    ok: bool = True
    detail: Optional[str] = None


def _validate_N(N: int) -> None:
    if N <= 3:
        raise ValueError("N must be > 3")
    if N.bit_length() > SYNQC_SHOR_MAX_N_BITS:
        raise ValueError(
            f"N too large for demo (bit_length={N.bit_length()} > max={SYNQC_SHOR_MAX_N_BITS}). "
            "Reduce N or raise SYNQC_SHOR_MAX_N_BITS intentionally."
        )


def factor_N(
    N: int,
    method: Method = "auto",
    *,
    backend_mode: str = "aer",
    shots: int = 1024,
    ibm_backend_name: Optional[str] = None,
    provider_backend_name: Optional[str] = None,
    provider_loader: Optional[str] = None,
) -> FactorResult:
    """Factor N into (p, q).

    backend_mode/shots/ibm_backend_name/provider_backend_name/provider_loader are only used
    when method resolves to Qiskit Shor.
    """
    steps: list[StepTiming] = []

    t_validate0 = time.perf_counter()
    _validate_N(N)
    t_validate1 = time.perf_counter()
    steps.append(StepTiming(name="validate", ms=(t_validate1 - t_validate0) * 1000))
    method = (method or "auto").lower().strip()  # type: ignore

    t0 = time.perf_counter()

    if method == "classical":
        t_class0 = time.perf_counter()
        p, q = factor_semiprime(N)
        t_class1 = time.perf_counter()
        steps.append(StepTiming(name="classical_factor", ms=(t_class1 - t_class0) * 1000))
        t1 = t_class1
        return FactorResult(
            N=N,
            p=p,
            q=q,
            method_used="classical_fallback",
            runtime_ms=(t1 - t0) * 1000,
            steps=steps,
        )

    if method == "qiskit":
        t_q0 = time.perf_counter()
        res = factor_with_qiskit_shor(
            N,
            backend_mode=backend_mode,
            shots=shots,
            ibm_backend_name=ibm_backend_name,
            provider_backend_name=provider_backend_name,
            provider_loader=provider_loader,
        )
        t_q1 = time.perf_counter()
        steps.append(StepTiming(name="qiskit_shor", ms=(t_q1 - t_q0) * 1000))
        t1 = t_q1
        return FactorResult(
            N=N,
            p=res.p,
            q=res.q,
            method_used=f"qiskit_shor:{res.backend_mode}",
            runtime_ms=(t1 - t0) * 1000,
            steps=steps,
        )

    if method == "auto":
        if is_qiskit_available():
            try:
                t_q0 = time.perf_counter()
                res = factor_with_qiskit_shor(
                    N,
                    backend_mode=backend_mode,
                    shots=shots,
                    ibm_backend_name=ibm_backend_name,
                    provider_backend_name=provider_backend_name,
                    provider_loader=provider_loader,
                )
                t_q1 = time.perf_counter()
                steps.append(StepTiming(name="qiskit_shor", ms=(t_q1 - t_q0) * 1000))
                t1 = t_q1
                return FactorResult(
                    N=N,
                    p=res.p,
                    q=res.q,
                    method_used=f"qiskit_shor:{res.backend_mode}",
                    runtime_ms=(t1 - t0) * 1000,
                    steps=steps,
                )
            except Exception as e:
                # Fall back silently; the UI displays which method was used.
                t_q1 = time.perf_counter()
                steps.append(
                    StepTiming(
                        name="qiskit_shor",
                        ms=(t_q1 - t_q0) * 1000,
                        ok=False,
                        detail=f"failed; used classical fallback ({type(e).__name__}: {e})",
                    )
                )

        t_class0 = time.perf_counter()
        p, q = factor_semiprime(N)
        t_class1 = time.perf_counter()
        steps.append(StepTiming(name="classical_factor", ms=(t_class1 - t_class0) * 1000))
        t1 = t_class1
        return FactorResult(
            N=N,
            p=p,
            q=q,
            method_used="classical_fallback",
            runtime_ms=(t1 - t0) * 1000,
            steps=steps,
        )

    raise ValueError(f"Unknown method: {method}")
