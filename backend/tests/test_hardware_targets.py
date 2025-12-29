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


def _reload_app(monkeypatch, allow_remote: bool):
    monkeypatch.setenv("SYNQC_ALLOWED_ORIGINS", "http://localhost")
    monkeypatch.setenv("SYNQC_AUTH_REQUIRED", "false")
    monkeypatch.setenv("SYNQC_ENV", "dev")
    monkeypatch.setenv("SYNQC_ALLOW_REMOTE_HARDWARE", "true" if allow_remote else "false")
    monkeypatch.setenv("SYNQC_ENABLE_METRICS", "false")

    import synqc_backend.settings as settings_module
    import synqc_backend.api as api_module

    importlib.reload(settings_module)
    import synqc_backend.config as config_module
    importlib.reload(config_module)
    importlib.reload(api_module)
    return api_module.app


def test_hardware_targets_includes_providers_when_enabled(monkeypatch):
    app = _reload_app(monkeypatch, allow_remote=True)
    status, body = asyncio.run(_send_request(app, "/hardware/targets"))

    assert status == 200
    ids = {t["id"] for t in __import__("json").loads(body)["targets"]}

    assert "sim_local" in ids
    assert {"ibm_quantum", "aws_braket", "azure_quantum", "ionq_cloud", "rigetti_forest"}.issubset(ids)


def test_hardware_targets_filter_when_remote_disabled(monkeypatch):
    app = _reload_app(monkeypatch, allow_remote=False)
    status, body = asyncio.run(_send_request(app, "/hardware/targets"))

    assert status == 200
    targets = __import__("json").loads(body)["targets"]
    assert all(t["kind"] == "sim" for t in targets)
