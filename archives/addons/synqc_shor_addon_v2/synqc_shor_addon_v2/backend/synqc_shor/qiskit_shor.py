"""Best-effort Qiskit Shor integration (simulator + real hardware).

Qiskit's public API has moved around across major versions (0.4x -> 1.x). This module
tries multiple import and execution paths so the rest of SynQc doesn't have to care.

Design goals:
- Keep imports lazy (only import Qiskit when needed).
- Provide a clean error when Qiskit isn't available.
- Support "aer" (local simulation) out of the box.
- Support "ibm" (Runtime) when qiskit-ibm-runtime is installed and configured.

Reality check:
- Shor is not currently practical for real RSA sizes on real quantum hardware.
- This feature is intentionally capped to tiny N for demo purposes.
"""

from __future__ import annotations

from dataclasses import dataclass
import inspect
import importlib
import json
import os
from typing import Optional, Tuple


@dataclass(frozen=True)
class QiskitShorResult:
    p: int
    q: int
    raw: object
    backend_mode: str


def is_qiskit_available() -> bool:
    try:
        import qiskit  # noqa: F401
        return True
    except Exception:
        return False


def _import_shor_class():
    """Try the most common Shor import locations."""
    # Newer split packages (Qiskit 1.x)
    try:
        from qiskit_algorithms.factorizers import Shor  # type: ignore
        return Shor
    except Exception:
        pass

    # Older monorepo (Qiskit 0.4x)
    try:
        from qiskit.algorithms import Shor  # type: ignore
        return Shor
    except Exception:
        pass

    raise ImportError(
        "Could not import Shor from qiskit_algorithms.factorizers or qiskit.algorithms. "
        "Install qiskit-algorithms (or upgrade Qiskit) to enable quantum factoring."
    )


def _pick_aer_backend():
    try:
        from qiskit_aer import AerSimulator  # type: ignore
        return AerSimulator()
    except Exception as e:
        raise RuntimeError(
            "Requested Aer simulator but qiskit-aer is not installed."
        ) from e


def _load_provider_backend(provider_loader: Optional[str], backend_name: Optional[str]):
    """Load a backend from an arbitrary Qiskit provider.

    provider_loader: dotted path or ``module:Class`` string for the provider class
    backend_name: name passed to provider.get_backend

    Environment fallbacks:
    - SYNQC_SHOR_PROVIDER_CLASS (or SYNQC_SHOR_PROVIDER_LOADER)
    - SYNQC_SHOR_PROVIDER_BACKEND
    - SYNQC_SHOR_PROVIDER_TOKEN (added to kwargs if accepted)
    - SYNQC_SHOR_PROVIDER_KWARGS (JSON dict for provider constructor)
    """

    provider_path = (
        (provider_loader or "").strip()
        or os.getenv("SYNQC_SHOR_PROVIDER_CLASS", "").strip()
        or os.getenv("SYNQC_SHOR_PROVIDER_LOADER", "").strip()
    )
    backend_name = (backend_name or os.getenv("SYNQC_SHOR_PROVIDER_BACKEND", "").strip()) or None

    if not provider_path:
        raise RuntimeError(
            "Custom backend requested but no provider loader specified. "
            "Set provider_loader or SYNQC_SHOR_PROVIDER_CLASS."
        )
    if not backend_name:
        raise RuntimeError(
            "Custom backend requested but no backend name specified. "
            "Set provider_backend_name or SYNQC_SHOR_PROVIDER_BACKEND."
        )

    if ":" in provider_path:
        module_name, class_name = provider_path.split(":", 1)
    else:
        module_name, class_name = provider_path.rsplit(".", 1)

    module = importlib.import_module(module_name)
    provider_cls = getattr(module, class_name)

    kwargs = {}
    raw_kwargs = os.getenv("SYNQC_SHOR_PROVIDER_KWARGS", "").strip()
    if raw_kwargs:
        try:
            kwargs.update(json.loads(raw_kwargs))
        except Exception:
            # Keep kwargs empty on parse failure to avoid surprising constructor args
            pass

    token = os.getenv("SYNQC_SHOR_PROVIDER_TOKEN")
    if token and "token" not in kwargs:
        kwargs["token"] = token

    provider = provider_cls(**kwargs) if kwargs else provider_cls()
    return provider.get_backend(backend_name)


def _build_sampler_from_backend(backend, shots: int):
    """Construct a Sampler primitive for an arbitrary backend."""
    try:
        from qiskit.primitives import BackendSampler  # type: ignore

        return BackendSampler(backend, options={"shots": shots})
    except Exception as e:
        raise RuntimeError(
            "Custom backend requested but BackendSampler is unavailable. "
            "Ensure your Qiskit version supports primitives for hardware backends."
        ) from e


def _get_ibm_runtime_service():
    """Return a QiskitRuntimeService instance.

    This tries:
    1) QiskitRuntimeService() (uses saved account)
    2) QiskitRuntimeService(channel=..., token=..., instance=...) using env vars
    """
    try:
        from qiskit_ibm_runtime import QiskitRuntimeService  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "IBM Runtime requested but qiskit-ibm-runtime is not installed."
        ) from e

    # Try default (saved account)
    try:
        return QiskitRuntimeService()
    except Exception:
        pass

    token = os.getenv("QISKIT_IBM_TOKEN") or os.getenv("IBM_QUANTUM_TOKEN")
    channel = os.getenv("QISKIT_IBM_CHANNEL", "ibm_quantum")
    instance = os.getenv("QISKIT_IBM_INSTANCE")  # optional

    if not token:
        raise RuntimeError(
            "IBM Runtime requested, but no saved account and no QISKIT_IBM_TOKEN/IBM_QUANTUM_TOKEN env var."
        )

    kwargs = {"channel": channel, "token": token}
    if instance:
        kwargs["instance"] = instance

    return QiskitRuntimeService(**kwargs)


def _parse_factors(N: int, raw_result: object) -> Tuple[int, int]:
    """Normalize Shor result object into (p, q)."""
    factors = None
    if hasattr(raw_result, "factors"):
        factors = getattr(raw_result, "factors")
    elif isinstance(raw_result, dict) and "factors" in raw_result:
        factors = raw_result["factors"]

    if not factors:
        raise RuntimeError("Qiskit Shor did not return factors (it may have failed).")

    first = factors[0] if isinstance(factors, (list, tuple)) else factors
    if not (isinstance(first, (list, tuple)) and len(first) >= 2):
        raise RuntimeError(f"Unexpected Shor factors format: {type(factors)} / {factors!r}")

    p, q = int(first[0]), int(first[1])
    if p * q != N:
        raise RuntimeError(f"Invalid factors from Shor: p*q != N ({p}*{q} != {N})")
    return (min(p, q), max(p, q))


def factor_with_qiskit_shor(
    N: int,
    *,
    backend_mode: str = "aer",
    shots: int = 1024,
    ibm_backend_name: Optional[str] = None,
    provider_backend_name: Optional[str] = None,
    provider_loader: Optional[str] = None,
) -> QiskitShorResult:
    """Factor N using Qiskit's Shor implementation.

    backend_mode:
      - "aer" (default): local simulation using qiskit-aer
      - "ibm": IBM Quantum Runtime (requires qiskit-ibm-runtime configured)
      - "custom": any provider backend reachable via provider_loader/provider_backend_name

    Returns: QiskitShorResult(p, q, raw_result, backend_mode)
    """
    backend_mode = (backend_mode or "aer").lower().strip()
    Shor = _import_shor_class()

    # Determine how this Shor class wants to run
    sig = inspect.signature(Shor)
    wants_quantum_instance = "quantum_instance" in sig.parameters
    wants_sampler = "sampler" in sig.parameters

    if not wants_quantum_instance and not wants_sampler:
        # Some versions may accept no explicit execution primitive.
        wants_sampler = False
        wants_quantum_instance = False

    # ----------------------------
    # Path 1: quantum_instance (older)
    # ----------------------------
    if wants_quantum_instance:
        try:
            from qiskit.utils import QuantumInstance  # type: ignore
        except Exception as e:
            raise RuntimeError(
                "This Qiskit Shor expects quantum_instance but QuantumInstance is unavailable. "
                "Install a compatible Qiskit version or use the sampler-based Shor."
            ) from e

        if backend_mode in {"aer", "sim", "simulator"}:
            backend = _pick_aer_backend()
        elif backend_mode in {"ibm", "runtime", "ibm_quantum"}:
            # Best-effort backend retrieval for older stacks.
            backend_name = ibm_backend_name or os.getenv("SYNQC_SHOR_IBM_BACKEND") or os.getenv("IBM_BACKEND")
            if not backend_name:
                raise RuntimeError("IBM backend requested but no backend name provided (SYNQC_SHOR_IBM_BACKEND).")

            # Try the legacy provider first, then Runtime service backend.
            backend = None
            try:
                from qiskit_ibm_provider import IBMProvider  # type: ignore
                provider = IBMProvider()
                backend = provider.get_backend(backend_name)
            except Exception:
                try:
                    service = _get_ibm_runtime_service()
                    backend = service.backend(backend_name)
                except Exception as e:
                    raise RuntimeError(
                        "Could not acquire IBM backend. Configure qiskit-ibm-provider or qiskit-ibm-runtime."
                    ) from e
        elif backend_mode == "custom":
            backend = _load_provider_backend(provider_loader, provider_backend_name)
        else:
            raise ValueError(f"Unknown backend_mode: {backend_mode}")

        qi = QuantumInstance(backend=backend, shots=shots)
        shor = Shor(quantum_instance=qi)
        try:
            raw = shor.factor(N)  # type: ignore[attr-defined]
        except TypeError:
            raw = shor.factor(N=N)  # type: ignore[attr-defined]

        p, q = _parse_factors(N, raw)
        return QiskitShorResult(p=p, q=q, raw=raw, backend_mode=backend_mode)

    # ----------------------------
    # Path 2: sampler (newer primitives)
    # ----------------------------
    if wants_sampler:
        if backend_mode in {"aer", "sim", "simulator"}:
            sampler = None
            try:
                from qiskit_aer.primitives import Sampler as AerSampler  # type: ignore
                sampler = AerSampler(run_options={"shots": shots})
            except Exception:
                sampler = None

            if sampler is None:
                # Generic primitive sampler (may use a default simulator)
                try:
                    from qiskit.primitives import Sampler  # type: ignore
                    sampler = Sampler(options={"shots": shots})
                except Exception as e:
                    raise RuntimeError(
                        "Could not construct a Sampler primitive. Install qiskit-aer or a compatible Qiskit version."
                    ) from e

            shor = Shor(sampler=sampler)
            try:
                raw = shor.factor(N)  # type: ignore[attr-defined]
            except TypeError:
                raw = shor.factor(N=N)  # type: ignore[attr-defined]

            p, q = _parse_factors(N, raw)
            return QiskitShorResult(p=p, q=q, raw=raw, backend_mode=backend_mode)

        if backend_mode in {"ibm", "runtime", "ibm_quantum"}:
            backend_name = ibm_backend_name or os.getenv("SYNQC_SHOR_IBM_BACKEND") or os.getenv("IBM_BACKEND")
            if not backend_name:
                raise RuntimeError(
                    "IBM Runtime requested but no backend name provided. Set SYNQC_SHOR_IBM_BACKEND."
                )

            service = _get_ibm_runtime_service()
            backend = service.backend(backend_name)

            try:
                from qiskit_ibm_runtime import Session, Sampler as RuntimeSampler  # type: ignore
            except Exception as e:
                raise RuntimeError(
                    "IBM Runtime requested but qiskit-ibm-runtime primitives are unavailable."
                ) from e

            # Run inside a Session (recommended by IBM Runtime patterns).
            with Session(service=service, backend=backend) as session:
                sampler = RuntimeSampler(session=session, options={"shots": shots})
                shor = Shor(sampler=sampler)
                try:
                    raw = shor.factor(N)  # type: ignore[attr-defined]
                except TypeError:
                    raw = shor.factor(N=N)  # type: ignore[attr-defined]

            p, q = _parse_factors(N, raw)
            return QiskitShorResult(p=p, q=q, raw=raw, backend_mode=backend_mode)

        if backend_mode == "custom":
            backend = _load_provider_backend(provider_loader, provider_backend_name)
            sampler = _build_sampler_from_backend(backend, shots)
            shor = Shor(sampler=sampler)
            try:
                raw = shor.factor(N)  # type: ignore[attr-defined]
            except TypeError:
                raw = shor.factor(N=N)  # type: ignore[attr-defined]

            p, q = _parse_factors(N, raw)
            return QiskitShorResult(p=p, q=q, raw=raw, backend_mode=backend_mode)

        raise ValueError(f"Unknown backend_mode: {backend_mode}")

    # ----------------------------
    # Path 3: no explicit primitive
    # ----------------------------
    shor = Shor()
    try:
        raw = shor.factor(N)  # type: ignore[attr-defined]
    except TypeError:
        raw = shor.factor(N=N)  # type: ignore[attr-defined]

    p, q = _parse_factors(N, raw)
    return QiskitShorResult(p=p, q=q, raw=raw, backend_mode="default")
