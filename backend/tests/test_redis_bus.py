import json
import uuid

import pytest

from synqc_backend import redis_bus


@pytest.fixture(autouse=True)
def _reset_redis_state(monkeypatch):
    # Ensure the module-level Redis client cache does not leak between tests
    monkeypatch.setattr(redis_bus, "_REDIS", None)
    monkeypatch.setenv("REDIS_ENABLED", "true")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("REDIS_EVENTS_CHANNEL", "synqc:events")
    monkeypatch.setenv("REDIS_CLIENT_NAME", "synqc-backend")
    monkeypatch.delenv("SYNQC_REDIS_URL", raising=False)
    yield
    # ensure globals cleared
    redis_bus._REDIS = None


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1", True),
        ("true", True),
        ("Yes", True),
        ("ON", True),
        ("0", False),
        ("false", False),
        (None, False),
        (" ", False),
    ],
)
def test_truthy(value, expected):
    assert redis_bus._truthy(value) is expected


def test_get_redis_settings_prefers_env(monkeypatch):
    monkeypatch.setenv("REDIS_ENABLED", "false")
    monkeypatch.setenv("REDIS_URL", "redis://example:1234/9")
    monkeypatch.setenv("REDIS_EVENTS_CHANNEL", "custom:channel")
    monkeypatch.setenv("REDIS_CLIENT_NAME", "custom-client")

    settings = redis_bus.get_redis_settings()

    assert settings.enabled is False
    assert settings.url == "redis://example:1234/9"
    assert settings.events_channel == "custom:channel"
    assert settings.client_name == "custom-client"


def test_get_redis_settings_falls_back_to_synqc_url(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("SYNQC_REDIS_URL", "redis://fallback:6379/1")

    settings = redis_bus.get_redis_settings()

    assert settings.url == "redis://fallback:6379/1"


@pytest.mark.anyio
async def test_publish_event_disabled(monkeypatch):
    monkeypatch.setenv("REDIS_ENABLED", "false")

    result = await redis_bus.publish_event("topic", {"hello": "world"})

    assert result == ""


@pytest.mark.anyio
async def test_publish_event_enqueues_payload(monkeypatch):
    published = {}

    class StubRedis:
        async def publish(self, channel, message):  # pragma: no cover - exercised
            published["channel"] = channel
            published["message"] = message

    async def fake_get_redis():
        return StubRedis()

    monkeypatch.setenv("REDIS_EVENTS_CHANNEL", "synqc:events")
    monkeypatch.setenv("REDIS_CLIENT_NAME", "client-a")
    monkeypatch.setattr(redis_bus, "get_redis", fake_get_redis)

    event_id = await redis_bus.publish_event("demo", {"foo": "bar"})

    assert uuid.UUID(event_id)  # validates format
    assert published["channel"] == "synqc:events"

    envelope = json.loads(published["message"])
    assert envelope["topic"] == "demo"
    assert envelope["source"] == "client-a"
    assert envelope["payload"] == {"foo": "bar"}
    assert envelope["id"] == event_id


@pytest.mark.anyio
async def test_publish_event_uses_custom_channel(monkeypatch):
    published = {}

    class StubRedis:
        async def publish(self, channel, message):  # pragma: no cover - exercised
            published["channel"] = channel
            published["message"] = message

    async def fake_get_redis():
        return StubRedis()

    monkeypatch.setattr(redis_bus, "get_redis", fake_get_redis)

    await redis_bus.publish_event("demo", {"foo": "bar"}, channel="custom:channel")

    assert published["channel"] == "custom:channel"


@pytest.mark.anyio
async def test_redis_ping_disabled(monkeypatch):
    monkeypatch.setenv("REDIS_ENABLED", "false")

    result = await redis_bus.redis_ping()

    assert result == {"enabled": False, "ok": False, "detail": "disabled"}


@pytest.mark.anyio
async def test_redis_ping_reports_latency(monkeypatch):
    class StubRedis:
        def __init__(self):
            self.calls = 0

        async def ping(self):  # pragma: no cover - exercised
            self.calls += 1
            return True

    stub = StubRedis()

    async def fake_get_redis():
        return stub

    monkeypatch.setattr(redis_bus, "get_redis", fake_get_redis)

    result = await redis_bus.redis_ping()

    assert result["enabled"] is True
    assert result["ok"] is True
    assert result["client"] == "synqc-backend"
    assert result["latency_ms"] >= 0
    assert stub.calls == 1
