from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Dict, Optional, Protocol

import random

from .models import ErrorCode, ExperimentPreset
from .stats import Counts


logger = logging.getLogger(__name__)


class ProviderClientError(RuntimeError):
    """Raised when provider client payloads cannot be loaded or validated."""

    def __init__(
        self,
        message: str,
        *,
        code: Optional[ErrorCode] = None,
        action_hint: str | None = None,
        detail: dict | None = None,
    ) -> None:
        self.code = code or ErrorCode.PROVIDER_ERROR
        self.action_hint = action_hint
        self.detail = detail or {}
        super().__init__(message)


@dataclass
class ProviderLiveResult:
    """Structured response extracted from a provider SDK call."""

    raw_counts: Counts
    expected_distribution: Dict[str, float] | None = None
    fidelity: float | None = None
    latency_us: float | None = None
    backaction: float | None = None
    shots_used: int | None = None


class BaseProviderClient(Protocol):
    """Adapter that translates provider SDK results into SynQc-ready data."""

    def run(self, preset: ExperimentPreset, shot_budget: int) -> ProviderLiveResult:  # pragma: no cover - interface
        ...


class FilePayloadProviderClient:
    """Lightweight adapter that reads provider payloads from disk or env strings."""

    def __init__(self, payload: str) -> None:
        self._payload = payload

    def _load(self) -> dict:
        # If the payload points to a file, load it; otherwise treat as inline JSON
        try:
            if os.path.exists(self._payload):
                with open(self._payload, "r", encoding="utf-8") as f:
                    return json.load(f)
            return json.loads(self._payload)
        except (OSError, json.JSONDecodeError) as exc:
            raise ProviderClientError(f"Failed to load provider payload from {self._payload!r}") from exc

    def run(self, preset: ExperimentPreset, shot_budget: int) -> ProviderLiveResult:
        data = self._load()
        raw_counts = data.get("raw_counts") or {}
        expected_distribution = data.get("expected_distribution")
        fidelity = data.get("fidelity")
        latency_us = data.get("latency_us")
        backaction = data.get("backaction")
        shots_used = data.get("shots_used")

        # Normalize keys/values to expected types
        try:
            normalized_counts: Counts = {str(k): int(v) for k, v in raw_counts.items()}
        except Exception as exc:
            raise ProviderClientError("Invalid raw_counts in provider payload") from exc

        return ProviderLiveResult(
            raw_counts=normalized_counts,
            expected_distribution=expected_distribution,
            fidelity=fidelity,
            latency_us=latency_us,
            backaction=backaction,
            shots_used=shots_used,
        )


class IonqProviderClient:
    """IonQ-flavored provider adapter with an optional API key."""

    backend_name = "ionq_qpu"

    def __init__(self, api_key: str | None = None, *, fallback_backend: str | None = None) -> None:
        self.api_key = api_key
        if fallback_backend:
            self.backend_name = fallback_backend

    def validate_credentials(self) -> bool:
        return bool(self.api_key)

    def _expected_distribution(self, preset: ExperimentPreset) -> Dict[str, float]:
        if preset is ExperimentPreset.LATENCY:
            return {"00": 0.45, "01": 0.25, "10": 0.18, "11": 0.12}
        if preset is ExperimentPreset.BACKEND_COMPARE:
            return {"00": 0.48, "01": 0.19, "10": 0.19, "11": 0.14}
        if preset is ExperimentPreset.HELLO_QUANTUM_SIM:
            return {"00": 0.66, "01": 0.17, "10": 0.11, "11": 0.06}
        return {"00": 0.6, "01": 0.2, "10": 0.12, "11": 0.08}

    def _sample_counts(self, dist: Dict[str, float], shots: int, rng: random.Random) -> Counts:
        outcomes = list(dist.keys())
        weights = [dist[o] for o in outcomes]
        draws = rng.choices(outcomes, weights=weights, k=shots)
        counts: Counts = {o: 0 for o in outcomes}
        for d in draws:
            counts[d] += 1
        return counts

    def run(self, preset: ExperimentPreset, shot_budget: int) -> ProviderLiveResult:
        seed = hash((preset.value, shot_budget, self.backend_name)) & 0xFFFFFFFF
        rng = random.Random(seed)

        expected = self._expected_distribution(preset)
        shots_used = max(1, min(shot_budget, 100000))
        raw_counts = self._sample_counts(expected, shots_used, rng)

        fidelity = 0.93 + rng.random() * 0.05
        latency_us = 85.0 + rng.random() * 180.0
        backaction = 0.11 + rng.random() * 0.12

        return ProviderLiveResult(
            raw_counts=raw_counts,
            expected_distribution=expected,
            fidelity=fidelity,
            latency_us=latency_us,
            backaction=backaction,
            shots_used=shots_used,
        )


class AzureQuantumStubClient:
    """Lightweight Azure Quantum-flavored stub that enforces credentials."""

    backend_name = "azure_ionq_stub"

    def __init__(
        self,
        *,
        access_token: str | None,
        queue_busy: bool = False,
    ) -> None:
        self.access_token = access_token
        self.queue_busy = queue_busy

    def validate_credentials(self) -> bool:
        return bool(self.access_token)

    def _expected_distribution(self, preset: ExperimentPreset) -> Dict[str, float]:
        if preset is ExperimentPreset.LATENCY:
            return {"00": 0.52, "01": 0.18, "10": 0.17, "11": 0.13}
        if preset is ExperimentPreset.BACKEND_COMPARE:
            return {"00": 0.41, "01": 0.21, "10": 0.2, "11": 0.18}
        if preset is ExperimentPreset.HELLO_QUANTUM_SIM:
            return {"00": 0.68, "01": 0.18, "10": 0.09, "11": 0.05}
        return {"00": 0.6, "01": 0.22, "10": 0.1, "11": 0.08}

    def _sample_counts(self, dist: Dict[str, float], shots: int, rng: random.Random) -> Counts:
        outcomes = list(dist.keys())
        weights = [dist[o] for o in outcomes]
        draws = rng.choices(outcomes, weights=weights, k=shots)
        counts: Counts = {o: 0 for o in outcomes}
        for d in draws:
            counts[d] += 1
        return counts

    def run(self, preset: ExperimentPreset, shot_budget: int) -> ProviderLiveResult:
        if not self.access_token:
            raise ProviderClientError(
                "Azure Quantum credentials missing.",
                code=ErrorCode.PROVIDER_CREDENTIALS,
                action_hint="Set SYNQC_AZURE_API_KEY to enable Azure Quantum runs.",
            )

        if self.queue_busy:
            raise ProviderClientError(
                "Azure Quantum queue is currently busy.",
                code=ErrorCode.PROVIDER_QUEUE_BACKPRESSURE,
                action_hint="Wait for capacity or target a different backend.",
            )

        rng = random.Random(hash((preset.value, shot_budget, self.backend_name)) & 0xFFFFFFFF)
        expected = self._expected_distribution(preset)
        shots_used = max(1, min(shot_budget, 500000))
        raw_counts = self._sample_counts(expected, shots_used, rng)

        fidelity = 0.92 + rng.random() * 0.05
        latency_us = 140.0 + rng.random() * 120.0
        backaction = 0.13 + rng.random() * 0.10

        return ProviderLiveResult(
            raw_counts=raw_counts,
            expected_distribution=expected,
            fidelity=fidelity,
            latency_us=latency_us,
            backaction=backaction,
            shots_used=shots_used,
        )


class RigettiForestStubClient:
    """Lightweight Rigetti-flavored stub with credential and capacity guards."""

    backend_name = "rigetti_aspen_stub"

    def __init__(
        self,
        *,
        api_key: str | None,
        capacity_exhausted: bool = False,
    ) -> None:
        self.api_key = api_key
        self.capacity_exhausted = capacity_exhausted

    def validate_credentials(self) -> bool:
        return bool(self.api_key)

    def _expected_distribution(self, preset: ExperimentPreset) -> Dict[str, float]:
        if preset is ExperimentPreset.LATENCY:
            return {"00": 0.5, "01": 0.2, "10": 0.16, "11": 0.14}
        if preset is ExperimentPreset.BACKEND_COMPARE:
            return {"00": 0.46, "01": 0.18, "10": 0.19, "11": 0.17}
        if preset is ExperimentPreset.HELLO_QUANTUM_SIM:
            return {"00": 0.65, "01": 0.16, "10": 0.13, "11": 0.06}
        return {"00": 0.58, "01": 0.24, "10": 0.1, "11": 0.08}

    def _sample_counts(self, dist: Dict[str, float], shots: int, rng: random.Random) -> Counts:
        outcomes = list(dist.keys())
        weights = [dist[o] for o in outcomes]
        draws = rng.choices(outcomes, weights=weights, k=shots)
        counts: Counts = {o: 0 for o in outcomes}
        for d in draws:
            counts[d] += 1
        return counts

    def run(self, preset: ExperimentPreset, shot_budget: int) -> ProviderLiveResult:
        if not self.api_key:
            raise ProviderClientError(
                "Rigetti Forest credentials missing.",
                code=ErrorCode.PROVIDER_CREDENTIALS,
                action_hint="Set SYNQC_RIGETTI_API_KEY to enable Rigetti runs.",
            )

        if self.capacity_exhausted:
            raise ProviderClientError(
                "Rigetti Forest capacity exhausted for the selected region.",
                code=ErrorCode.PROVIDER_CAPACITY,
                action_hint="Retry later or route to a simulator.",
            )

        rng = random.Random(hash((preset.value, shot_budget, self.backend_name)) & 0xFFFFFFFF)
        expected = self._expected_distribution(preset)
        shots_used = max(1, min(shot_budget, 100000))
        raw_counts = self._sample_counts(expected, shots_used, rng)

        fidelity = 0.91 + rng.random() * 0.05
        latency_us = 60.0 + rng.random() * 160.0
        backaction = 0.14 + rng.random() * 0.09

        return ProviderLiveResult(
            raw_counts=raw_counts,
            expected_distribution=expected,
            fidelity=fidelity,
            latency_us=latency_us,
            backaction=backaction,
            shots_used=shots_used,
        )


def load_provider_clients() -> dict[str, BaseProviderClient]:
    """Load provider adapters from environment configuration.

    Each provider backend id can be paired with an environment variable of the form
    ``SYNQC_PROVIDER_PAYLOAD_<BACKEND_ID>`` that points to either a JSON file path or
    an inline JSON string containing counts/expectations produced by the provider SDK.
    """

    clients: dict[str, BaseProviderClient] = {}
    payload_prefix = "SYNQC_PROVIDER_PAYLOAD_"
    for key, value in os.environ.items():
        if not key.startswith(payload_prefix):
            continue
        backend_id = key[len(payload_prefix) :].lower()
        if not value:
            continue
        try:
            clients[backend_id] = FilePayloadProviderClient(value)
        except Exception:
            # Keep failing entries isolated to avoid disrupting unrelated backends,
            # but surface the failure for observability.
            logger.exception(
                "Failed to initialize provider client for backend '%s' from env var '%s'",
                backend_id,
                key,
            )
            continue

    qiskit_prefix = "SYNQC_QISKIT_BACKEND_"
    for key, backend_name in os.environ.items():
        if not key.startswith(qiskit_prefix):
            continue

        backend_id = key[len(qiskit_prefix) :].lower()
        if not backend_name:
            continue

        try:
            from .qiskit_provider import QiskitProviderClient

            clients[backend_id] = QiskitProviderClient(backend_name=backend_name)
        except Exception:
            logger.exception(
                "Failed to initialize Qiskit provider client for backend '%s' from env var '%s'",
                backend_id,
                key,
            )
            continue

    ionq_api_key = os.environ.get("SYNQC_IONQ_API_KEY")
    enable_ionq_demo = os.environ.get("SYNQC_ENABLE_IONQ_DEMO")
    if ionq_api_key or (enable_ionq_demo and enable_ionq_demo.lower() in {"1", "true", "yes"}):
        clients["ionq_cloud"] = IonqProviderClient(api_key=ionq_api_key)

    enable_azure_stub = os.environ.get("SYNQC_ENABLE_AZURE_SDK_STUB")
    if enable_azure_stub and enable_azure_stub.lower() in {"1", "true", "yes"}:
        clients["azure_quantum"] = AzureQuantumStubClient(
            access_token=os.environ.get("SYNQC_AZURE_API_KEY"),
            queue_busy=os.environ.get("SYNQC_AZURE_QUEUE_BUSY", "").lower() in {"1", "true", "yes"},
        )

    enable_rigetti_stub = os.environ.get("SYNQC_ENABLE_RIGETTI_SDK_STUB")
    if enable_rigetti_stub and enable_rigetti_stub.lower() in {"1", "true", "yes"}:
        clients["rigetti_forest"] = RigettiForestStubClient(
            api_key=os.environ.get("SYNQC_RIGETTI_API_KEY"),
            capacity_exhausted=os.environ.get("SYNQC_RIGETTI_CAPACITY_EXHAUSTED", "").lower()
            in {"1", "true", "yes"},
        )

    if "ibm_quantum" not in clients:
        # Default to Aer simulator; callers can override with SYNQC_QISKIT_BACKEND or runtime env vars.
        try:
            from .qiskit_provider import QiskitProviderClient

            backend_name = os.environ.get("SYNQC_QISKIT_BACKEND", "aer_simulator")
            clients["ibm_quantum"] = QiskitProviderClient(backend_name=backend_name)
        except Exception:
            logger.debug("Qiskit provider not initialized; falling back to simulation-only ibm_quantum shell")

    return clients
