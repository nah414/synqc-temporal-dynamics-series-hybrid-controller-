import anyio
import pytest


def test_health_exposes_provider_metrics(monkeypatch):
    from synqc_backend import api
    from synqc_backend.metrics_recorder import provider_metrics

    provider_metrics.reset()
    provider_metrics.record_success("sim", 0.05)
    provider_metrics.record_failure("ibm", "AUTH_REQUIRED", 0.12)
    provider_metrics.record_simulated("ionq", 0.02)

    api._HEALTH_CACHE.clear()
    monkeypatch.setattr(api.settings, "health_cache_ttl_seconds", 0)

    payload = anyio.run(api.health)

    provider_summary = payload.get("provider_metrics") or {}
    assert provider_summary.get("totals", {}).get("failure") == 1
    assert "ibm" in (provider_summary.get("failing_targets") or [])
    targets = provider_summary.get("targets", {})
    assert targets.get("ibm", {}).get("failure") == 1
    assert targets.get("ibm", {}).get("error_codes", {}).get("AUTH_REQUIRED") == 1
    assert targets.get("sim", {}).get("success") == 1
    assert targets.get("ionq", {}).get("simulated") == 1


def test_metrics_exporter_publishes_provider_snapshot():
    from synqc_backend import api
    from synqc_backend.metrics_recorder import provider_metrics

    provider_metrics.reset()
    provider_metrics.record_failure("azure", "AUTH_REQUIRED", 0.1)
    provider_metrics.record_success("azure", 0.2)

    api.metrics_exporter.stop()
    api.metrics_exporter._collect_provider_metrics()

    assert (
        api.metrics_exporter._provider_failure.labels(hardware_target="azure")._value.get()
        == 1
    )
    assert (
        api.metrics_exporter._provider_success.labels(hardware_target="azure")._value.get()
        == 1
    )
    assert (
        api.metrics_exporter._provider_simulated.labels(hardware_target="azure")._value.get()
        == 0
    )
