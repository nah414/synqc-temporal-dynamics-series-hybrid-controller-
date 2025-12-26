from __future__ import annotations

import random
import time
import zlib
from abc import ABC, abstractmethod
from typing import Dict

from .config import settings
from .grover import (
    GroverConfig,
    GroverDependencyError,
    energy_aware_search,
    ideal_marked_distribution,
    success_probability,
)
from .kpi_estimators import distribution_fidelity, fidelity_dist_from_counts
from .logging_utils import get_logger
from .metrics_recorder import provider_metrics
from .models import ErrorCode, ExperimentPreset, ExperimentStatus, KpiBundle
from .provider_clients import BaseProviderClient, ProviderClientError, load_provider_clients
from .stats import Counts


logger = get_logger(__name__)


def _normalize_distribution(dist: Dict[str, float]) -> Dict[str, float]:
    total = sum(max(0.0, float(v)) for v in dist.values())
    if total <= 0:
        raise ValueError("distribution must have positive mass")
    return {k: max(0.0, float(v)) / total for k, v in dist.items()}


def _expected_distribution(preset: ExperimentPreset, rng: random.Random) -> Dict[str, float]:
    """Return a lightweight reference distribution for the requested preset."""

    if preset is ExperimentPreset.LATENCY:
        base = {"00": 0.55, "01": 0.22, "10": 0.14, "11": 0.09}
    elif preset is ExperimentPreset.GROVER_DEMO:
        base = ideal_marked_distribution(5, ["10101", "01010"], background=0.01)
    elif preset is ExperimentPreset.BACKEND_COMPARE:
        base = {"00": 0.42, "01": 0.22, "10": 0.2, "11": 0.16}
    elif preset is ExperimentPreset.HELLO_QUANTUM_SIM:
        base = {"00": 0.7, "01": 0.15, "10": 0.1, "11": 0.05}
    else:
        # HEALTH, DPD_DEMO (or unknown)
        base = {"00": 0.64, "11": 0.28, "01": 0.05, "10": 0.03}

    # Add gentle jitter so runs don't look copy-pasted while staying normalized.
    jittered = {k: v + rng.uniform(-0.01, 0.01) for k, v in base.items()}
    return _normalize_distribution(jittered)


def _mix_toward_uniform(
    expected_q: Dict[str, float], target_fidelity: float | None, rng: random.Random
) -> Dict[str, float]:
    """Blend a reference distribution toward uniform to match a target fidelity."""

    outcomes = list(expected_q.keys())
    uniform = 1.0 / len(outcomes)

    # Candidate noise weights toward uniform. Evaluate fidelity to pick the closest match.
    candidates = [i / 200 for i in range(1, 80)]  # 0.005 .. 0.395
    best = _normalize_distribution(expected_q)
    best_score = float("inf")

    for noise in candidates:
        mixed = {o: (1 - noise) * expected_q[o] + noise * uniform for o in outcomes}
        mixed = _normalize_distribution(mixed)
        f = distribution_fidelity(expected_q, mixed)
        if target_fidelity is None:
            score = rng.random() * 0.01  # deterministic-ish but keeps loop cheap
        else:
            score = abs(f - target_fidelity)
        if score < best_score:
            best = mixed
            best_score = score

    # Small random tilt to avoid identical runs and ensure normalization.
    tilted = {o: max(0.0, v + rng.uniform(-0.005, 0.005)) for o, v in best.items()}
    return _normalize_distribution(tilted)


def _sample_counts(dist: Dict[str, float], shots: int, rng: random.Random) -> Counts:
    outcomes = list(dist.keys())
    weights = [dist[o] for o in outcomes]
    draws = rng.choices(outcomes, weights=weights, k=shots)
    counts: Counts = {o: 0 for o in outcomes}
    for d in draws:
        counts[d] += 1
    return counts


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
        if preset is ExperimentPreset.GROVER_DEMO:
            return self._run_grover_preset(shot_budget)

        # Clamp shots to something reasonable in this demo backend
        shots_used = min(shot_budget, settings.max_shots_per_experiment)

        # Seed randomness with time + preset to provide variety but some continuity
        base_seed = int(time.time()) ^ hash(preset.value)
        rng = random.Random(base_seed)

        expected_q = _expected_distribution(preset, rng)
        target_fidelity: float | None

        if preset is ExperimentPreset.HEALTH:
            target_fidelity = 0.94 + rng.random() * 0.04  # 0.94–0.98
            latency = 15.0 + rng.random() * 6.0
            backaction = 0.15 + rng.random() * 0.1
        elif preset is ExperimentPreset.LATENCY:
            target_fidelity = None
            latency = 10.0 + rng.random() * 15.0
            backaction = 0.1 + rng.random() * 0.1
        elif preset is ExperimentPreset.BACKEND_COMPARE:
            target_fidelity = 0.93 + rng.random() * 0.05
            latency = 18.0 + rng.random() * 10.0
            backaction = 0.2 + rng.random() * 0.1
        elif preset is ExperimentPreset.HELLO_QUANTUM_SIM:
            target_fidelity = 0.975 + rng.random() * 0.015  # 0.975–0.99
            latency = 9.0 + rng.random() * 4.0
            backaction = 0.08 + rng.random() * 0.04
        else:  # DPD_DEMO or unknown
            target_fidelity = 0.90 + rng.random() * 0.06
            latency = 12.0 + rng.random() * 8.0
            backaction = 0.1 + rng.random() * 0.1

        actual_q = _mix_toward_uniform(expected_q, target_fidelity, rng)
        raw_counts = _sample_counts(actual_q, shots_used, rng)
        measured_shots = sum(raw_counts.values())

        fidelity = None
        if target_fidelity is not None:
            fidelity = fidelity_dist_from_counts(raw_counts, expected_q)

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
            raw_counts=raw_counts,
            expected_distribution=expected_q,
            shots_used=measured_shots,
            shot_budget=shot_budget,
            status=status,
        )

    def _run_grover_preset(self, shot_budget: int) -> KpiBundle:
        shots_cap = min(shot_budget, settings.max_shots_per_experiment)
        cfg = GroverConfig(
            n_qubits=5,
            marked=["10101", "01010"],
            iterations=None,
            seed_sim=int(time.time()) & 0xFFFF,
        )

        expected_q = ideal_marked_distribution(cfg.n_qubits, cfg.marked, background=0.01)

        try:
            shots_used, counts, _success_est = energy_aware_search(
                cfg, target_success=0.65, eps=0.08, delta=0.05, max_shots_cap=shots_cap, verbose=False
            )
        except GroverDependencyError as exc:
            raise ProviderClientError(
                "Grover preset requires the qiskit and qiskit-aer extras to run real circuits",
                code=ErrorCode.PROVIDER_SIM_DISABLED,
                action_hint="Install the 'backend[qiskit]' extra or enable a live provider target for Grover runs.",
            ) from exc

        fidelity = fidelity_dist_from_counts(counts, expected_q)
        latency = 14.0 + random.random() * 6.0
        backaction = 0.11 + random.random() * 0.07

        status: ExperimentStatus
        if fidelity < 0.9:
            status = ExperimentStatus.FAIL
        elif fidelity < 0.94:
            status = ExperimentStatus.WARN
        else:
            status = ExperimentStatus.OK

        return KpiBundle(
            fidelity=fidelity,
            latency_us=latency,
            backaction=backaction,
            raw_counts=counts,
            expected_distribution=expected_q,
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
        live_client: BaseProviderClient | None = None,
    ) -> None:
        super().__init__(id=id, name=name, kind=kind)
        self.vendor = vendor
        self._fidelity_floor = fidelity_floor
        self._fidelity_ceiling = fidelity_ceiling
        self._latency_base_us = latency_base_us
        self._latency_span_us = latency_span_us
        self._backaction_base = backaction_base
        self._backaction_span = backaction_span
        self._live_client = live_client

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
        expected_q = _expected_distribution(preset, rng)
        target_fidelity: float | None = None
        if preset is not ExperimentPreset.LATENCY:
            fidelity_span = self._fidelity_ceiling - self._fidelity_floor
            target_fidelity = self._fidelity_floor + rng.random() * fidelity_span
            target_fidelity = max(0.0, min(1.0, target_fidelity))

        actual_q = _mix_toward_uniform(expected_q, target_fidelity, rng)
        raw_counts = _sample_counts(actual_q, shots_used, rng)
        measured_shots = sum(raw_counts.values())

        if target_fidelity is not None:
            fidelity = fidelity_dist_from_counts(raw_counts, expected_q)

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
            raw_counts=raw_counts,
            expected_distribution=expected_q,
            shots_used=measured_shots,
            shot_budget=shot_budget,
            status=status,
        )

    def _run_live(self, preset: ExperimentPreset, shot_budget: int) -> KpiBundle:
        if not self._live_client:
            raise RuntimeError("No live provider client configured")

        try:
            result = self._live_client.run(preset, shot_budget)
        except ProviderClientError:
            raise
        except Exception as exc:
            raise ProviderClientError(f"Live provider call failed: {exc}") from exc

        raw_counts = result.raw_counts
        measured_shots = result.shots_used or sum(raw_counts.values())

        expected_q: Dict[str, float]
        try:
            if result.expected_distribution:
                expected_q = _normalize_distribution(result.expected_distribution)
            else:
                # Fall back to the reference shape so fidelity can still be estimated
                rng = self._rng(preset)
                expected_q = _expected_distribution(preset, rng)
        except ValueError as exc:
            raise ProviderClientError(f"Invalid expected_distribution from provider: {exc}") from exc

        fidelity = result.fidelity
        if fidelity is None and expected_q:
            try:
                fidelity = fidelity_dist_from_counts(raw_counts, expected_q)
            except ValueError:
                fidelity = None

        latency_us = result.latency_us
        if latency_us is None:
            rng = self._rng(preset)
            latency_us = self._latency_base_us + rng.random() * self._latency_span_us

        backaction = result.backaction
        if backaction is None:
            rng = self._rng(preset)
            backaction = self._backaction_base + rng.random() * self._backaction_span

        status: ExperimentStatus
        if fidelity is not None and fidelity < 0.90:
            status = ExperimentStatus.FAIL
        elif fidelity is not None and fidelity < 0.94:
            status = ExperimentStatus.WARN
        elif backaction is not None and backaction > 0.35:
            status = ExperimentStatus.WARN
        else:
            status = ExperimentStatus.OK

        return KpiBundle(
            fidelity=fidelity,
            latency_us=latency_us,
            backaction=backaction,
            raw_counts=raw_counts,
            expected_distribution=expected_q,
            shots_used=measured_shots,
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
        start_time = time.time()

        # If a live client is configured, prefer it to ensure raw_counts/expectations
        # reflect the provider SDK response instead of synthetic draws.
        if self._live_client:
            try:
                result = self._run_live(preset, shot_budget)
                latency = max(0.0, time.time() - start_time)
                provider_metrics.record_success(self.id, latency)
                logger.info(
                    "Provider live run succeeded",
                    extra={
                        "hardware_target": self.id,
                        "vendor": self.vendor,
                        "preset": preset.value,
                        "shot_budget": shot_budget,
                        "latency_s": latency,
                    },
                )
                return result
            except ProviderClientError as exc:
                latency = max(0.0, time.time() - start_time)
                code = getattr(exc, "code", None)
                provider_metrics.record_failure(self.id, code.value if code else None, latency)
                logger.warning(
                    "Live provider execution failed",
                    extra={
                        "hardware_target": self.id,
                        "vendor": self.vendor,
                        "preset": preset.value,
                        "shot_budget": shot_budget,
                        "error_code": code.value if code else None,
                        "error_message": str(exc),
                        "latency_s": latency,
                    },
                )
                if not settings.allow_provider_simulation:
                    raise
            except Exception as exc:  # noqa: BLE001 - defensive guard for unexpected failures
                latency = max(0.0, time.time() - start_time)
                provider_metrics.record_failure(self.id, ErrorCode.PROVIDER_ERROR.value, latency)
                logger.exception(
                    "Live provider execution crashed",
                    extra={
                        "hardware_target": self.id,
                        "vendor": self.vendor,
                        "preset": preset.value,
                        "shot_budget": shot_budget,
                        "latency_s": latency,
                    },
                )
                if not settings.allow_provider_simulation:
                    raise ProviderClientError(f"Live provider call failed: {exc}") from exc

        if not settings.allow_provider_simulation:
            raise RuntimeError(
                "Provider simulation is disabled for this deployment. "
                "To exercise provider stubs in simulation mode, set SYNQC_ALLOW_PROVIDER_SIMULATION=true "
                "or provide a live provider client via SYNQC_PROVIDER_PAYLOAD_<BACKEND_ID>."
            )

        sim_start = time.time()
        result = self._simulate(preset, shot_budget)
        provider_metrics.record_simulated(self.id, max(0.0, time.time() - sim_start))
        logger.info(
            "Provider simulation path used",
            extra={
                "hardware_target": self.id,
                "vendor": self.vendor,
                "preset": preset.value,
                "shot_budget": shot_budget,
            },
        )
        return result

_PROVIDER_CLIENTS = load_provider_clients()


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
        live_client=_PROVIDER_CLIENTS.get("aws_braket"),
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
        live_client=_PROVIDER_CLIENTS.get("ibm_quantum"),
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
        live_client=_PROVIDER_CLIENTS.get("azure_quantum"),
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
        live_client=_PROVIDER_CLIENTS.get("ionq_cloud"),
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
        live_client=_PROVIDER_CLIENTS.get("rigetti_forest"),
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
