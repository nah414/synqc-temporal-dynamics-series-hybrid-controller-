"""Simple multi-worker load test to validate queue drain and budget stability.

Run this while the SynQc backend is live (and metrics exporter enabled). It will:
- Submit a burst of runs concurrently via `/runs`.
- Poll until all runs finish.
- Pull `/health` and Prometheus metrics to confirm the queue drains to zero,
  Redis stays connected, and session budget keys remain bounded.

Example:
    python backend/scripts/load_test.py --base-url http://127.0.0.1:8001 \
        --metrics-url http://127.0.0.1:9000/metrics --runs 30 --concurrency 6 \
        --api-key "super-secret" --session-id "local-load"

The script is intentionally dependency-light. We prefer the real ``httpx``
client, but will fall back to a bundled stub if a wheel is not cached in CI or
the environment blocks outbound downloads.
"""
from __future__ import annotations

import argparse
import asyncio
import re
import time
from typing import Any
import sys
from pathlib import Path

# Ensure the project root is importable when executed directly or under pytest
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synqc_backend.vendor.httpx_loader import load_httpx

httpx = load_httpx()


def _parse_metric(text: str, metric: str, labels: dict[str, str] | None = None) -> float | None:
    """Return the first matching Prometheus metric value or None.

    This is a lightweight parser for the simple, unlumped metrics we expose. It
    does not implement the full Prometheus exposition format.
    """

    labels = labels or {}
    label_fragments = [f'{key}="{value}"' for key, value in labels.items()]

    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        if not line.startswith(metric):
            continue
        if label_fragments and not all(fragment in line for fragment in label_fragments):
            continue
        match = re.search(r"(-?\d+(?:\.\d+)?)$", line.strip())
        if match:
            return float(match.group(1))
    return None


def _load_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8001", help="Backend base URL")
    parser.add_argument("--metrics-url", default="http://127.0.0.1:9000/metrics", help="Prometheus metrics URL")
    parser.add_argument("--runs", type=int, default=20, help="Number of runs to submit")
    parser.add_argument("--concurrency", type=int, default=4, help="Concurrent submissions")
    parser.add_argument("--api-key", required=True, help="API key for the backend")
    parser.add_argument("--session-id", default="load-test-session", help="Session ID for budgeting")
    parser.add_argument("--preset", default="health", help="Experiment preset to run")
    parser.add_argument("--timeout", type=int, default=120, help="Overall timeout in seconds")
    parser.add_argument(
        "--strict",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Fail with a non-zero exit code if the queue fails to drain, Redis disconnects, "
            "or runs are incomplete. Disable with --no-strict for exploratory use."
        ),
    )
    return parser.parse_args()


def _request_headers(api_key: str, session_id: str) -> dict[str, str]:
    return {"X-Api-Key": api_key, "X-Session-Id": session_id}


async def _submit_run(client: httpx.AsyncClient, base_url: str, preset: str, headers: dict[str, str]) -> str:
    payload = {"preset": preset}
    resp = await client.post(f"{base_url}/runs", json=payload, headers=headers)
    resp.raise_for_status()
    run_id = resp.json()["id"]
    return run_id


async def _poll_run(client: httpx.AsyncClient, base_url: str, run_id: str, headers: dict[str, str]) -> str:
    resp = await client.get(f"{base_url}/runs/{run_id}", headers=headers)
    resp.raise_for_status()
    return resp.json()["status"]


async def _gather_runs(
    base_url: str,
    metrics_url: str,
    runs: int,
    concurrency: int,
    headers: dict[str, str],
    preset: str,
    timeout: int,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
        # Initial metrics snapshot to compare after the run
        metrics_before = await _safe_get_metrics(client, metrics_url)

        # Submit runs with bounded concurrency
        semaphore = asyncio.Semaphore(concurrency)
        run_ids: list[str] = []

        async def submit_one() -> None:
            async with semaphore:
                run_id = await _submit_run(client, base_url, preset, headers)
                run_ids.append(run_id)

        await asyncio.gather(*(submit_one() for _ in range(runs)))

        # Poll until all runs finish or timeout
        start = time.monotonic()
        remaining = set(run_ids)
        statuses: dict[str, str] = {}
        while remaining:
            await asyncio.sleep(0.5)
            for run_id in list(remaining):
                status = await _poll_run(client, base_url, run_id, headers)
                statuses[run_id] = status
                if status in {"succeeded", "failed"}:
                    remaining.discard(run_id)
            if time.monotonic() - start > timeout:
                break

        metrics_after = await _safe_get_metrics(client, metrics_url)
        health = await _safe_get_json(client, f"{base_url}/health", headers=headers)

    return {
        "run_ids": run_ids,
        "statuses": statuses,
        "metrics_before": metrics_before,
        "metrics_after": metrics_after,
        "health": health,
    }


async def _safe_get_metrics(client: httpx.AsyncClient, metrics_url: str) -> str:
    try:
        resp = await client.get(metrics_url)
        resp.raise_for_status()
        return resp.text
    except Exception:  # noqa: BLE001 - surfaced in caller summary
        return ""


async def _safe_get_json(
    client: httpx.AsyncClient, url: str, headers: dict[str, str]
) -> dict[str, Any] | None:
    try:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()
    except Exception:  # noqa: BLE001 - surfaced in caller summary
        return None


def _summarize(result: dict[str, Any], *, expected_runs: int, strict: bool) -> bool:
    finished = [status for status in result["statuses"].values() if status in {"succeeded", "failed"}]
    incomplete = [rid for rid, status in result["statuses"].items() if status not in {"succeeded", "failed"}]

    print("=== Load Test Summary ===")
    print(f"Runs submitted: {len(result['run_ids'])}")
    print(f"Runs finished: {len(finished)}")
    if incomplete:
        print(f"Incomplete run IDs: {', '.join(incomplete)}")

    issues: list[str] = []
    issues.extend(_summarize_health(result.get("health")))
    issues.extend(_summarize_metrics(result.get("metrics_before", ""), result.get("metrics_after", "")))

    failed_runs = [rid for rid, status in result["statuses"].items() if status == "failed"]
    if failed_runs:
        issues.append(f"Runs failed: {', '.join(failed_runs)}")
    if len(finished) < expected_runs:
        issues.append(
            f"Only {len(finished)} of {expected_runs} runs finished before timeout"
        )

    if issues and strict:
        print("\nSTRICT mode detected issues:")
        for issue in issues:
            print(f"  - {issue}")
        return False

    if issues:
        print("\nWarnings (non-strict mode):")
        for issue in issues:
            print(f"  - {issue}")
    return True


def _summarize_health(health: dict[str, Any] | None) -> list[str]:
    print("\nHealth snapshot:")
    issues: list[str] = []
    if not health:
        print("  (failed to fetch /health)")
        issues.append("/health unreachable")
        return issues
    queue = health.get("queue", {})
    budget = health.get("budget_tracker", {})
    print(f"  Queue queued/running/total: {queue.get('queued')} / {queue.get('running')} / {queue.get('total')}")
    print(f"  Oldest queued age (s): {queue.get('oldest_queued_age_s')}")
    print(f"  Budget backend: {budget.get('backend')} | redis_connected={budget.get('redis_connected')}")
    print(f"  Session keys: {budget.get('session_keys')}")

    if queue.get("queued") not in (0, None):
        issues.append(f"Queue not drained: queued={queue.get('queued')}")
    if queue.get("running") not in (0, None):
        issues.append(f"Workers still running: running={queue.get('running')}")
    if budget.get("backend") == "redis" and budget.get("redis_connected") is False:
        issues.append("Redis disconnected per /health")
    return issues


def _summarize_metrics(before: str, after: str) -> list[str]:
    print("\nPrometheus metrics diff:")
    issues: list[str] = []
    if not after:
        print("  (metrics endpoint unreachable)")
        issues.append("metrics endpoint unreachable")
        return issues

    queue_queued_before = _parse_metric(before, "synqc_queue_jobs_queued") if before else 0
    queue_queued_after = _parse_metric(after, "synqc_queue_jobs_queued")
    queue_age_after = _parse_metric(after, "synqc_queue_oldest_queued_age_seconds")
    redis_connected = _parse_metric(after, "synqc_redis_connected", labels={"backend": "redis"})
    session_keys = _parse_metric(after, "synqc_budget_session_keys", labels={"backend": "redis"})

    print(f"  Queue queued before/after: {queue_queued_before} -> {queue_queued_after}")
    print(f"  Oldest queued age after: {queue_age_after}")
    print(f"  Redis connected: {redis_connected}")
    print(f"  Session budget keys: {session_keys}")
    if queue_queued_after and queue_queued_after > 0:
        print("  WARNING: queue did not drain to zero")
        issues.append(f"Queue depth remained at {queue_queued_after}")
    if redis_connected == 0:
        print("  WARNING: Redis disconnected during test")
        issues.append("Redis disconnected per metrics")
    return issues


async def main() -> None:
    args = _load_args()
    headers = _request_headers(api_key=args.api_key, session_id=args.session_id)

    result = await _gather_runs(
        base_url=args.base_url,
        metrics_url=args.metrics_url,
        runs=args.runs,
        concurrency=args.concurrency,
        headers=headers,
        preset=args.preset,
        timeout=args.timeout,
    )
    ok = _summarize(result, expected_runs=args.runs, strict=args.strict)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
