from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from synqc_backend.hardware_backends import ProviderBackend
from synqc_backend.models import ExperimentPreset
from synqc_backend.provider_clients import ProviderLiveResult


class _FakeLiveClient:
    def __init__(self, result: ProviderLiveResult):
        self._result = result
        self.calls: list[tuple[ExperimentPreset, int]] = []

    def run(self, preset: ExperimentPreset, shot_budget: int) -> ProviderLiveResult:
        self.calls.append((preset, shot_budget))
        return self._result


def test_provider_backend_prefers_live_counts(monkeypatch):
    result = ProviderLiveResult(
        raw_counts={"00": 30, "11": 70},
        expected_distribution={"00": 0.25, "11": 0.75},
        latency_us=123.0,
        backaction=0.12,
    )
    client = _FakeLiveClient(result)

    backend = ProviderBackend(
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
        live_client=client,
    )

    # Ensure simulation fallback is available if live were to fail
    monkeypatch.setattr("synqc_backend.hardware_backends.settings.allow_provider_simulation", True)

    bundle = backend.run_experiment(ExperimentPreset.HEALTH, shot_budget=100)

    assert client.calls == [(ExperimentPreset.HEALTH, 100)]
    assert bundle.raw_counts == result.raw_counts
    assert bundle.expected_distribution == result.expected_distribution
    assert bundle.shots_used == 100
    assert bundle.latency_us == result.latency_us
    assert bundle.backaction == result.backaction
    assert bundle.fidelity is not None
