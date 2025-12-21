from __future__ import annotations

import logging
import threading
import time
from typing import Dict

import redis

logger = logging.getLogger(__name__)


class BudgetBackendUnavailable(RuntimeError):
    """Raised when the configured budget backend is unavailable and fail-open is disabled."""


class BudgetTracker:
    """
    Tracks per-session shot usage with a hard cap.

    Production mode (recommended):
      - Use Redis (atomic reserve via Lua, shared across replicas)
      - Fail CLOSED on Redis errors (deny reserves) to prevent runaway cost.

    Dev mode:
      - Optional fail-open fallback to in-memory.
    """

    # KEYS[1] = session key
    # ARGV[1] = requested
    # ARGV[2] = max
    # ARGV[3] = ttl_seconds
    _LUA_RESERVE = r"""
local key = KEYS[1]
local requested = tonumber(ARGV[1]) or 0
local maxv = tonumber(ARGV[2]) or 0
local ttl = tonumber(ARGV[3]) or 0

local current = tonumber(redis.call("GET", key) or "0")
local new_total = current + requested

if new_total > maxv then
  -- Sliding TTL: keep the session "alive" even when over budget
  if ttl > 0 then
    redis.call("EXPIRE", key, ttl)
  end
  return {0, current}
end

-- Accepted: store new total and refresh TTL
if ttl > 0 then
  redis.call("SET", key, tostring(new_total), "EX", ttl)
else
  redis.call("SET", key, tostring(new_total))
end

return {1, new_total}
"""

    def __init__(
        self,
        redis_url: str | None,
        session_ttl_seconds: int = 3600,
        *,
        fail_open_on_redis_error: bool = False,
    ) -> None:
        self._redis_url = redis_url
        self._session_ttl_seconds = int(session_ttl_seconds)
        self._fail_open_on_redis_error = bool(fail_open_on_redis_error)

        self._lock = threading.Lock()
        # session_id -> (shots_used, last_seen_ts)
        self._in_memory_usage: dict[str, tuple[int, float]] = {}

        self._client: redis.Redis | None = None
        self._reserve_script = None
        self._redis_last_error: str | None = None

        if redis_url:
            self._client = redis.Redis.from_url(redis_url)
            self._reserve_script = self._client.register_script(self._LUA_RESERVE)

    def _session_key(self, session_id: str) -> str:
        return f"synqc:session:{session_id}:shots"

    def reserve(
        self, session_id: str, requested: int, max_shots_per_session: int
    ) -> tuple[bool, int]:
        """
        Attempt to reserve `requested` shots for session_id.

        Returns (accepted, usage_after_or_current).
        """
        requested_i = int(requested)
        max_i = int(max_shots_per_session)

        if requested_i < 0:
            raise ValueError("requested must be >= 0")
        if max_i <= 0:
            # Treat "no max" as disallowed; better to be explicit in config.
            raise ValueError("max_shots_per_session must be > 0")

        # Redis path (shared across replicas)
        if self._client and self._reserve_script:
            try:
                accepted, usage = self._reserve_script(
                    keys=[self._session_key(session_id)],
                    args=[requested_i, max_i, self._session_ttl_seconds],
                )
                self._redis_last_error = None
                return bool(int(accepted)), int(usage)
            except Exception as exc:
                self._redis_last_error = f"{type(exc).__name__}: {exc}"
                logger.exception("BudgetTracker Redis error")
                if not self._fail_open_on_redis_error:
                    # Fail closed: deny all reserves when budget backend is down.
                    raise BudgetBackendUnavailable(
                        "Budget backend unavailable (Redis error)"
                    ) from exc
                # Fail open: fallback to in-memory
                return self._reserve_memory(session_id, requested_i, max_i)

        # In-memory path (single-process only)
        return self._reserve_memory(session_id, requested_i, max_i)

    def _reserve_memory(
        self, session_id: str, requested: int, max_shots_per_session: int
    ) -> tuple[bool, int]:
        now = time.time()
        with self._lock:
            self._evict_expired_locked(now)
            current, _last_seen = self._in_memory_usage.get(session_id, (0, now))
            new_total = current + requested

            # Sliding TTL: refresh last_seen on *any* attempt
            if new_total > max_shots_per_session:
                self._in_memory_usage[session_id] = (current, now)
                return False, current

            self._in_memory_usage[session_id] = (new_total, now)
            return True, new_total

    def get_usage(self, session_id: str) -> int:
        if self._client:
            try:
                val = self._client.get(self._session_key(session_id))
                return int(val) if val is not None else 0
            except Exception:
                # If Redis is flaky, don't explode read paths; usage is advisory.
                pass
        now = time.time()
        with self._lock:
            self._evict_expired_locked(now)
            shots, _ = self._in_memory_usage.get(session_id, (0, now))
            return shots

    def remaining_shots(self, session_id: str, max_shots_per_session: int) -> int:
        usage = self.get_usage(session_id)
        return max(0, int(max_shots_per_session) - int(usage))

    def reset_session(self, session_id: str) -> None:
        """Dangerous in prod (can erase budgets). Keep for admin/debug only."""
        if self._client:
            try:
                self._client.delete(self._session_key(session_id))
            except Exception:
                pass
        with self._lock:
            self._in_memory_usage.pop(session_id, None)

    def health_summary(self) -> Dict[str, object]:
        if self._client:
            ok = True
            try:
                self._client.ping()
            except Exception:
                ok = False
            return {
                "backend": "redis",
                "redis_ok": ok,
                "redis_url_set": bool(self._redis_url),
                "session_ttl_seconds": self._session_ttl_seconds,
                "redis_last_error": self._redis_last_error,
                "session_keys": self._count_session_keys(),
            }

        now = time.time()
        with self._lock:
            self._evict_expired_locked(now)
            return {
                "backend": "memory",
                "session_ttl_seconds": self._session_ttl_seconds,
                "session_keys": len(self._in_memory_usage),
            }

    def _count_session_keys(self) -> int:
        if not self._client:
            now = time.time()
            with self._lock:
                self._evict_expired_locked(now)
                return len(self._in_memory_usage)

        count = 0
        try:
            for _ in self._client.scan_iter(match="synqc:session:*:shots", count=200):
                count += 1
        except Exception:
            # Don't fail health checks due to SCAN issues.
            pass
        return count

    def _evict_expired_locked(self, now: float | None = None) -> None:
        """Remove expired in-memory session entries (lock must be held)."""
        now = time.time() if now is None else now
        ttl = self._session_ttl_seconds
        expired = [sid for sid, (_, ts) in self._in_memory_usage.items() if now - ts >= ttl]
        for sid in expired:
            self._in_memory_usage.pop(sid, None)
