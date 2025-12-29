"""Lightweight run logging for SynQc Shor/RSA demo.

Why this exists
--------------
Your SynQc UI already has an "Experiment Runs" concept. The Shor/RSA panel
is a separate feature, but it becomes *way* more useful if it can emit
run records that the rest of the UI can display.

This module keeps an in-memory ring buffer of recent runs and can
optionally append JSONL to disk.

It is intentionally dependency-free.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
import os
from threading import Lock
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .config import SYNQC_SHOR_RUN_LOG_MAX, SYNQC_SHOR_RUN_LOG_PATH


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    ts_utc: str
    kind: str
    ok: bool
    runtime_ms: float
    request: Dict[str, Any]
    response: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_public_summary(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "ts_utc": self.ts_utc,
            "kind": self.kind,
            "ok": self.ok,
            "runtime_ms": self.runtime_ms,
        }


_LOCK = Lock()
_RUNS: List[RunRecord] = []


def record_run(
    *,
    kind: str,
    ok: bool,
    runtime_ms: float,
    request: Dict[str, Any],
    response: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> RunRecord:
    """Create and store a run record."""

    rec = RunRecord(
        run_id=str(uuid4()),
        ts_utc=_utc_now_iso(),
        kind=kind,
        ok=ok,
        runtime_ms=float(runtime_ms),
        request=request,
        response=response,
        error=error,
    )

    with _LOCK:
        _RUNS.append(rec)
        # Keep only last N
        if len(_RUNS) > SYNQC_SHOR_RUN_LOG_MAX:
            del _RUNS[: len(_RUNS) - SYNQC_SHOR_RUN_LOG_MAX]

    # Optional JSONL append
    if SYNQC_SHOR_RUN_LOG_PATH:
        try:
            os.makedirs(os.path.dirname(SYNQC_SHOR_RUN_LOG_PATH), exist_ok=True)
        except Exception:
            # If the directory cannot be created, we still keep in-memory runs.
            pass
        try:
            with open(SYNQC_SHOR_RUN_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")
        except Exception:
            pass

    return rec


def list_runs(limit: int = 50) -> List[Dict[str, Any]]:
    """Return public summaries, newest-first."""
    limit = max(1, min(int(limit), 500))
    with _LOCK:
        return [r.to_public_summary() for r in reversed(_RUNS[-limit:])]


def get_run(run_id: str) -> Optional[Dict[str, Any]]:
    """Return full run details, or None."""
    with _LOCK:
        for r in _RUNS:
            if r.run_id == run_id:
                return asdict(r)
    return None
