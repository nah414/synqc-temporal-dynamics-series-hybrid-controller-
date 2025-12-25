from __future__ import annotations

import logging
from unittest import mock

import pytest

from synqc_backend import hardware_backends
from synqc_backend.config import settings
from synqc_backend.hardware_backends import ProviderBackend
from synqc_backend.metrics_recorder import provider_metrics
from synqc_backend.models import ErrorCode, ExperimentPreset
from synqc_backend.provider_clients import ProviderClientError, ProviderLiveResult


class _HappyClient:
    backend_name = "happy_stub"

    def run(self, preset: ExperimentPreset, shot_budget: int) -> ProviderLiveResult:
        return ProviderLiveResult(
            raw_counts={"00": shot_budget},
            expected_distribution={"00": 1.0},
            shots_used=shot_budget,
        )


class _FailingClient:
    backend_name = "failing_stub"

    def run(self, preset: ExperimentPreset, shot_budget: int) -> ProviderLiveResult:
        raise ProviderClientError(
            "Queue is overloaded",
            code=ErrorCode.PROVIDER_QUEUE_BACKPRESSURE,
            action_hint="Wait or switch backends",
        )


def _provider_backend(live_client) -> ProviderBackend:
    return ProviderBackend(
        id="test_provider",
        name="Test Provider",
        kind="trapped_ion",
        vendor="stub-vendor",
        fidelity_floor=0.9,
        fidelity_ceiling=0.99,
        latency_base_us=10.0,
        latency_span_us=5.0,
        backaction_base=0.1,
        backaction_span=0.05,
        live_client=live_client,
    )


def test_provider_live_success_records_metrics(monkeypatch):
    backend = _provider_backend(_HappyClient())

    success = mock.Mock()
    failure = mock.Mock()
    simulated = mock.Mock()
    monkeypatch.setattr(provider_metrics, "record_success", success)
    monkeypatch.setattr(provider_metrics, "record_failure", failure)
    monkeypatch.setattr(provider_metrics, "record_simulated", simulated)

    result = backend.run_experiment(ExperimentPreset.HELLO_QUANTUM_SIM, shot_budget=4)

    assert result.shots_used == 4
    success.assert_called_once()
    failure.assert_not_called()
    simulated.assert_not_called()


def test_provider_live_failure_logs_and_falls_back(monkeypatch, caplog):
    backend = _provider_backend(_FailingClient())

    success = mock.Mock()
    failure = mock.Mock()
    simulated = mock.Mock()
    monkeypatch.setattr(provider_metrics, "record_success", success)
    monkeypatch.setattr(provider_metrics, "record_failure", failure)
    monkeypatch.setattr(provider_metrics, "record_simulated", simulated)
    monkeypatch.setattr(settings, "allow_provider_simulation", True)

    with caplog.at_level(logging.WARNING):
        result = backend.run_experiment(ExperimentPreset.HELLO_QUANTUM_SIM, shot_budget=6)

    assert result.shots_used == 6
    failure.assert_called_once()
    simulated.assert_called_once()
    success.assert_not_called()

    provider_failure_logs = [rec for rec in caplog.records if "Live provider execution failed" in rec.message]
    assert provider_failure_logs, "expected provider failure log entry"
    assert provider_failure_logs[0].error_code == ErrorCode.PROVIDER_QUEUE_BACKPRESSURE.value


def teardown_module():
    """Reload backends so global registry picks up default provider clients."""

    import importlib

    importlib.reload(hardware_backends)
