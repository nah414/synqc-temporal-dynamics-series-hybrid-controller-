"""Runtime Redis connectivity probe for containerized deployments."""

from __future__ import annotations

import os
import sys

import redis
from redis.exceptions import RedisError

DEFAULT_CHANNEL = "synqc:events"
DEFAULT_URL = "redis://redis:6379/0"


def _redact_url(redis_url: str) -> str:
    """Remove user info from a Redis URL for safe logging/output."""

    from urllib.parse import urlparse

    parsed = urlparse(redis_url)
    if not parsed.scheme or not parsed.hostname:
        return "redis://<redacted>"

    host = parsed.hostname
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path or ""
    return f"{parsed.scheme}://{host}{port}{path}"


def _resolve_settings() -> tuple[str, str]:
    redis_url = (
        os.getenv("SYNQC_REDIS_URL")
        or os.getenv("REDIS_URL")
        or DEFAULT_URL
    )
    channel = os.getenv("REDIS_EVENTS_CHANNEL") or DEFAULT_CHANNEL
    return redis_url, channel


def check_redis_connectivity() -> tuple[bool, str]:
    """
    Ping Redis and publish a small message to validate connectivity.

    Returns
    -------
    tuple[bool, str]
        success flag and a human-readable status message.
    """

    redis_url, channel = _resolve_settings()
    client = redis.Redis.from_url(redis_url)

    safe_url = _redact_url(redis_url)

    try:
        client.ping()
    except RedisError as exc:  # pragma: no cover - simple runtime probe
        return False, f"Redis ping failed for {safe_url}: {exc}"

    try:
        subscribers = client.publish(channel, "healthcheck")
    except RedisError as exc:  # pragma: no cover - simple runtime probe
        return False, f"Redis publish failed on {channel}: {exc}"

    return True, (
        f"Redis ping OK for {safe_url}; published healthcheck to '{channel}' "
        f"(subscribers={subscribers})"
    )


def main() -> int:
    ok, message = check_redis_connectivity()
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
