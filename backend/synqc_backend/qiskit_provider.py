"""Qiskit-backed provider client for SynQc experiments.

This adapter keeps Qiskit as an optional dependency while providing a
structured path to run SynQc presets on Aer simulators or IBM Quantum
backends. Circuit shapes are intentionally lightweight: they prioritize
repeatability and a clear measurement basis over cutting-edge physics so
that KPI extraction downstream stays stable.
"""
from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from typing import Dict

from .models import ErrorCode, ExperimentPreset
from .provider_clients import BaseProviderClient, ProviderClientError, ProviderLiveResult
from .stats import Counts


_EXPECTED_BASELINES: Dict[ExperimentPreset, Dict[str, float]] = {
    ExperimentPreset.HEALTH: {"00": 0.64, "11": 0.28, "01": 0.05, "10": 0.03},
    ExperimentPreset.LATENCY: {"00": 0.55, "01": 0.22, "10": 0.14, "11": 0.09},
    ExperimentPreset.BACKEND_COMPARE: {"00": 0.42, "01": 0.22, "10": 0.2, "11": 0.16},
    ExperimentPreset.HELLO_QUANTUM_SIM: {"00": 0.7, "01": 0.15, "10": 0.1, "11": 0.05},
    ExperimentPreset.DPD_DEMO: {"00": 0.64, "11": 0.28, "01": 0.05, "10": 0.03},
}


@dataclass(slots=True)
class QiskitProviderClient(BaseProviderClient):
    """Adapter that runs SynQc presets with Qiskit backends.

    The client targets Aer simulators by default ("aer_simulator") but can be
    pointed at any Qiskit backend name available in the environment. Expected
    distributions mirror the backend shells in ``hardware_backends`` so
    fidelity can be derived consistently when the live SDK does not return it
    directly.
    """

    backend_name: str
    optimization_level: int = 1

    def _runtime_configured(self) -> bool:
        """Detect whether runtime credentials are present for cloud execution."""

        return any(
            os.environ.get(env_key)
            for env_key in (
                "SYNQC_QISKIT_RUNTIME_TOKEN",
                "SYNQC_QISKIT_RUNTIME_CHANNEL",
                "SYNQC_QISKIT_RUNTIME_INSTANCE",
            )
        )

    def _ensure_qiskit_available(self, *, use_runtime: bool) -> None:
        if importlib.util.find_spec("qiskit") is None:
            raise ProviderClientError(
                "Qiskit is not installed. Install the 'qiskit' extra to enable Qiskit-backed runs.",
                code=ErrorCode.PROVIDER_CREDENTIALS,
                action_hint="Install qiskit or switch to a simulator backend.",
            )

        if use_runtime:
            if importlib.util.find_spec("qiskit_ibm_runtime") is None:
                raise ProviderClientError(
                    "qiskit-ibm-runtime is required for cloud execution. Install the 'qiskit' extra or add it manually.",
                    code=ErrorCode.PROVIDER_CREDENTIALS,
                    action_hint="Install qiskit-ibm-runtime or select Aer simulation.",
                )
            return

        if importlib.util.find_spec("qiskit_aer") is None:
            raise ProviderClientError(
                "qiskit-aer is required for the configured Qiskit backend. Install the 'qiskit' extra.",
                code=ErrorCode.PROVIDER_CREDENTIALS,
                action_hint="Install qiskit-aer or target a runtime backend.",
            )

    def validate_credentials(self) -> bool:
        """Lightweight validation that required packages and secrets are present."""

        use_runtime = self._runtime_configured()
        try:
            self._ensure_qiskit_available(use_runtime=use_runtime)
        except ProviderClientError:
            return False

        if use_runtime:
            return bool(os.environ.get("SYNQC_QISKIT_RUNTIME_TOKEN"))

        return True

    def _resolve_backend(self, *, use_runtime: bool):
        if use_runtime:
            from qiskit_ibm_runtime import QiskitRuntimeService

            service_kwargs = {}
            if os.environ.get("SYNQC_QISKIT_RUNTIME_TOKEN"):
                service_kwargs["token"] = os.environ["SYNQC_QISKIT_RUNTIME_TOKEN"]
            if os.environ.get("SYNQC_QISKIT_RUNTIME_CHANNEL"):
                service_kwargs["channel"] = os.environ["SYNQC_QISKIT_RUNTIME_CHANNEL"]
            if os.environ.get("SYNQC_QISKIT_RUNTIME_INSTANCE"):
                service_kwargs["instance"] = os.environ["SYNQC_QISKIT_RUNTIME_INSTANCE"]

            service = QiskitRuntimeService(**service_kwargs)
            return service.backend(self.backend_name)

        from qiskit_aer import Aer

        return Aer.get_backend(self.backend_name)

    def _expected_distribution(self, preset: ExperimentPreset) -> Dict[str, float]:
        return _EXPECTED_BASELINES.get(preset, _EXPECTED_BASELINES[ExperimentPreset.DPD_DEMO])

    def _build_circuit(self, preset: ExperimentPreset):
        # Imports are deferred to keep the dependency optional until runtime.
        from qiskit import QuantumCircuit

        circuit = QuantumCircuit(2, 2)

        if preset is ExperimentPreset.HEALTH:
            circuit.h(0)
            circuit.cx(0, 1)
            circuit.ry(0.35, 0)
            circuit.ry(0.15, 1)
        elif preset is ExperimentPreset.LATENCY:
            circuit.x(0)
            circuit.delay(100, 0, unit="dt")
            circuit.h(1)
        elif preset is ExperimentPreset.BACKEND_COMPARE:
            circuit.h(0)
            circuit.h(1)
            circuit.cz(0, 1)
            circuit.rx(0.2, 0)
        else:  # DPD_DEMO or unknown
            circuit.h(0)
            circuit.cx(0, 1)
            circuit.rx(0.1, 0)
            circuit.ry(0.2, 1)

        circuit.measure([0, 1], [0, 1])
        return circuit

    def run(self, preset: ExperimentPreset, shot_budget: int) -> ProviderLiveResult:
        use_runtime = self._runtime_configured()
        try:
            self._ensure_qiskit_available(use_runtime=use_runtime)

            from qiskit import transpile

            shots = max(1, int(shot_budget))
            circuit = self._build_circuit(preset)

            backend = self._resolve_backend(use_runtime=use_runtime)

            if use_runtime:
                execution_backend = backend
            else:
                from qiskit_aer import AerSimulator

                execution_backend = (
                    backend if isinstance(backend, AerSimulator) else AerSimulator.from_backend(backend)
                )

            compiled = transpile(circuit, execution_backend, optimization_level=self.optimization_level)
            job = execution_backend.run(compiled, shots=shots)
            result = job.result()
            counts_raw = result.get_counts()  # type: ignore[assignment]

            counts: Counts = {str(k): int(v) for k, v in counts_raw.items()}
            expected_distribution = self._expected_distribution(preset)

            return ProviderLiveResult(
                raw_counts=counts,
                expected_distribution=expected_distribution,
                shots_used=shots,
                fidelity=None,
                latency_us=None,
                backaction=None,
            )
        except ProviderClientError:
            raise
        except Exception as exc:  # noqa: BLE001 - map provider failures into taxonomy
            message = str(exc)
            lower_msg = message.lower()
            code = ErrorCode.PROVIDER_ERROR
            action_hint = "Retry later or switch to Aer simulation."
            if "credential" in lower_msg or "token" in lower_msg:
                code = ErrorCode.PROVIDER_CREDENTIALS
                action_hint = "Set SYNQC_QISKIT_RUNTIME_TOKEN or run with Aer simulation."
            elif "queue" in lower_msg or "busy" in lower_msg:
                code = ErrorCode.PROVIDER_QUEUE_BACKPRESSURE
                action_hint = "Wait for capacity or select a different backend."

            raise ProviderClientError(message, code=code, action_hint=action_hint)
