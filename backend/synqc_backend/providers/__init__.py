from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from ..config import settings
from .. import hardware_backends
from ..hardware_backends import BaseBackend, LocalSimulatorBackend, ProviderBackend, list_backends
from ..models import ErrorCode, ExperimentPreset, KpiBundle, ProviderCapabilities
from ..provider_clients import ProviderClientError
from ..stats import Counts


@dataclass
class ProviderTarget:
    """Provider target descriptor with capabilities and vendor metadata."""

    id: str
    name: str
    kind: str
    vendor: str
    capabilities: ProviderCapabilities


@dataclass
class ProviderRunResult:
    """Structured provider execution output."""

    kpis: KpiBundle
    artifacts: Dict[str, Any]


_CAPABILITIES: Dict[str, ProviderCapabilities] = {
    "sim_local": ProviderCapabilities(
        max_shots=None,
        queue_behavior="inline",
        supported_gates=["h", "x", "y", "z", "cx", "rx", "ry", "cz"],
        notes="Reference simulator for demo runs.",
    ),
    "ibm_quantum": ProviderCapabilities(
        max_shots=32000,
        queue_behavior="queued",
        supported_gates=["h", "x", "y", "z", "cx", "cz", "rx", "ry"],
        notes="Qiskit-backed provider supporting Aer simulation or IBM Quantum backends.",
    ),
    "aws_braket": ProviderCapabilities(
        max_shots=100000,
        queue_behavior="queued",
        supported_gates=["ccnot", "cphaseshift", "cnot", "cz", "hadamard", "i", "phaseshift", "rx", "ry", "rz", "swap", "xy"],
        notes="AWS Braket shell with queue semantics and file/env payload adapters.",
    ),
    "azure_quantum": ProviderCapabilities(
        max_shots=500000,
        queue_behavior="queued",
        supported_gates=[
            "h",
            "x",
            "y",
            "z",
            "s",
            "t",
            "cz",
            "rx",
            "ry",
            "rz",
            "swap",
        ],
        notes="Azure Quantum shell that can be wired to IonQ/Honeywell-style targets.",
    ),
    "ionq_cloud": ProviderCapabilities(
        max_shots=100000,
        queue_behavior="priority_queue",
        supported_gates=["h", "x", "y", "z", "cz", "rx", "ry", "rz", "ms"],
        notes="IonQ-native adapter supporting demo API-key wiring and synthetic fallbacks.",
    ),
    "rigetti_forest": ProviderCapabilities(
        max_shots=100000,
        queue_behavior="queued",
        supported_gates=["i", "x", "y", "z", "rx", "ry", "rz", "cz", "cnot", "hadamard"],
        notes="Rigetti Forest shell for Aspen-style QCS simulators or live endpoints.",
    ),
}


def _vendor_for_backend(backend: BaseBackend) -> str:
    vendor = getattr(backend, "vendor", None)
    if vendor:
        return vendor
    if isinstance(backend, LocalSimulatorBackend):
        return "synqc"
    return "provider"


def list_targets() -> Dict[str, ProviderTarget]:
    """Return the provider target registry with capabilities attached."""

    targets: Dict[str, ProviderTarget] = {}
    for backend_id, backend in list_backends().items():
        capabilities = _CAPABILITIES.get(
            backend_id,
            ProviderCapabilities(
                max_shots=settings.max_shots_per_experiment,
                queue_behavior="queued" if backend.kind != "sim" else "inline",
                supported_gates=["h", "x", "y", "z", "cx", "rx", "ry", "cz"],
                notes="Simulated provider shell" if backend.kind != "sim" else "Local simulator",
            ),
        )
        targets[backend_id] = ProviderTarget(
            id=backend_id,
            name=backend.name,
            kind=backend.kind,
            vendor=_vendor_for_backend(backend),
            capabilities=capabilities,
        )
    return targets


def validate_credentials(target_id: str) -> bool:
    """Validate whether a provider target has usable credentials or simulation enabled."""

    backend = hardware_backends.get_backend(target_id)
    if isinstance(backend, LocalSimulatorBackend):
        return True

    live_client = getattr(backend, "_live_client", None)
    if live_client and hasattr(live_client, "validate_credentials"):
        try:
            return bool(live_client.validate_credentials())
        except Exception:
            return False

    # If simulation is permitted for providers, consider credentials valid enough.
    return settings.allow_provider_simulation


def capabilities(target_id: str) -> ProviderCapabilities:
    """Return advertised capabilities for a target id."""

    if target_id not in _CAPABILITIES:
        return ProviderCapabilities(
            max_shots=settings.max_shots_per_experiment,
            queue_behavior="queued",
            supported_gates=["h", "x", "y", "z", "cx", "rx", "ry", "cz"],
            notes="Simulated provider shell",
        )
    return _CAPABILITIES[target_id]


def run_experiment(target_id: str, preset: ExperimentPreset, shot_budget: int) -> ProviderRunResult:
    """Execute a preset on the requested provider target."""

    backend = hardware_backends.get_backend(target_id)
    caps = capabilities(target_id)
    if caps.max_shots and shot_budget > caps.max_shots:
        raise ProviderClientError(
            f"Requested shots ({shot_budget}) exceed provider limit ({caps.max_shots})",
            code=ErrorCode.PROVIDER_CAPACITY,
            action_hint="Lower the shot budget for this target or select a simulator.",
            detail={"requested": shot_budget, "max": caps.max_shots},
        )
    try:
        kpis = backend.run_experiment(preset, shot_budget)
    except ProviderClientError:
        raise
    except Exception as exc:  # pragma: no cover - defensive guard for unexpected failures
        raise ProviderClientError(f"Provider execution failed: {exc}") from exc

    artifacts: Dict[str, Any] = {}
    raw_counts: Counts | None = getattr(kpis, "raw_counts", None)
    expected_dist = getattr(kpis, "expected_distribution", None)
    if raw_counts:
        artifacts["raw_counts"] = raw_counts
    if expected_dist:
        artifacts["expected_distribution"] = expected_dist

    if isinstance(backend, ProviderBackend):
        backend_name = getattr(getattr(backend, "_live_client", None), "backend_name", None)
        if backend_name:
            artifacts["provider_backend"] = backend_name

    return ProviderRunResult(kpis=kpis, artifacts=artifacts)


__all__ = [
    "ProviderRunResult",
    "ProviderTarget",
    "capabilities",
    "list_targets",
    "run_experiment",
    "validate_credentials",
]
