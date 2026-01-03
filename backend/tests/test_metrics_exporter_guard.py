from synqc_backend.metrics import MetricsExporterGuard


class _StubExporter:
    def __init__(self, starts_running: bool = False):
        self.started = starts_running

    def start(self) -> None:
        self.started = True

    @property
    def is_running(self) -> bool:  # pragma: no cover - trivial property
        return self.started


def test_guard_bootstraps_missing_exporter():
    created: list[_StubExporter] = []

    def builder() -> _StubExporter:
        exp = _StubExporter()
        created.append(exp)
        return exp

    guard = MetricsExporterGuard(
        builder,
        check_interval_seconds=1,
        restart_backoff_seconds=0,
    )

    exporter = guard.ensure_running()
    assert exporter is created[-1]
    assert exporter.is_running
    assert guard.restart_count == 1

    created[-1].started = False
    exporter_two = guard.ensure_running()
    assert exporter_two is created[-1]
    assert exporter_two.is_running
    assert guard.restart_count == 2
