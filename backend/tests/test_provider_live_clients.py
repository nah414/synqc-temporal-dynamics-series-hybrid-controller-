import math

import pytest

from synqc_backend.budget import BudgetTracker
from synqc_backend.config import settings
from synqc_backend.control_profiles import ControlProfileStore
from synqc_backend.engine import SynQcEngine
from synqc_backend.hardware_backends import ProviderBackend
from synqc_backend.models import ExperimentPreset, ExperimentStatus, KpiBundle, RunExperimentRequest
from synqc_backend.provider_clients import ProviderClientError, ProviderLiveResult
from synqc_backend.storage import ExperimentStore


class _FakeLiveClient:
    def __init__(self, result: ProviderLiveResult):
        self._result = result
        self.calls: list[tuple[ExperimentPreset, int]] = []

    def run(self, preset: ExperimentPreset, shot_budget: int) -> ProviderLiveResult:
        self.calls.append((preset, shot_budget))
        return self._result


def _make_backend(live_client=None) -> ProviderBackend:
    return ProviderBackend(
        id="aws_braket",
        name="AWS Braket",
        kind="superconducting",
        vendor="aws",
        fidelity_floor=0.90,
        fidelity_ceiling=0.99,
        latency_base_us=50.0,
        latency_span_us=10.0,
        backaction_base=0.1,
        backaction_span=0.05,
        live_client=live_client,
    )


def _make_engine(monkeypatch, backend: ProviderBackend) -> SynQcEngine:
    store = ExperimentStore()
    budget_tracker = BudgetTracker(redis_url=None, fail_open_on_redis_error=True)
    control_store = ControlProfileStore()
    engine = SynQcEngine(store=store, budget_tracker=budget_tracker, control_store=control_store)
    monkeypatch.setattr("synqc_backend.hardware_backends.get_backend", lambda _target: backend)
    monkeypatch.setattr("synqc_backend.engine.get_backend", lambda _target: backend)
    return engine


def test_provider_backend_prefers_live_counts(monkeypatch):
    result = ProviderLiveResult(
        raw_counts={"00": 30, "11": 70},
        expected_distribution={"00": 0.25, "11": 0.75},
        latency_us=123.0,
        backaction=0.12,
    )
    client = _FakeLiveClient(result)
    backend = _make_backend(live_client=client)

    # Ensure simulation fallback is available if live were to fail
    monkeypatch.setattr(settings, "allow_provider_simulation", True, raising=False)

    bundle = backend.run_experiment(ExperimentPreset.HEALTH, shot_budget=100)

    assert client.calls == [(ExperimentPreset.HEALTH, 100)]
    assert bundle.raw_counts == result.raw_counts
    assert bundle.expected_distribution == result.expected_distribution
    assert bundle.shots_used == 100
    assert bundle.latency_us == result.latency_us
    assert bundle.backaction == result.backaction
    assert bundle.fidelity is not None


def test_provider_backend_falls_back_to_simulation_on_live_failure(monkeypatch):
    backend = _make_backend()

    simulate_bundle = KpiBundle(
        fidelity=0.91,
        latency_us=15.0,
        backaction=0.05,
        raw_counts={"00": 10, "11": 90},
        expected_distribution={"00": 0.1, "11": 0.9},
        shots_used=100,
        shot_budget=100,
        status=ExperimentStatus.OK,
    )

    def _failing_run_live(preset, shot_budget):
        raise ProviderClientError("live client failure")

    def _fake_simulate(preset, shot_budget):
        assert shot_budget == 100
        return simulate_bundle

    monkeypatch.setattr(settings, "allow_provider_simulation", True, raising=False)
    monkeypatch.setattr(backend, "_run_live", _failing_run_live)
    monkeypatch.setattr(backend, "_simulate", _fake_simulate)

    bundle = backend.run_experiment(preset=ExperimentPreset.HEALTH, shot_budget=100)

    assert bundle.model_dump() == simulate_bundle.model_dump()


def test_provider_backend_raises_when_simulation_not_allowed(monkeypatch):
    backend = _make_backend(live_client=_FakeLiveClient(ProviderLiveResult(raw_counts={"00": 1})))

    def _failing_run_live(preset, shot_budget):
        raise ProviderClientError("live client failure")

    def _simulate_should_not_be_called(preset, shot_budget):
        raise AssertionError("_simulate should not be called when allow_provider_simulation is False")

    monkeypatch.setattr(settings, "allow_provider_simulation", False, raising=False)
    monkeypatch.setattr(backend, "_run_live", _failing_run_live)
    monkeypatch.setattr(backend, "_simulate", _simulate_should_not_be_called)

    with pytest.raises(ProviderClientError, match="live client failure"):
        backend.run_experiment(preset=ExperimentPreset.HEALTH, shot_budget=100)


def test_live_missing_expected_distribution_uses_internal_expected_distribution(monkeypatch):
    raw_counts = {"00": 60, "11": 40}
    provider_result = ProviderLiveResult(
        raw_counts=raw_counts,
        shots_used=None,
        expected_distribution=None,
        latency_us=123.0,
        backaction=0.05,
    )
    client = _FakeLiveClient(provider_result)
    backend = _make_backend(live_client=client)

    monkeypatch.setattr(settings, "allow_provider_simulation", True, raising=False)

    engine = _make_engine(monkeypatch, backend)
    response = engine.run_experiment(
        RunExperimentRequest(preset=ExperimentPreset.HEALTH, hardware_target="aws_braket", shot_budget=100),
        session_id="test-session",
    )

    assert client.calls == [(ExperimentPreset.HEALTH, 100)]
    assert response.kpis.raw_counts == raw_counts
    assert response.kpis.expected_distribution is not None
    assert response.kpis.expected_distribution
    assert math.isfinite(response.kpis.fidelity)

    fidelity_details = [d for d in response.kpi_details if d.definition_id == "fidelity_dist_v1"]
    assert fidelity_details
    ci = fidelity_details[0].ci95
    assert ci is not None and len(ci) == 2


def test_live_conflicting_shots_used_prefers_counts_sum(monkeypatch):
    raw_counts = {"00": 60, "11": 40}
    provider_result = ProviderLiveResult(
        raw_counts=raw_counts,
        shots_used=42,
        expected_distribution=None,
        latency_us=321.0,
        backaction=0.02,
    )
    client = _FakeLiveClient(provider_result)
    backend = _make_backend(live_client=client)

    monkeypatch.setattr(settings, "allow_provider_simulation", True, raising=False)

    engine = _make_engine(monkeypatch, backend)
    response = engine.run_experiment(
        RunExperimentRequest(preset=ExperimentPreset.HEALTH, hardware_target="aws_braket", shot_budget=100),
        session_id="test-session",
    )

    assert response.kpis.shots_used == sum(raw_counts.values())
    assert response.kpis.shots_used != provider_result.shots_used


def test_live_missing_latency_and_backaction_use_simulated_defaults(monkeypatch):
    raw_counts = {"00": 50, "11": 50}
    provider_result = ProviderLiveResult(
        raw_counts=raw_counts,
        shots_used=None,
        expected_distribution=None,
        latency_us=None,
        backaction=None,
    )

    client = _FakeLiveClient(provider_result)
    backend = _make_backend(live_client=client)

    monkeypatch.setattr(settings, "allow_provider_simulation", True, raising=False)

    bundle = backend.run_experiment(ExperimentPreset.HEALTH, shot_budget=100)

    assert bundle.raw_counts == raw_counts
    assert bundle.latency_us is not None and math.isfinite(bundle.latency_us)
    assert bundle.backaction is not None and math.isfinite(bundle.backaction)
