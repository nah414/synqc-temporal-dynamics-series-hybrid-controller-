"""Quickstart smoke test for the SynQc backend.

The script verifies:
1) /health responds with status ok
2) Redis is reachable when configured
3) A simulator preset can be enqueued and completes successfully

Usage:
    SYNQC_API_URL=http://127.0.0.1:8001 \
    SYNQC_API_KEY=... (optional, only if your deployment requires it) \
    python backend/scripts/quickstart_health_check.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_API_URL = "http://127.0.0.1:8001"
POLL_INTERVAL_SECONDS = 1.5
POLL_TIMEOUT_SECONDS = 30


def _request(method: str, url: str, api_key: str | None, payload: Dict[str, Any] | None = None) -> Tuple[int, Dict[str, Any]]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(url=url, data=data, method=method)
    if api_key:
        req.add_header("X-Api-Key", api_key)
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req, timeout=10) as resp:
            status = resp.getcode()
            body = json.loads(resp.read().decode()) if resp.length not in (None, 0) else {}
            return status, body
    except HTTPError as exc:  # pragma: no cover - diagnostic output
        message = exc.read().decode()
        raise RuntimeError(f"HTTP {exc.code} calling {url}: {message}") from exc
    except URLError as exc:  # pragma: no cover - diagnostic output
        raise RuntimeError(f"Failed to reach {url}: {exc.reason}") from exc


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def verify_health(api_url: str, api_key: str | None) -> Dict[str, Any]:
    status, body = _request("GET", f"{api_url}/health", api_key)
    _assert(status == 200, "Health endpoint did not return HTTP 200")
    _assert(body.get("status") == "ok", "Health payload did not report status=ok")

    budget = body.get("budget_tracker", {})
    if budget.get("backend") == "redis":
        _assert(budget.get("redis_ok"), "Redis backend reported redis_ok=False")
    print("✓ /health reports ok and budget backend is healthy")
    return body


def verify_sim_preset(api_url: str, api_key: str | None) -> None:
    payload = {
        "preset": "health",
        "hardware_target": "sim_local",
        "shot_budget": 256,
    }
    status, body = _request("POST", f"{api_url}/runs", api_key, payload)
    _assert(status in (200, 202), f"Run submission failed with status {status}")
    run_id = body.get("id")
    _assert(run_id, "Run submission did not return an id")
    print(f"✓ Submitted simulator preset (run_id={run_id})")

    deadline = time.time() + POLL_TIMEOUT_SECONDS
    while time.time() < deadline:
        status, poll = _request("GET", f"{api_url}/runs/{run_id}", api_key)
        _assert(status == 200, f"Polling run {run_id} failed with status {status}")
        job_status = poll.get("status")
        if job_status == "succeeded":
            print("✓ Simulator preset completed successfully")
            return
        if job_status == "failed":
            detail = poll.get("error_message") or poll.get("error") or "unknown error"
            raise RuntimeError(f"Run failed: {detail}")
        time.sleep(POLL_INTERVAL_SECONDS)

    raise RuntimeError(f"Run {run_id} did not complete within {POLL_TIMEOUT_SECONDS} seconds")


def main() -> None:
    api_url = os.environ.get("SYNQC_API_URL", DEFAULT_API_URL).rstrip("/")
    api_key = os.environ.get("SYNQC_API_KEY")

    print(f"Using API base: {api_url}")
    if api_key:
        print("Using X-Api-Key authentication")
    else:
        print("No API key supplied; ensure your deployment allows anonymous access")

    verify_health(api_url, api_key)
    verify_sim_preset(api_url, api_key)
    print("All quickstart checks passed")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - CLI entrypoint
        print(f"ERROR: {exc}")
        sys.exit(1)
