from __future__ import annotations

import os
from functools import lru_cache

from redis import Redis


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@lru_cache(maxsize=1)
def get_redis() -> Redis:
    url = os.environ.get("SYNQC_REDIS_URL", "redis://localhost:6379/0")
    socket_timeout = _env_float("SYNQC_REDIS_SOCKET_TIMEOUT_SECONDS", 5.0)
    return Redis.from_url(
        url,
        decode_responses=True,
        socket_timeout=socket_timeout,
        health_check_interval=30,
    )
