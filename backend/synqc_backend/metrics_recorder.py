from __future__ import annotations

"""Prometheus run-level metrics helpers."""

from prometheus_client import Counter, Histogram


class RunMetricsRecorder:
    def __init__(self) -> None:
        self._runs = Counter(
            "synqc_runs_total",
            "Total run events by hardware target and status",
            labelnames=["hardware_target", "status"],
        )
        self._failures = Counter(
            "synqc_run_failures_total",
            "Run failures by error_code",
            labelnames=["error_code"],
        )
        self._latency = Histogram(
            "synqc_run_latency_seconds",
            "Observed wall-clock latency for runs",
            labelnames=["hardware_target", "status"],
            buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 15, 30, 60, 120, 300, float("inf")),
        )

    def record_submission(self, hardware_target: str) -> None:
        target = hardware_target or "unknown"
        self._runs.labels(hardware_target=target, status="submitted").inc()

    def record_success(self, hardware_target: str, latency_seconds: float | None) -> None:
        target = hardware_target or "unknown"
        latency = latency_seconds or 0.0
        self._runs.labels(hardware_target=target, status="succeeded").inc()
        self._latency.labels(hardware_target=target, status="succeeded").observe(latency)

    def record_failure(
        self, hardware_target: str, error_code: str | None, latency_seconds: float | None
    ) -> None:
        target = hardware_target or "unknown"
        code = error_code or "unknown"
        latency = latency_seconds or 0.0
        self._runs.labels(hardware_target=target, status="failed").inc()
        self._failures.labels(error_code=code).inc()
        self._latency.labels(hardware_target=target, status="failed").observe(latency)


run_metrics = RunMetricsRecorder()


class ProviderMetricsRecorder:
    """Provider-side run metrics for observability and smoke coverage."""

    def __init__(self) -> None:
        self._runs = Counter(
            "synqc_provider_runs_total",
            "Provider client invocations by target, status, and error code",
            labelnames=["hardware_target", "status", "error_code"],
        )
        self._latency = Histogram(
            "synqc_provider_latency_seconds",
            "Observed latency for provider client invocations",
            labelnames=["hardware_target", "status"],
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 15, 30, 60, float("inf")),
        )
        self._summary: dict[str, dict[str, object]] = {}

    def record_success(self, hardware_target: str, latency_seconds: float | None) -> None:
        target = hardware_target or "unknown"
        latency = latency_seconds or 0.0
        self._runs.labels(hardware_target=target, status="success", error_code="none").inc()
        self._latency.labels(hardware_target=target, status="success").observe(latency)

        stats = self._summary.setdefault(
            target, {"success": 0, "failure": 0, "simulated": 0, "error_codes": {}}
        )
        stats["success"] = int(stats.get("success", 0)) + 1

    def record_failure(self, hardware_target: str, error_code: str | None, latency_seconds: float | None) -> None:
        target = hardware_target or "unknown"
        code = error_code or "unknown"
        latency = latency_seconds or 0.0
        self._runs.labels(hardware_target=target, status="failure", error_code=code).inc()
        self._latency.labels(hardware_target=target, status="failure").observe(latency)

        stats = self._summary.setdefault(
            target, {"success": 0, "failure": 0, "simulated": 0, "error_codes": {}}
        )
        stats["failure"] = int(stats.get("failure", 0)) + 1
        error_counts = stats.get("error_codes", {}) or {}
        error_counts[code] = int(error_counts.get(code, 0)) + 1
        stats["error_codes"] = error_counts

    def record_simulated(self, hardware_target: str, latency_seconds: float | None) -> None:
        target = hardware_target or "unknown"
        latency = latency_seconds or 0.0
        self._runs.labels(hardware_target=target, status="simulated", error_code="none").inc()
        self._latency.labels(hardware_target=target, status="simulated").observe(latency)

        stats = self._summary.setdefault(
            target, {"success": 0, "failure": 0, "simulated": 0, "error_codes": {}}
        )
        stats["simulated"] = int(stats.get("simulated", 0)) + 1

    def reset(self) -> None:
        """Reset in-memory provider summaries (metrics counters remain for Prometheus)."""

        self._summary.clear()

    def health_summary(self) -> dict[str, object]:
        """Return snapshot-friendly provider metrics for health surfaces."""

        totals = {"success": 0, "failure": 0, "simulated": 0}
        failing_targets: list[str] = []
        per_target: dict[str, dict[str, object]] = {}

        for target, stats in self._summary.items():
            success = int(stats.get("success", 0) or 0)
            failure = int(stats.get("failure", 0) or 0)
            simulated = int(stats.get("simulated", 0) or 0)
            error_codes = stats.get("error_codes", {}) or {}

            totals["success"] += success
            totals["failure"] += failure
            totals["simulated"] += simulated

            if failure > 0:
                failing_targets.append(target)

            per_target[target] = {
                "success": success,
                "failure": failure,
                "simulated": simulated,
                "error_codes": error_codes,
            }

        return {
            "totals": totals,
            "targets": per_target,
            "failing_targets": sorted(failing_targets),
        }


provider_metrics = ProviderMetricsRecorder()

