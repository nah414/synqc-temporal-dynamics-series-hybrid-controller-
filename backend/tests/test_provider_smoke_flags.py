import importlib
import os

import pytest

from synqc_backend import provider_clients
from synqc_backend.models import ErrorCode, ExperimentPreset


pytestmark = pytest.mark.skipif(
    not os.getenv("SYNQC_ENABLE_PROVIDER_SMOKE"),
    reason="Provider smoke tests require SYNQC_ENABLE_PROVIDER_SMOKE",
)


@pytest.fixture
def reload_backends(monkeypatch):
    mutated_env_keys = [
        "SYNQC_PROVIDER_PAYLOAD_AWS_BRAKET",
        "SYNQC_PROVIDER_PAYLOAD_AZURE_QUANTUM",
        "SYNQC_PROVIDER_PAYLOAD_RIGETTI_FOREST",
        "SYNQC_ENABLE_IONQ_DEMO",
        "SYNQC_ENABLE_AZURE_SMOKE",
        "SYNQC_ENABLE_RIGETTI_SMOKE",
        "SYNQC_ENABLE_AZURE_SDK_STUB",
        "SYNQC_ENABLE_RIGETTI_SDK_STUB",
        "SYNQC_AZURE_API_KEY",
        "SYNQC_RIGETTI_API_KEY",
        "SYNQC_AZURE_QUEUE_BUSY",
        "SYNQC_RIGETTI_CAPACITY_EXHAUSTED",
        "SYNQC_ALLOW_PROVIDER_SIMULATION",
    ]

    def _reload(env: dict[str, str]):
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        import synqc_backend.provider_clients as provider_clients
        import synqc_backend.hardware_backends as hardware_backends

        importlib.reload(provider_clients)
        importlib.reload(hardware_backends)
        return hardware_backends

    yield _reload

    for key in mutated_env_keys:
        monkeypatch.delenv(key, raising=False)

    import synqc_backend.provider_clients as provider_clients
    import synqc_backend.hardware_backends as hardware_backends

    importlib.reload(provider_clients)
    importlib.reload(hardware_backends)


def test_braket_payload_live_path(monkeypatch, reload_backends):
    env = {
        "SYNQC_PROVIDER_PAYLOAD_AWS_BRAKET": '{"raw_counts":{"00":4,"11":6},"expected_distribution":{"00":0.4,"11":0.6}}',
        "SYNQC_ALLOW_PROVIDER_SIMULATION": "true",
    }
    hardware_backends = reload_backends(env)
    backend = hardware_backends.get_backend("aws_braket")

    assert backend._live_client is not None

    bundle = backend.run_experiment(ExperimentPreset.HELLO_QUANTUM_SIM, shot_budget=10)
    assert bundle.raw_counts == {"00": 4, "11": 6}
    assert bundle.expected_distribution and pytest.approx(0.6, rel=1e-6) == bundle.expected_distribution.get("11")
    assert bundle.shots_used == 10


@pytest.mark.skipif(
    not os.getenv("SYNQC_ENABLE_AZURE_SMOKE"),
    reason="Azure smoke requires SYNQC_ENABLE_AZURE_SMOKE",
)
def test_azure_payload_live_path(monkeypatch, reload_backends):
    env = {
        "SYNQC_PROVIDER_PAYLOAD_AZURE_QUANTUM": '{"raw_counts":{"00":8,"11":12},"expected_distribution":{"00":0.4,"11":0.6},"shots_used":20}',
        "SYNQC_ALLOW_PROVIDER_SIMULATION": "true",
    }
    hardware_backends = reload_backends(env)
    backend = hardware_backends.get_backend("azure_quantum")

    assert backend._live_client is not None

    bundle = backend.run_experiment(ExperimentPreset.HELLO_QUANTUM_SIM, shot_budget=20)
    assert bundle.raw_counts == {"00": 8, "11": 12}
    assert bundle.expected_distribution and pytest.approx(0.6, rel=1e-6) == bundle.expected_distribution.get("11")
    assert bundle.shots_used == 20


def test_ionq_demo_live_client(monkeypatch, reload_backends):
    env = {
        "SYNQC_ENABLE_IONQ_DEMO": "true",
        "SYNQC_ALLOW_PROVIDER_SIMULATION": "true",
    }
    hardware_backends = reload_backends(env)
    backend = hardware_backends.get_backend("ionq_cloud")

    assert backend._live_client is not None

    bundle = backend.run_experiment(ExperimentPreset.BACKEND_COMPARE, shot_budget=64)
    assert bundle.raw_counts
    assert bundle.expected_distribution
    assert bundle.shots_used == 64


@pytest.mark.skipif(
    not os.getenv("SYNQC_ENABLE_RIGETTI_SMOKE"),
    reason="Rigetti smoke requires SYNQC_ENABLE_RIGETTI_SMOKE",
)
def test_rigetti_payload_live_path(monkeypatch, reload_backends):
    env = {
        "SYNQC_PROVIDER_PAYLOAD_RIGETTI_FOREST": '{"raw_counts":{"00":14,"01":6},"expected_distribution":{"00":0.7,"01":0.3},"shots_used":20}',
        "SYNQC_ALLOW_PROVIDER_SIMULATION": "true",
    }
    hardware_backends = reload_backends(env)
    backend = hardware_backends.get_backend("rigetti_forest")

    assert backend._live_client is not None

    bundle = backend.run_experiment(ExperimentPreset.BACKEND_COMPARE, shot_budget=20)
    assert bundle.raw_counts == {"00": 14, "01": 6}
    assert bundle.expected_distribution and pytest.approx(0.7, rel=1e-6) == bundle.expected_distribution.get("00")
    assert bundle.shots_used == 20


@pytest.mark.skipif(
    not os.getenv("SYNQC_ENABLE_AZURE_SMOKE"),
    reason="Azure smoke requires SYNQC_ENABLE_AZURE_SMOKE",
)
def test_azure_stub_requires_credentials(monkeypatch, reload_backends):
    env = {
        "SYNQC_ENABLE_AZURE_SDK_STUB": "true",
        "SYNQC_ALLOW_PROVIDER_SIMULATION": "true",
    }
    hardware_backends = reload_backends(env)
    backend = hardware_backends.get_backend("azure_quantum")

    assert backend._live_client is not None
    with pytest.raises(provider_clients.ProviderClientError) as excinfo:
        backend._live_client.run(ExperimentPreset.HELLO_QUANTUM_SIM, shot_budget=8)

    assert excinfo.value.code == ErrorCode.PROVIDER_CREDENTIALS


@pytest.mark.skipif(
    not os.getenv("SYNQC_ENABLE_AZURE_SMOKE"),
    reason="Azure smoke requires SYNQC_ENABLE_AZURE_SMOKE",
)
def test_azure_stub_queue_backpressure(monkeypatch, reload_backends):
    env = {
        "SYNQC_ENABLE_AZURE_SDK_STUB": "true",
        "SYNQC_AZURE_API_KEY": "fake-token",
        "SYNQC_AZURE_QUEUE_BUSY": "true",
        "SYNQC_ALLOW_PROVIDER_SIMULATION": "true",
    }
    hardware_backends = reload_backends(env)
    backend = hardware_backends.get_backend("azure_quantum")

    assert backend._live_client is not None
    with pytest.raises(provider_clients.ProviderClientError) as excinfo:
        backend._live_client.run(ExperimentPreset.HELLO_QUANTUM_SIM, shot_budget=8)

    assert excinfo.value.code == ErrorCode.PROVIDER_QUEUE_BACKPRESSURE


@pytest.mark.skipif(
    not os.getenv("SYNQC_ENABLE_RIGETTI_SMOKE"),
    reason="Rigetti smoke requires SYNQC_ENABLE_RIGETTI_SMOKE",
)
def test_rigetti_stub_happy_path(monkeypatch, reload_backends):
    env = {
        "SYNQC_ENABLE_RIGETTI_SDK_STUB": "true",
        "SYNQC_RIGETTI_API_KEY": "rigetti-demo",
        "SYNQC_ALLOW_PROVIDER_SIMULATION": "true",
    }
    hardware_backends = reload_backends(env)
    backend = hardware_backends.get_backend("rigetti_forest")

    bundle = backend.run_experiment(ExperimentPreset.BACKEND_COMPARE, shot_budget=12)
    assert bundle.raw_counts
    assert bundle.shots_used == 12


@pytest.mark.skipif(
    not os.getenv("SYNQC_ENABLE_RIGETTI_SMOKE"),
    reason="Rigetti smoke requires SYNQC_ENABLE_RIGETTI_SMOKE",
)
def test_rigetti_stub_capacity_guard(monkeypatch, reload_backends):
    env = {
        "SYNQC_ENABLE_RIGETTI_SDK_STUB": "true",
        "SYNQC_RIGETTI_API_KEY": "rigetti-demo",
        "SYNQC_RIGETTI_CAPACITY_EXHAUSTED": "true",
        "SYNQC_ALLOW_PROVIDER_SIMULATION": "true",
    }
    hardware_backends = reload_backends(env)
    backend = hardware_backends.get_backend("rigetti_forest")

    assert backend._live_client is not None
    with pytest.raises(provider_clients.ProviderClientError) as excinfo:
        backend._live_client.run(ExperimentPreset.BACKEND_COMPARE, shot_budget=12)

    assert excinfo.value.code == ErrorCode.PROVIDER_CAPACITY
