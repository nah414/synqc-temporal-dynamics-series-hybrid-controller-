import pytest

from synqc_backend import providers
from synqc_backend.config import settings
from synqc_backend.hardware_backends import ProviderBackend
from synqc_backend.models import ExperimentPreset
from synqc_backend.provider_clients import (
    AzureQuantumStubClient,
    IonqProviderClient,
    RigettiForestStubClient,
)


class _ValidatingClient:
    def __init__(self, *, valid: bool, raise_error: bool = False):
        self.valid = valid
        self.raise_error = raise_error
        self.calls = 0

    def validate_credentials(self) -> bool:
        self.calls += 1
        if self.raise_error:
            raise RuntimeError("unexpected validation failure")
        return self.valid

    def run(self, preset: ExperimentPreset, shot_budget: int):  # pragma: no cover - not used
        raise AssertionError("run should not be invoked in credential validation tests")


def _backend_with_client(client: _ValidatingClient) -> ProviderBackend:
    return ProviderBackend(
        id="aws_braket",
        name="AWS Braket",
        kind="superconducting",
        vendor="aws",
        fidelity_floor=0.9,
        fidelity_ceiling=0.99,
        latency_base_us=10.0,
        latency_span_us=5.0,
        backaction_base=0.1,
        backaction_span=0.05,
        live_client=client,
    )


def test_validate_credentials_respects_live_client_result(monkeypatch):
    client = _ValidatingClient(valid=False)
    backend = _backend_with_client(client)

    monkeypatch.setattr("synqc_backend.hardware_backends.get_backend", lambda _target: backend)

    assert providers.validate_credentials("aws_braket") is False
    assert client.calls == 1


def test_validate_credentials_handles_live_client_errors(monkeypatch):
    client = _ValidatingClient(valid=True, raise_error=True)
    backend = _backend_with_client(client)

    monkeypatch.setattr("synqc_backend.hardware_backends.get_backend", lambda _target: backend)

    assert providers.validate_credentials("aws_braket") is False
    assert client.calls == 1


def test_validate_credentials_falls_back_to_simulation_flag(monkeypatch):
    backend = ProviderBackend(
        id="ionq_cloud",
        name="IonQ Cloud",
        kind="ion_trap",
        vendor="ionq",
        fidelity_floor=0.9,
        fidelity_ceiling=0.99,
        latency_base_us=10.0,
        latency_span_us=5.0,
        backaction_base=0.1,
        backaction_span=0.05,
        live_client=None,
    )

    monkeypatch.setattr("synqc_backend.hardware_backends.get_backend", lambda _target: backend)
    monkeypatch.setattr(settings, "allow_provider_simulation", True, raising=False)

    assert providers.validate_credentials("ionq_cloud") is True


def test_validate_credentials_requires_auth_when_simulation_disabled(monkeypatch):
    backend = ProviderBackend(
        id="ionq_cloud",
        name="IonQ Cloud",
        kind="ion_trap",
        vendor="ionq",
        fidelity_floor=0.9,
        fidelity_ceiling=0.99,
        latency_base_us=10.0,
        latency_span_us=5.0,
        backaction_base=0.1,
        backaction_span=0.05,
        live_client=None,
    )

    monkeypatch.setattr("synqc_backend.hardware_backends.get_backend", lambda _target: backend)
    monkeypatch.setattr(settings, "allow_provider_simulation", False, raising=False)

    assert providers.validate_credentials("ionq_cloud") is False


@pytest.mark.parametrize(
    "client_factory, expected",
    [
        (lambda: IonqProviderClient(api_key="token"), True),
        (lambda: IonqProviderClient(api_key=None), False),
        (lambda: AzureQuantumStubClient(access_token="abc"), True),
        (lambda: AzureQuantumStubClient(access_token=None), False),
        (lambda: RigettiForestStubClient(api_key="rk"), True),
        (lambda: RigettiForestStubClient(api_key=None), False),
    ],
)
def test_validate_credentials_exercises_live_provider_clients(monkeypatch, client_factory, expected):
    client = client_factory()
    backend = ProviderBackend(
        id="rigetti_forest",
        name="Rigetti Forest",
        kind="superconducting",
        vendor="rigetti",
        fidelity_floor=0.9,
        fidelity_ceiling=0.99,
        latency_base_us=10.0,
        latency_span_us=5.0,
        backaction_base=0.1,
        backaction_span=0.05,
        live_client=client,
    )

    monkeypatch.setattr("synqc_backend.hardware_backends.get_backend", lambda _target: backend)
    monkeypatch.setattr(settings, "allow_provider_simulation", False, raising=False)

    assert providers.validate_credentials("rigetti_forest") is expected
