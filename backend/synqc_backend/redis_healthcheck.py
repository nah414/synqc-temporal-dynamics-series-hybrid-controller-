"""Runtime Redis connectivity probe for containerized deployments."""

from __future__ import annotations

import os
import sys

import redis
from redis.exceptions import RedisError

DEFAULT_CHANNEL = "synqc:events"
DEFAULT_URL = "redis://redis:6379/0"


def _resolve_settings() -> tuple[str, str]:
    redis_url = (
        os.getenv("REDIS_URL")
        or os.getenv("SYNQC_REDIS_URL")
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

    try:
        client.ping()
    except RedisError as exc:  # pragma: no cover - simple runtime probe
        return False, f"Redis ping failed for {redis_url}: {exc}"

    try:
        subscribers = client.publish(channel, "healthcheck")
    except RedisError as exc:  # pragma: no cover - simple runtime probe
        return False, f"Redis publish failed on {channel}: {exc}"

    return True, (
        f"Redis ping OK for {redis_url}; published healthcheck to '{channel}' "
        f"(subscribers={subscribers})"
    )


def main() -> int:
    ok, message = check_redis_connectivity()
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
