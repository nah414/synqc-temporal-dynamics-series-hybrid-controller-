from __future__ import annotations

import random
import time
import zlib
from abc import ABC, abstractmethod
from typing import Dict

from .config import settings
from .models import ExperimentPreset, KpiBundle, ExperimentStatus


class BaseBackend(ABC):
    """Abstract base class for SynQc hardware backends.

    Concrete subclasses implement the logic to translate a high-level preset + shot
    budget into real hardware calls (or simulations) and return KPIs.
    """

    id: str
    name: str
    kind: str

    def __init__(self, id: str, name: str, kind: str) -> None:
        self.id = id
        self.name = name
        self.kind = kind

    @abstractmethod
    def run_experiment(self, preset: ExperimentPreset, shot_budget: int) -> KpiBundle:
        """Run the requested preset and return a KpiBundle.

        Implementations MUST obey the provided shot_budget (or lower),
        and they SHOULD NOT exceed engine-level limits. Those limits are
        enforced separately in the SynQcEngine, but backends need to be
        well-behaved as well.
        """


class LocalSimulatorBackend(BaseBackend):
    """Simple local simulator backend.

    This is intentionally lightweight and self-contained: it generates
    plausible KPI values without talking to real quantum hardware. The
    structure, not the physics, is the focus here.

    Future versions can replace the random draws with calls into a
    true SynQc simulator.
    """

    def __init__(self) -> None:
        super().__init__(id="sim_local", name="Local simulator", kind="sim" )

    def run_experiment(self, preset: ExperimentPreset, shot_budget: int) -> KpiBundle:
        # Clamp shots to something reasonable in this demo backend
        shots_used = min(shot_budget, settings.max_shots_per_experiment)

        # Seed randomness with time + preset to provide variety but some continuity
        base_seed = int(time.time()) ^ hash(preset.value)
        rng = random.Random(base_seed)

        if preset is ExperimentPreset.HEALTH:
            fidelity = 0.94 + rng.random() * 0.04  # 0.94–0.98
            latency = 15.0 + rng.random() * 6.0
            backaction = 0.15 + rng.random() * 0.1
        elif preset is ExperimentPreset.LATENCY:
            fidelity = None
            latency = 10.0 + rng.random() * 15.0
            backaction = 0.1 + rng.random() * 0.1
        elif preset is ExperimentPreset.BACKEND_COMPARE:
            fidelity = 0.93 + rng.random() * 0.05
            latency = 18.0 + rng.random() * 10.0
            backaction = 0.2 + rng.random() * 0.1
        else:  # DPD_DEMO or unknown
            fidelity = 0.9 + rng.random() * 0.08
            latency = 12.0 + rng.random() * 8.0
            backaction = 0.1 + rng.random() * 0.1

        status: ExperimentStatus
        if fidelity is not None and fidelity < 0.9:
            status = ExperimentStatus.FAIL
        elif fidelity is not None and fidelity < 0.94:
            status = ExperimentStatus.WARN
        else:
            status = ExperimentStatus.OK

        return KpiBundle(
            fidelity=fidelity,
            latency_us=latency,
            backaction=backaction,
            shots_used=shots_used,
            shot_budget=shot_budget,
            status=status,
        )




class ProviderBackend(BaseBackend):
    """Production-ready backend shell for real provider integrations.

    This class is intentionally lightweight but structured for live SDK wiring.
    Each instance can be configured with vendor-specific timing/fidelity priors
    so that KPI ranges remain realistic even when running in offline mode. In a
    deployed environment, replace the `_simulate` call with the provider's SDK
    invocation and adapt the KPI extraction accordingly.
    """

    def __init__(
        self,
        *,
        id: str,
        name: str,
        kind: str,
        vendor: str,
        fidelity_floor: float,
        fidelity_ceiling: float,
        latency_base_us: float,
        latency_span_us: float,
        backaction_base: float,
        backaction_span: float,
    ) -> None:
        super().__init__(id=id, name=name, kind=kind)
        self.vendor = vendor
        self._fidelity_floor = fidelity_floor
        self._fidelity_ceiling = fidelity_ceiling
        self._latency_base_us = latency_base_us
        self._latency_span_us = latency_span_us
        self._backaction_base = backaction_base
        self._backaction_span = backaction_span

    def _rng(self, preset: ExperimentPreset) -> random.Random:
        # Use a stable-ish seed: time changes provide variety, zlib keeps deterministic mixing.
        salt = zlib.adler32(f"{self.id}:{preset.value}".encode("utf-8"))
        seed = int(time.time()) ^ salt
        return random.Random(seed)

    def _simulate(self, preset: ExperimentPreset, shot_budget: int) -> KpiBundle:
        shots_used = min(shot_budget, settings.max_shots_per_experiment)
        rng = self._rng(preset)

        latency_us = self._latency_base_us + rng.random() * self._latency_span_us
        backaction = self._backaction_base + rng.random() * self._backaction_span

        fidelity = None
        if preset is not ExperimentPreset.LATENCY:
            fidelity_span = self._fidelity_ceiling - self._fidelity_floor
            fidelity = self._fidelity_floor + rng.random() * fidelity_span
            fidelity = max(0.0, min(1.0, fidelity))

        status: ExperimentStatus
        if fidelity is not None and fidelity < 0.90:
            status = ExperimentStatus.FAIL
        elif fidelity is not None and fidelity < 0.94:
            status = ExperimentStatus.WARN
        elif backaction > 0.35:
            status = ExperimentStatus.WARN
        else:
            status = ExperimentStatus.OK

        return KpiBundle(
            fidelity=fidelity,
            latency_us=latency_us,
            backaction=backaction,
            shots_used=shots_used,
            shot_budget=shot_budget,
            status=status,
        )

    def run_experiment(self, preset: ExperimentPreset, shot_budget: int) -> KpiBundle:
        """Run an experiment on a real provider or fall back to simulation.

        The live path can be wired by replacing `_simulate` with vendor-specific
        SDK calls (AWS Braket, IBM Qiskit, Azure Quantum, IonQ native APIs,
        Rigetti SDK, etc.). The simulation keeps the API stable for environments
        without credentials while still exercising the full flow.
        """

        if not settings.allow_provider_simulation:
            raise RuntimeError(
                "Provider simulation is disabled for this deployment. "
                "To exercise provider stubs in simulation mode, set SYNQC_ALLOW_PROVIDER_SIMULATION=true "
                "or use the local simulator backend."
            )

        # Placeholder for live integration. In production deployments, swap this
        # with provider SDK dispatch and KPI extraction.
        return self._simulate(preset, shot_budget)

# Registry of backends
_BACKENDS: Dict[str, BaseBackend] = {
    "sim_local": LocalSimulatorBackend(),

    # Production-targeted provider shells. Replace `_simulate` with live SDK calls
    # (Braket, Qiskit, Azure Quantum, IonQ native, Rigetti SDK) in deployment.
    "aws_braket": ProviderBackend(
        id="aws_braket",
        name="AWS Braket",
        kind="superconducting",
        vendor="aws",
        fidelity_floor=0.92,
        fidelity_ceiling=0.98,
        latency_base_us=45.0,
        latency_span_us=110.0,
        backaction_base=0.16,
        backaction_span=0.14,
    ),
    "ibm_quantum": ProviderBackend(
        id="ibm_quantum",
        name="IBM Quantum",
        kind="superconducting",
        vendor="ibm",
        fidelity_floor=0.93,
        fidelity_ceiling=0.985,
        latency_base_us=28.0,
        latency_span_us=65.0,
        backaction_base=0.15,
        backaction_span=0.16,
    ),
    "azure_quantum": ProviderBackend(
        id="azure_quantum",
        name="Microsoft Azure Quantum",
        kind="trapped_ion",
        vendor="microsoft",
        fidelity_floor=0.925,
        fidelity_ceiling=0.98,
        latency_base_us=85.0,
        latency_span_us=190.0,
        backaction_base=0.12,
        backaction_span=0.15,
    ),
    "ionq_cloud": ProviderBackend(
        id="ionq_cloud",
        name="IonQ Cloud",
        kind="trapped_ion",
        vendor="ionq",
        fidelity_floor=0.935,
        fidelity_ceiling=0.985,
        latency_base_us=120.0,
        latency_span_us=260.0,
        backaction_base=0.10,
        backaction_span=0.14,
    ),
    "rigetti_forest": ProviderBackend(
        id="rigetti_forest",
        name="Rigetti Forest",
        kind="superconducting",
        vendor="rigetti",
        fidelity_floor=0.91,
        fidelity_ceiling=0.975,
        latency_base_us=32.0,
        latency_span_us=75.0,
        backaction_base=0.16,
        backaction_span=0.18,
    ),
}


def get_backend(target_id: str) -> BaseBackend:
    """Return a backend instance for the given target id.

    Raises KeyError if the backend is not known. The engine will catch this
    and translate to a user-visible error.
    """
    if target_id not in _BACKENDS:
        raise KeyError(f"Unknown hardware_target '{target_id}'")
    return _BACKENDS[target_id]


def list_backends() -> Dict[str, BaseBackend]:
    """Return the current backend registry (id -> backend)."""
    return dict(_BACKENDS)
