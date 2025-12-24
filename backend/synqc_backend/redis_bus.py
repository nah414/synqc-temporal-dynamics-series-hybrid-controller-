"""Async Redis utilities for pub/sub health checks and event publishing."""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

from redis.asyncio import Redis


@dataclass(frozen=True)
class RedisSettings:
    enabled: bool
    url: str
    events_channel: str
    client_name: str


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def get_redis_settings() -> RedisSettings:
    enabled = _truthy(os.getenv("REDIS_ENABLED", "true"))
    url = (os.getenv("REDIS_URL", os.getenv("SYNQC_REDIS_URL", "redis://localhost:6379/0")) or "").strip()
    events_channel = (os.getenv("REDIS_EVENTS_CHANNEL", "synqc:events") or "").strip() or "synqc:events"
    client_name = (os.getenv("REDIS_CLIENT_NAME", "synqc-backend") or "").strip() or "synqc-backend"
    return RedisSettings(enabled=enabled, url=url, events_channel=events_channel, client_name=client_name)


_REDIS: Optional[Redis] = None
_REDIS_LOCK = asyncio.Lock()


async def get_redis() -> Redis:
    global _REDIS
    settings = get_redis_settings()
    if not settings.enabled:
        raise RuntimeError("Redis disabled (REDIS_ENABLED=false)")

    if _REDIS is not None:
        return _REDIS

    async with _REDIS_LOCK:
        if _REDIS is None:
            _REDIS = Redis.from_url(
                settings.url,
                decode_responses=True,
                health_check_interval=30,
                client_name=settings.client_name,
            )
    return _REDIS


async def close_redis() -> None:
    global _REDIS
    if _REDIS is not None:
        try:
            await _REDIS.close()
        finally:
            _REDIS = None


async def redis_ping() -> Dict[str, Any]:
    settings = get_redis_settings()
    if not settings.enabled:
        return {"enabled": False, "ok": False, "detail": "disabled"}

    try:
        client = await get_redis()
        t0 = time.perf_counter()
        ok = await client.ping()
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "enabled": True,
            "ok": bool(ok),
            "latency_ms": latency_ms,
            "client": settings.client_name,
        }
    except Exception as exc:  # pragma: no cover - runtime probe
        return {
            "enabled": True,
            "ok": False,
            "detail": repr(exc),
            "client": settings.client_name,
        }


def _now_ms() -> int:
    return int(time.time() * 1000)


async def publish_event(topic: str, payload: Dict[str, Any], *, channel: str | None = None) -> str:
    settings = get_redis_settings()
    if not settings.enabled:
        return ""

    event_id = str(uuid.uuid4())
    envelope = {
        "id": event_id,
        "ts_ms": _now_ms(),
        "topic": topic,
        "source": settings.client_name,
        "payload": payload,
    }
    message = json.dumps(envelope, separators=(",", ":"), ensure_ascii=False)

    client = await get_redis()
    await client.publish(channel or settings.events_channel, message)
    return event_id
