from __future__ import annotations

import argparse
import json
import time
from typing import Any

import requests


def main() -> int:
    p = argparse.ArgumentParser(description="SynQc agent audit runner (calls the HTTP API).")
    p.add_argument("--api", default="http://127.0.0.1:8001", help="Base API URL")
    p.add_argument("--queue", default="default", help="Queue name")
    p.add_argument("--timeout", type=int, default=30, help="Seconds to wait per agent")
    args = p.parse_args()

    base = args.api.rstrip("/")
    agents = requests.get(f"{base}/agents", timeout=10).json()["agents"]
    print(f"Found {len(agents)} agent(s). Running audit...\n")

    report: list[dict[str, Any]] = []

    for a in agents:
        name = a["name"]
        started = time.perf_counter()
        try:
            resp = requests.post(
                f"{base}/agents/{name}/run",
                params={"queue_name": args.queue, "wait": True, "timeout_seconds": args.timeout},
                json={"shots": 64, "target": "simulator", "params": {}},
                timeout=args.timeout + 5,
            )
            resp.raise_for_status()
            payload = resp.json()
            job_id = payload["job_id"]
        except Exception as e:
            report.append({"agent": name, "ok": False, "error": str(e)})
            continue

        job = requests.get(f"{base}/jobs/{job_id}", timeout=10).json()
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        report.append(
            {
                "agent": name,
                "ok": job["status"] == "succeeded",
                "status": job["status"],
                "elapsed_ms": round(elapsed_ms, 1),
                "attempts": job.get("attempts"),
                "error": job.get("error"),
                "kpis": (job.get("result") or {}).get("kpis") if job.get("result") else None,
            }
        )

    print(json.dumps({"report": report}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
