import importlib.util

import pytest

from synqc_backend.models import ExperimentPreset
from synqc_backend.provider_clients import ProviderClientError, ProviderLiveResult, load_provider_clients
from synqc_backend.qiskit_provider import QiskitProviderClient


RUNTIME_DEPENDENCIES_MISSING = (
    importlib.util.find_spec("qiskit") is None
    or importlib.util.find_spec("qiskit_ibm_runtime") is None
    or importlib.util.find_spec("qiskit_aer") is None
)


def test_qiskit_client_loaded_from_env(monkeypatch):
    monkeypatch.setenv("SYNQC_QISKIT_BACKEND_IBM_QUANTUM", "aer_simulator")
    monkeypatch.delenv("SYNQC_PROVIDER_PAYLOAD_IBM_QUANTUM", raising=False)

    clients = load_provider_clients()

    assert "ibm_quantum" in clients
    assert isinstance(clients["ibm_quantum"], QiskitProviderClient)
    assert clients["ibm_quantum"].backend_name == "aer_simulator"


def test_qiskit_client_requires_dependency(monkeypatch):
    client = QiskitProviderClient(backend_name="aer_simulator")

    if importlib.util.find_spec("qiskit") is None:
        with pytest.raises(ProviderClientError):
            client.run(ExperimentPreset.HEALTH, 50)
    else:
        result = client.run(ExperimentPreset.HEALTH, 50)
        assert result.raw_counts
        assert result.shots_used == 50


def test_qiskit_runtime_requires_dependency(monkeypatch):
    client = QiskitProviderClient(backend_name="ibm_fake_backend")

    monkeypatch.setenv("SYNQC_QISKIT_RUNTIME_TOKEN", "dummy")
    monkeypatch.delenv("SYNQC_QISKIT_RUNTIME_INSTANCE", raising=False)
    monkeypatch.delenv("SYNQC_QISKIT_RUNTIME_CHANNEL", raising=False)

    if importlib.util.find_spec("qiskit") is None or importlib.util.find_spec("qiskit_ibm_runtime") is None:
        with pytest.raises(ProviderClientError):
            client.run(ExperimentPreset.HEALTH, 10)
    else:
        # When dependencies are present, prefer Aer if available to avoid real cloud calls in unit tests.
        monkeypatch.setenv("SYNQC_QISKIT_RUNTIME_TOKEN", "")
        result = client.run(ExperimentPreset.HEALTH, 10)
        assert result.raw_counts


@pytest.mark.skipif(RUNTIME_DEPENDENCIES_MISSING, reason="Qiskit runtime dependencies are not installed")
def test_qiskit_runtime_stub_backend(monkeypatch, stub_runtime_service):
    client = QiskitProviderClient(backend_name="ibm_stub_backend")

    result = client.run(ExperimentPreset.HEALTH, 20)

    assert result.raw_counts
    assert result.shots_used == 20
    assert result.fidelity is None
    assert result.latency_us is None
    assert stub_runtime_service.last_backend_name == "ibm_stub_backend"


@pytest.mark.skipif(RUNTIME_DEPENDENCIES_MISSING, reason="Qiskit runtime dependencies are not installed")
@pytest.mark.parametrize(
    ("preset", "shots"),
    [
        (ExperimentPreset.HEALTH, 12),
        (ExperimentPreset.LATENCY, 5),
        (ExperimentPreset.DPD_DEMO, 8),
    ],
)
def test_qiskit_runtime_stub_multiple_presets(monkeypatch, stub_runtime_service, preset, shots):
    client = QiskitProviderClient(backend_name="ibm_stub_backend")

    result = client.run(preset, shots)

    assert result.raw_counts
    assert result.shots_used == shots
    assert result.fidelity is None
    assert result.latency_us is None
    assert stub_runtime_service.last_backend_name == "ibm_stub_backend"


def test_qiskit_grover_cap_when_no_success(monkeypatch):
    client = QiskitProviderClient(backend_name="ibm_stub_backend")

    executed_shots: list[int] = []

    monkeypatch.setattr(QiskitProviderClient, "_ensure_qiskit_available", lambda self, use_runtime: None)
    monkeypatch.setattr(QiskitProviderClient, "_runtime_configured", lambda self: False)
    monkeypatch.setattr("synqc_backend.qiskit_provider.grover_utils.build_grover_circuit", lambda cfg: object())

    def _fake_execute(self, preset, circuit, shots: int, *, use_runtime: bool):
        executed_shots.append(shots)
        # Always return low success probability counts
        raw_counts = {"00": shots}
        return ProviderLiveResult(raw_counts=raw_counts, expected_distribution=None, shots_used=shots)

    monkeypatch.setattr(QiskitProviderClient, "_execute", _fake_execute, raising=False)

    result = client.run(ExperimentPreset.GROVER_DEMO, 64)

    assert result.raw_counts
    assert result.shots_used == 64
    assert executed_shots[-1] == 64
    assert result.fidelity is not None
    assert result.fidelity < 0.9
