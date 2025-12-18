from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass
class QubitUsageSnapshot:
    """Simple snapshot of per-session qubit usage."""

    session_total: int
    last_run_qubits: int
    last_updated: float


class SessionQubitTracker:
    """Track how many qubits were exercised per session.

    This mirrors the session TTL behavior of the budget tracker so that per-session
    aggregates naturally expire without manual cleanup.
    """

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._usage: Dict[str, Tuple[int, int, float]] = {}

    def _evict_expired_locked(self) -> None:
        now = time.time()
        expired = [
            session_id
            for session_id, (_, _, ts) in self._usage.items()
            if now - ts >= self._ttl_seconds
        ]
        for session_id in expired:
            self._usage.pop(session_id, None)

    def record(self, session_id: str, qubits_used: int) -> None:
        """Record qubit usage for a session."""
        with self._lock:
            self._evict_expired_locked()
            total, _, _ = self._usage.get(session_id, (0, 0, time.time()))
            now = time.time()
            self._usage[session_id] = (max(0, total + max(qubits_used, 0)), max(qubits_used, 0), now)

    def snapshot(self, session_id: str) -> QubitUsageSnapshot:
        """Return a session-scoped usage snapshot (zeros if none recorded)."""
        with self._lock:
            self._evict_expired_locked()
            total, last, ts = self._usage.get(session_id, (0, 0, time.time()))
            return QubitUsageSnapshot(session_total=total, last_run_qubits=last, last_updated=ts)

    def health(self) -> Dict[str, object]:
        """Expose a lightweight health summary for observability."""
        with self._lock:
            self._evict_expired_locked()
            return {
                "backend": "memory",
                "tracked_sessions": len(self._usage),
                "ttl_seconds": self._ttl_seconds,
            }
