import asyncio
import importlib


async def _send_request(app, path: str):
    messages = []

    async def receive():
        if receive.called:
            return {"type": "http.disconnect"}
        receive.called = True  # type: ignore[attr-defined]
        return {"type": "http.request", "body": b"", "more_body": False}

    receive.called = False  # type: ignore[attr-defined]

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "scheme": "http",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }

    await app(scope, receive, send)
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    body_chunks = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return status, body_chunks


def _reload_app(monkeypatch, enable_shared_endpoint: bool):
    monkeypatch.setenv("SYNQC_ALLOWED_ORIGINS", "http://localhost")
    monkeypatch.setenv("SYNQC_REQUIRE_API_KEY", "false")
    monkeypatch.setenv("SYNQC_ENABLE_METRICS", "true")
    monkeypatch.setenv("SYNQC_METRICS_USE_SHARED_REGISTRY", "true")
    monkeypatch.setenv(
        "SYNQC_METRICS_SHARED_REGISTRY_ENDPOINT_ENABLED",
        "true" if enable_shared_endpoint else "false",
    )

    import synqc_backend.metrics as metrics_module

    importlib.reload(metrics_module)
    monkeypatch.setattr(metrics_module, "start_http_server", lambda *args, **kwargs: None)

    import synqc_backend.settings as settings_module
    importlib.reload(settings_module)
    import synqc_backend.config as config_module
    importlib.reload(config_module)
    import synqc_backend.api as api_module
    importlib.reload(api_module)

    return api_module.app


def test_shared_metrics_endpoint_enabled(monkeypatch):
    app = _reload_app(monkeypatch, enable_shared_endpoint=True)
    status, body = asyncio.run(_send_request(app, "/metrics"))

    assert status == 200
    assert b"synqc_queue_jobs_total" in body


def test_shared_metrics_endpoint_absent_when_disabled(monkeypatch):
    app = _reload_app(monkeypatch, enable_shared_endpoint=False)
    status, body = asyncio.run(_send_request(app, "/metrics"))

    assert status == 404
    assert b"Not Found" in body
