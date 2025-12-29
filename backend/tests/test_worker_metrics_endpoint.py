import importlib


class _FakeBudget:
    def health_summary(self):
        return {"backend": "memory", "session_keys": 0}


class _FakeQueue:
    def stats(self):
        return {
            "total": 1,
            "queued": 1,
            "running": 0,
            "succeeded": 0,
            "failed": 0,
            "oldest_queued_age_s": 0,
            "max_workers": 2,
        }


def _reload_worker(monkeypatch, **env):
    monkeypatch.setenv("SYNQC_ALLOWED_ORIGINS", "http://localhost")

    for key, value in env.items():
        monkeypatch.setenv(key, value)

    import synqc_backend.metrics as metrics_module

    importlib.reload(metrics_module)

    import synqc_backend.settings as settings_module

    importlib.reload(settings_module)
    import synqc_backend.config as config_module
    importlib.reload(config_module)
    import synqc_backend.worker as worker_module
    importlib.reload(worker_module)

    return worker_module


def test_worker_metrics_disabled_by_default(monkeypatch):
    worker_module = _reload_worker(monkeypatch, SYNQC_ENABLE_METRICS="true")

    exporter = worker_module.build_worker_metrics_exporter(_FakeBudget(), _FakeQueue())

    assert exporter is None


def test_worker_metrics_shared_registry_opt_in(monkeypatch):
    worker_module = _reload_worker(
        monkeypatch,
        SYNQC_ENABLE_METRICS="true",
        SYNQC_METRICS_WORKER_ENDPOINT_ENABLED="true",
        SYNQC_METRICS_WORKER_PORT="9350",
        SYNQC_METRICS_USE_SHARED_REGISTRY="true",
    )

    exporter = worker_module.build_worker_metrics_exporter(_FakeBudget(), _FakeQueue())

    assert exporter is not None
    assert exporter.registry is worker_module.shared_prometheus_registry()
