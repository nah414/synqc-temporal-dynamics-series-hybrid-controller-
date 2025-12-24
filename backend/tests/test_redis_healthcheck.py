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


def test_resolve_settings_env_overrides(monkeypatch):
    monkeypatch.delenv("SYNQC_REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_EVENTS_CHANNEL", raising=False)

    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/1")
    monkeypatch.setenv("SYNQC_REDIS_URL", "redis://localhost:6379/2")
    monkeypatch.setenv("REDIS_EVENTS_CHANNEL", "custom-channel")

    url, channel = redis_healthcheck._resolve_settings()

    assert url == "redis://localhost:6379/2"
    assert channel == "custom-channel"

    monkeypatch.delenv("SYNQC_REDIS_URL", raising=False)

    url, channel = redis_healthcheck._resolve_settings()

    assert url == "redis://localhost:6379/1"
    assert channel == "custom-channel"


def test_check_redis_connectivity_ping_failure(monkeypatch):
    class _FailPingRedis(_StubRedis):
        def ping(self):  # pragma: no cover - exercised
            self.pings += 1
            raise redis_healthcheck.redis.RedisError("ping failed")

    stub = _FailPingRedis()

    monkeypatch.setattr(
        redis_healthcheck.redis.Redis,
        "from_url",
        classmethod(lambda cls, url: stub),
    )

    ok, message = redis_healthcheck.check_redis_connectivity()

    assert ok is False
    assert "ping failed" in message.lower()
    assert stub.pings == 1
    assert stub.publishes == []


def test_check_redis_connectivity_publish_failure(monkeypatch):
    class _FailPublishRedis(_StubRedis):
        def publish(self, channel, message):  # pragma: no cover - exercised
            self.publishes.append((channel, message))
            raise redis_healthcheck.redis.RedisError("publish failed")

    stub = _FailPublishRedis()

    monkeypatch.setattr(
        redis_healthcheck.redis.Redis,
        "from_url",
        classmethod(lambda cls, url: stub),
    )

    ok, message = redis_healthcheck.check_redis_connectivity()

    assert ok is False
    assert "publish failed" in message.lower()
    assert stub.pings == 1
    assert stub.publishes == [(redis_healthcheck.DEFAULT_CHANNEL, "healthcheck")]


def test_main_returns_zero_on_success(monkeypatch, capsys):
    monkeypatch.setattr(
        redis_healthcheck,
        "check_redis_connectivity",
        lambda: (True, "ok message"),
    )

    exit_code = redis_healthcheck.main()

    captured = capsys.readouterr()
    assert "ok message" in captured.out
    assert exit_code == 0


def test_main_returns_one_on_failure(monkeypatch, capsys):
    monkeypatch.setattr(
        redis_healthcheck,
        "check_redis_connectivity",
        lambda: (False, "failure message"),
    )

    exit_code = redis_healthcheck.main()

    captured = capsys.readouterr()
    assert "failure message" in captured.out or "failure message" in captured.err
    assert exit_code == 1
