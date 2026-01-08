from __future__ import annotations

import json
import os
import sqlite3
import redis
import time
from dataclasses import asdict, dataclass

from prometheus_client import Counter, Histogram
from typing import Any, Dict, Optional



BENCH_EVENTS_TOTAL = Counter(
    "synqc_bench_events_total",
    "Total benchmark events recorded",
    ["agent", "ok"],
)

BENCH_LATENCY_MS = Histogram(
    "synqc_bench_latency_ms",
    "Benchmark latency in milliseconds",
    ["agent"],
    buckets=(1, 5, 10, 25, 50, 100, 250, 500, 1000, 2000, 5000),
)

@dataclass
class BenchEvent:
    ts_unix: float
    kind: str
    agent: str
    job_id: str
    ok: bool
    latency_ms: int
    details: Dict[str, Any]


def _storage_mode() -> str:
    return os.getenv("SYNQC_STORAGE_MODE", "sqlite").strip().lower()


def _sqlite_path() -> str:
    # Use /data (already volume-mounted in api container) by default
    return os.getenv("SYNQC_SQLITE_PATH", "/data/sandbox_events.sqlite3")
def _redis_url() -> str:
    return os.getenv("SYNQC_REDIS_URL", "").strip() or os.getenv("REDIS_URL", "").strip()


def _ensure_sqlite(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bench_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_unix REAL NOT NULL,
            kind TEXT NOT NULL,
            agent TEXT NOT NULL,
            job_id TEXT NOT NULL,
            ok INTEGER NOT NULL,
            latency_ms INTEGER NOT NULL,
            details_json TEXT NOT NULL
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bench_events_ts ON bench_events(ts_unix);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bench_events_agent ON bench_events(agent);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bench_events_job ON bench_events(job_id);")
    conn.commit()


def record_event(event: BenchEvent) -> None:
    mode = _storage_mode()

    if mode == "sqlite":
        path = _sqlite_path()
        conn = sqlite3.connect(path)
        try:
            _ensure_sqlite(conn)
            conn.execute(
                "INSERT INTO bench_events (ts_unix, kind, agent, job_id, ok, latency_ms, details_json) VALUES (?,?,?,?,?,?,?)",
                (
                    event.ts_unix,
                    event.kind,
                    event.agent,
                    event.job_id,
                    1 if event.ok else 0,
                    int(event.latency_ms),
                    json.dumps(event.details, ensure_ascii=False),
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return

    # Placeholder for next steps (kept explicit per your requirement)
    if mode == "redis":
        url = _redis_url()
        if not url:
            raise RuntimeError("SYNQC_STORAGE_MODE=redis requires SYNQC_REDIS_URL (or REDIS_URL).")
        client = redis.Redis.from_url(url)
        stream = os.getenv("SYNQC_REDIS_BENCH_STREAM", "synqc:bench_events")
        payload = {
            "ts_unix": str(event.ts_unix),
            "kind": str(event.kind),
            "agent": str(event.agent),
            "job_id": str(event.job_id),
            "ok": int(event.ok),  # bool -> 0/1
            "latency_ms": int(event.latency_ms),
            "details": json.dumps(event.details, ensure_ascii=False),
        }
        client.xadd(stream, payload, maxlen=10000, approximate=True)
        return


    if mode == "prometheus":
        BENCH_EVENTS_TOTAL.labels(agent=event.agent, ok=str(int(event.ok))).inc()
        BENCH_LATENCY_MS.labels(agent=event.agent).observe(float(event.latency_ms))
        return

    raise ValueError(f"Unknown SYNQC_STORAGE_MODE={mode!r}")
