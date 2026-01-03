from __future__ import annotations

import logging
import threading
from time import monotonic
from typing import Callable, Optional

from prometheus_client import CollectorRegistry, Counter, Gauge, start_http_server

from .metrics_recorder import provider_metrics


logger = logging.getLogger(__name__)

_shared_registry: CollectorRegistry | None = None
_shared_registry_lock = threading.Lock()


def shared_prometheus_registry() -> CollectorRegistry:
    """Return a shared registry for production scraping if enabled."""

    global _shared_registry
    with _shared_registry_lock:
        if _shared_registry is None:
            _shared_registry = CollectorRegistry()
        return _shared_registry


class MetricsExporter:
    """Expose queue/budget health via Prometheus metrics on a background loop."""

    def __init__(
        self,
        *,
        budget_tracker,
        queue,
        enabled: bool,
        port: int,
        bind_address: str,
        collection_interval_seconds: int,
        registry: CollectorRegistry | None = None,
    ) -> None:
        self._budget_tracker = budget_tracker
        self._queue = queue
        self._enabled = enabled
        self._port = port
        self._addr = bind_address
        self._interval = collection_interval_seconds
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._previous_session_keys: Optional[int] = None

        # Allow callers to isolate registries to avoid duplicate collectors when
        # applications reload during tests or dev iterations.
        self._registry = registry or CollectorRegistry()

        # Budget metrics
        self._redis_connected = self._get_or_create_gauge(
            "synqc_redis_connected",
            "Redis connectivity status for the budget tracker (1=connected, 0=disconnected)",
            labelnames=["backend"],
        )
        self._budget_session_keys = self._get_or_create_gauge(
            "synqc_budget_session_keys",
            "Number of active budget session keys",
            labelnames=["backend"],
        )
        self._budget_session_key_churn_total = self._get_or_create_counter(
            "synqc_budget_session_key_churn_total",
            "Count of changes in session budget key totals (tracks churn spikes)",
            labelnames=["backend"],
        )

        # Queue metrics
        self._queue_total = self._get_or_create_gauge(
            "synqc_queue_jobs_total",
            "Total jobs tracked in the queue",
        )
        self._queue_queued = self._get_or_create_gauge(
            "synqc_queue_jobs_queued",
            "Jobs currently waiting to be executed",
        )
        self._queue_running = self._get_or_create_gauge(
            "synqc_queue_jobs_running",
            "Jobs currently executing in the worker pool",
        )
        self._queue_succeeded = self._get_or_create_gauge(
            "synqc_queue_jobs_succeeded",
            "Jobs that completed successfully",
        )
        self._queue_failed = self._get_or_create_gauge(
            "synqc_queue_jobs_failed", "Jobs that failed"
        )
        self._queue_oldest_age = self._get_or_create_gauge(
            "synqc_queue_oldest_queued_age_seconds",
            "Age in seconds of the oldest queued job (0 when queue is empty)",
        )
        self._queue_max_workers = self._get_or_create_gauge(
            "synqc_queue_max_workers",
            "Configured maximum worker threads available to execute jobs",
        )
        self._queue_failure_codes = self._get_or_create_gauge(
            "synqc_queue_failure_codes_total",
            "Total failures recorded by error_code",
            labelnames=["error_code"],
        )
        self._queue_failure_targets = self._get_or_create_gauge(
            "synqc_queue_failures_by_target_total",
            "Total failures recorded by hardware target",
            labelnames=["hardware_target"],
        )
        self._known_failure_labels: set[str] = set()
        self._known_failure_targets: set[str] = set()
        self._provider_seen_targets: set[str] = set()

        self._provider_success = self._get_or_create_gauge(
            "synqc_provider_health_success_total",
            "Snapshot of provider successes recorded by target",
            labelnames=["hardware_target"],
        )
        self._provider_failure = self._get_or_create_gauge(
            "synqc_provider_health_failures_total",
            "Snapshot of provider failures recorded by target",
            labelnames=["hardware_target"],
        )
        self._provider_simulated = self._get_or_create_gauge(
            "synqc_provider_health_simulated_total",
            "Snapshot of provider simulation fallbacks recorded by target",
            labelnames=["hardware_target"],
        )

        self._collection_errors = self._get_or_create_counter(
            "synqc_metrics_collection_errors_total",
            "Total errors while collecting and exporting metrics",
        )

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    @property
    def registry(self) -> CollectorRegistry:
        """Expose the exporter registry for inspection in tests or health probes."""

        return self._registry

    def start(self) -> None:
        """Start metrics exposition if enabled."""

        if not self._enabled:
            logger.info("Metrics exporter disabled; not starting Prometheus server")
            return

        if self._thread and self._thread.is_alive():
            return

        try:
            start_http_server(self._port, addr=self._addr, registry=self._registry)
            logger.info(
                "Started Prometheus metrics server", extra={"port": self._port}
            )
        except Exception as exc:  # noqa: BLE001 - we must surface startup failures
            logger.error("Failed to start metrics server", exc_info=exc)
            return

        self._thread = threading.Thread(
            target=self._run, name="synqc-metrics-exporter", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2 * self._interval)

    def _run(self) -> None:
        self._collect_with_guard()

        while not self._stop_event.wait(self._interval):
            self._collect_with_guard()

    def _collect_with_guard(self) -> None:
        try:
            self._collect_once()
        except Exception as exc:  # noqa: BLE001 - surfaced via metric for alerts
            self._collection_errors.inc()
            logger.exception("Metrics collection failed", exc_info=exc)

    def _collect_once(self) -> None:
        self._collect_budget_metrics()
        self._collect_queue_metrics()
        self._collect_provider_metrics()

    def _lookup_collector(self, name: str, expected_type: type):
        existing = self._registry._names_to_collectors.get(name)  # noqa: SLF001
        if existing is None:
            return None
        if not isinstance(existing, expected_type):
            raise ValueError(f"Collector {name} already registered with mismatched type")
        return existing

    def _get_or_create_gauge(self, name: str, doc: str, labelnames: list[str] | None = None):
        existing = self._lookup_collector(name, Gauge)
        if existing:
            return existing
        return Gauge(name, doc, labelnames=labelnames or (), registry=self._registry)

    def _get_or_create_counter(
        self, name: str, doc: str, labelnames: list[str] | None = None
    ):
        existing = self._lookup_collector(name, Counter)
        if existing:
            return existing
        return Counter(name, doc, labelnames=labelnames or (), registry=self._registry)

    def _collect_budget_metrics(self) -> None:
        summary = self._budget_tracker.health_summary()
        backend = summary.get("backend", "unknown")

        connected = 1.0 if (backend == "memory" or summary.get("redis_connected")) else 0.0
        session_keys = float(summary.get("session_keys", 0) or 0)

        self._redis_connected.labels(backend=backend).set(connected)
        self._budget_session_keys.labels(backend=backend).set(session_keys)

        if self._previous_session_keys is not None:
            delta = abs(session_keys - self._previous_session_keys)
            if delta > 0:
                self._budget_session_key_churn_total.labels(backend=backend).inc(delta)

        self._previous_session_keys = session_keys

    def _collect_queue_metrics(self) -> None:
        stats = self._queue.stats()

        self._queue_total.set(stats.get("total", 0))
        self._queue_queued.set(stats.get("queued", 0))
        self._queue_running.set(stats.get("running", 0))
        self._queue_succeeded.set(stats.get("succeeded", 0))
        self._queue_failed.set(stats.get("failed", 0))

        oldest_age = stats.get("oldest_queued_age_s")
        self._queue_oldest_age.set(oldest_age or 0)
        self._queue_max_workers.set(stats.get("max_workers", 0))

        failure_codes = stats.get("failure_codes", {}) or {}
        current_labels = set()
        for code, count in failure_codes.items():
            label = str(code)
            current_labels.add(label)
            self._queue_failure_codes.labels(error_code=label).set(count)

        # Zero out gauges for codes we have seen before but are now absent
        for code in self._known_failure_labels - current_labels:
            self._queue_failure_codes.labels(error_code=code).set(0)
        self._known_failure_labels = self._known_failure_labels | current_labels

        failure_targets = stats.get("failures_by_target", {}) or {}
        current_targets = set()
        for target, count in failure_targets.items():
            current_targets.add(target)
            self._queue_failure_targets.labels(hardware_target=target).set(count)

        for target in self._known_failure_targets - current_targets:
            self._queue_failure_targets.labels(hardware_target=target).set(0)
        self._known_failure_targets = self._known_failure_targets | current_targets

    def _collect_provider_metrics(self) -> None:
        summary = provider_metrics.health_summary()
        targets = summary.get("targets", {}) or {}

        current_targets = set()
        for target, stats in targets.items():
            current_targets.add(target)
            self._provider_success.labels(hardware_target=target).set(
                int(stats.get("success", 0) or 0)
            )
            self._provider_failure.labels(hardware_target=target).set(
                int(stats.get("failure", 0) or 0)
            )
            self._provider_simulated.labels(hardware_target=target).set(
                int(stats.get("simulated", 0) or 0)
            )

        for target in self._provider_seen_targets - current_targets:
            self._provider_success.labels(hardware_target=target).set(0)
            self._provider_failure.labels(hardware_target=target).set(0)
            self._provider_simulated.labels(hardware_target=target).set(0)

        self._provider_seen_targets = self._provider_seen_targets | current_targets


class MetricsExporterGuard:
    """Background sentinel to rehydrate metrics exporters that go missing."""

    def __init__(
        self,
        builder: Callable[[], MetricsExporter | None],
        *,
        check_interval_seconds: int = 60,
        restart_backoff_seconds: int = 180,
        initial_exporter: MetricsExporter | None = None,
    ) -> None:
        self._builder = builder
        self._check_interval = max(0.1, float(check_interval_seconds))
        self._restart_backoff = max(0.0, float(restart_backoff_seconds))
        self._current_exporter = initial_exporter
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_attempt = 0.0
        self._restart_count = 0

    @property
    def restart_count(self) -> int:
        return self._restart_count

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._thread = threading.Thread(
            target=self._run, name="synqc-metrics-guard", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2 * self._check_interval)

    def ensure_running(self) -> MetricsExporter | None:
        try:
            if self._current_exporter and self._current_exporter.is_running:
                return self._current_exporter

            now = monotonic()
            if now - self._last_attempt < self._restart_backoff:
                return self._current_exporter

            self._last_attempt = now
            exporter = self._builder()
            if exporter is None:
                return self._current_exporter

            exporter.start()
            if exporter.is_running:
                self._current_exporter = exporter
                self._restart_count += 1
                logger.info(
                    "Metrics exporter guard restarted exporter",
                    extra={
                        "port": getattr(exporter, "_port", None),
                        "restart_count": self._restart_count,
                    },
                )
            return self._current_exporter
        except Exception:
            logger.exception("Metrics exporter guard failed to restore exporter")
            return self._current_exporter

    def _run(self) -> None:
        while not self._stop_event.wait(self._check_interval):
            self.ensure_running()
