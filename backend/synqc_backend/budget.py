from __future__ import annotations

import threading
import time
from typing import Dict, Tuple

import redis


class BudgetTracker:
    """Track and enforce per-session shot budgets with optional Redis backing.

    When a Redis URL is provided, we use an atomic Lua script to ensure shot
    accounting works correctly across multiple workers or processes. If Redis is
    not configured, we fall back to a thread-safe in-memory counter so the
    service can still operate in dev environments.
    """

    _LUA_RESERVE = """
    local current = redis.call('GET', KEYS[1])
    if not current then
      current = 0
    else
      current = tonumber(current)
    end

    local requested = tonumber(ARGV[1])
    local session_max = tonumber(ARGV[2])
    local ttl = tonumber(ARGV[3])

    local new_total = current + requested
    if new_total > session_max then
      return {0, current}
    end

    redis.call('SET', KEYS[1], new_total, 'EX', ttl)
    return {1, new_total}
    """

    def __init__(self, redis_url: str | None, session_ttl_seconds: int = 3600) -> None:
        self._redis_url = redis_url
        self._session_ttl_seconds = session_ttl_seconds
        self._lock = threading.Lock()
        self._in_memory_usage: dict[str, tuple[int, float]] = {}
        self._client = redis.Redis.from_url(redis_url) if redis_url else None
        self._reserve_script = (
            self._client.register_script(self._LUA_RESERVE) if self._client else None
        )

    def reserve(self, session_id: str, requested: int, max_shots_per_session: int) -> Tuple[bool, int]:
        """Try to reserve ``requested`` shots for a session.

        Returns a tuple of (accepted, new_usage_or_current_usage).
        When accepted is False, the second element represents the current usage
        so callers can derive remaining budget.
        """

        if self._client and self._reserve_script:
            accepted, usage = self._reserve_script(
                keys=[self._session_key(session_id)],
                args=[requested, max_shots_per_session, self._session_ttl_seconds],
            )
            return bool(accepted), int(usage)

        with self._lock:
            self._evict_expired_locked()
            current, _ = self._in_memory_usage.get(session_id, (0, time.time()))
            new_total = current + requested
            if new_total > max_shots_per_session:
                return False, current
            self._in_memory_usage[session_id] = (new_total, time.time())
            return True, new_total

    def _session_key(self, session_id: str) -> str:
        return f"synqc:session:{session_id}:shots"

    def health_summary(self) -> Dict[str, object]:
        """Return a lightweight health summary for monitoring and /health output."""

        if self._client:
            try:
                self._client.ping()
                session_keys = self._count_session_keys()
                return {
                    "backend": "redis",
                    "redis_url": self._redis_url,
                    "redis_connected": True,
                    "session_keys": session_keys,
                    "session_ttl_seconds": self._session_ttl_seconds,
                }
            except Exception as exc:  # noqa: BLE001 - we surface connection problems
                return {
                    "backend": "redis",
                    "redis_url": self._redis_url,
                    "redis_connected": False,
                    "error": str(exc),
                }

        with self._lock:
            self._evict_expired_locked()
            return {
                "backend": "memory",
                "session_keys": len(self._in_memory_usage),
                "session_ttl_seconds": self._session_ttl_seconds,
            }

    def _count_session_keys(self) -> int:
        if not self._client:
            self._evict_expired_locked()
            return len(self._in_memory_usage)

        count = 0
        for _ in self._client.scan_iter(match="synqc:session:*:shots", count=200):
            count += 1
        return count

    def _evict_expired_locked(self) -> None:
        """Remove expired in-memory session entries (lock must be held)."""

        now = time.time()
        ttl = self._session_ttl_seconds
        expired = [sid for sid, (_, ts) in self._in_memory_usage.items() if now - ts >= ttl]
        for sid in expired:
            self._in_memory_usage.pop(sid, None)
