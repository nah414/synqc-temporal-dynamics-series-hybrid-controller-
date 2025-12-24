from synqc_backend import redis_healthcheck


class _StubRedis:
    def __init__(self):
        self.pings = 0
        self.publishes = []

    def ping(self):  # pragma: no cover - exercised
        self.pings += 1
        return True

    def publish(self, channel, message):  # pragma: no cover - exercised
        self.publishes.append((channel, message))
        return 0


def test_check_redis_connectivity_success(monkeypatch):
    stub = _StubRedis()

    monkeypatch.setattr(
        redis_healthcheck.redis.Redis,
        "from_url",
        classmethod(lambda cls, url: stub),
    )

    ok, message = redis_healthcheck.check_redis_connectivity()

    assert ok is True
    assert "Redis ping OK" in message
    assert "published healthcheck" in message
    assert stub.pings == 1
    assert stub.publishes == [(redis_healthcheck.DEFAULT_CHANNEL, "healthcheck")]
