from prometheus_client import CollectorRegistry

from synqc_backend.metrics import MetricsExporter


class _StubBudgetTracker:
    def health_summary(self) -> dict:
        return {"backend": "memory", "session_keys": 0}


class _StubQueue:
    def stats(self) -> dict:
        return {
            "total": 0,
            "queued": 0,
            "running": 0,
            "succeeded": 0,
            "failed": 0,
            "max_workers": 1,
            "oldest_queued_age_s": 0,
            "failure_codes": {},
            "failures_by_target": {},
        }


def test_metrics_exporter_can_use_isolated_registries():
    registry_one = CollectorRegistry()
    registry_two = CollectorRegistry()

    exporter_one = MetricsExporter(
        budget_tracker=_StubBudgetTracker(),
        queue=_StubQueue(),
        enabled=False,
        port=9000,
        bind_address="127.0.0.1",
        collection_interval_seconds=5,
        registry=registry_one,
    )

    exporter_two = MetricsExporter(
        budget_tracker=_StubBudgetTracker(),
        queue=_StubQueue(),
        enabled=False,
        port=9001,
        bind_address="127.0.0.1",
        collection_interval_seconds=5,
        registry=registry_two,
    )

    assert "synqc_queue_jobs_total" in exporter_one.registry._names_to_collectors  # noqa: SLF001
    assert "synqc_queue_jobs_total" in exporter_two.registry._names_to_collectors  # noqa: SLF001
    assert registry_one is not registry_two


def test_metrics_exporter_defaults_keep_registries_isolated():
    exporter_one = MetricsExporter(
        budget_tracker=_StubBudgetTracker(),
        queue=_StubQueue(),
        enabled=False,
        port=9002,
        bind_address="127.0.0.1",
        collection_interval_seconds=5,
    )

    exporter_two = MetricsExporter(
        budget_tracker=_StubBudgetTracker(),
        queue=_StubQueue(),
        enabled=False,
        port=9003,
        bind_address="127.0.0.1",
        collection_interval_seconds=5,
    )

    assert exporter_one.registry is not exporter_two.registry
    assert "synqc_queue_jobs_total" in exporter_one.registry._names_to_collectors  # noqa: SLF001
    assert "synqc_queue_jobs_total" in exporter_two.registry._names_to_collectors  # noqa: SLF001


def test_metrics_exporter_can_opt_into_shared_registry_without_duplication():
    shared_registry = CollectorRegistry()

    exporter_one = MetricsExporter(
        budget_tracker=_StubBudgetTracker(),
        queue=_StubQueue(),
        enabled=False,
        port=9004,
        bind_address="127.0.0.1",
        collection_interval_seconds=5,
        registry=shared_registry,
    )

    exporter_two = MetricsExporter(
        budget_tracker=_StubBudgetTracker(),
        queue=_StubQueue(),
        enabled=False,
        port=9005,
        bind_address="127.0.0.1",
        collection_interval_seconds=5,
        registry=shared_registry,
    )

    assert exporter_one.registry is exporter_two.registry
    assert exporter_one._queue_total is exporter_two._queue_total  # noqa: SLF001
