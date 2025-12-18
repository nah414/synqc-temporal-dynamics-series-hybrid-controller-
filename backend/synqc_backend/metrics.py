from __future__ import annotations

import logging
import threading
from typing import Optional

from prometheus_client import Counter, Gauge, start_http_server


logger = logging.getLogger(__name__)


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

        # Budget metrics
        self._redis_connected = Gauge(
            "synqc_redis_connected",
            "Redis connectivity status for the budget tracker (1=connected, 0=disconnected)",
            labelnames=["backend"],
        )
        self._budget_session_keys = Gauge(
            "synqc_budget_session_keys",
            "Number of active budget session keys",
            labelnames=["backend"],
        )
        self._budget_session_key_churn_total = Counter(
            "synqc_budget_session_key_churn_total",
            "Count of changes in session budget key totals (tracks churn spikes)",
            labelnames=["backend"],
        )

        # Queue metrics
        self._queue_total = Gauge("synqc_queue_jobs_total", "Total jobs tracked in the queue")
        self._queue_queued = Gauge(
            "synqc_queue_jobs_queued", "Jobs currently waiting to be executed"
        )
        self._queue_running = Gauge(
            "synqc_queue_jobs_running", "Jobs currently executing in the worker pool"
        )
        self._queue_succeeded = Gauge(
            "synqc_queue_jobs_succeeded", "Jobs that completed successfully"
        )
        self._queue_failed = Gauge("synqc_queue_jobs_failed", "Jobs that failed")
        self._queue_oldest_age = Gauge(
            "synqc_queue_oldest_queued_age_seconds",
            "Age in seconds of the oldest queued job (0 when queue is empty)",
        )
        self._queue_max_workers = Gauge(
            "synqc_queue_max_workers",
            "Configured maximum worker threads available to execute jobs",
        )

        self._collection_errors = Counter(
            "synqc_metrics_collection_errors_total",
            "Total errors while collecting and exporting metrics",
        )

    def start(self) -> None:
        """Start metrics exposition if enabled."""

        if not self._enabled:
            logger.info("Metrics exporter disabled; not starting Prometheus server")
            return

        if self._thread and self._thread.is_alive():
            return

        try:
            start_http_server(self._port, addr=self._addr)
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
