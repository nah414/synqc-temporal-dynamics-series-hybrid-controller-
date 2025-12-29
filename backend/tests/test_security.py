import importlib

import asyncio
from typing import List, Tuple

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse

from synqc_backend.middleware import MaxRequestSizeMiddleware


async def _send_request(
    app,
    method: str,
    path: str,
    headers: List[Tuple[bytes, bytes]] | None = None,
    body: bytes = b"",
    body_chunks: list[bytes] | None = None,
):
    headers = headers or []
    messages = []

    chunks = list(body_chunks) if body_chunks is not None else [body]

    async def receive():
        if not chunks:
            return {"type": "http.disconnect"}
        next_chunk = chunks.pop(0)
        more_body = bool(chunks)
        return {"type": "http.request", "body": next_chunk, "more_body": more_body}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "scheme": "http",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }

    await app(scope, receive, send)
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    response_headers = next(m["headers"] for m in messages if m["type"] == "http.response.start")
    body_chunks = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return status, response_headers, body_chunks


def _reload_app(monkeypatch):
    import synqc_backend.settings as settings_module
    import synqc_backend.api as api_module

    importlib.reload(settings_module)
    import synqc_backend.config as config_module
    importlib.reload(config_module)
    importlib.reload(api_module)
    return api_module.app


def test_prod_requires_auth(monkeypatch):
    monkeypatch.setenv("SYNQC_ENV", "prod")
    monkeypatch.setenv("SYNQC_ALLOWED_ORIGINS", "https://example.com")
    monkeypatch.setenv("SYNQC_AUTH_REQUIRED", "true")
    monkeypatch.setenv("SYNQC_JWKS_URL", "https://auth.example.com/jwks")
    monkeypatch.setenv("SYNQC_AUTH_ISSUER", "https://auth.example.com/")
    monkeypatch.setenv("SYNQC_AUTH_AUDIENCE", "synqc")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    monkeypatch.setenv("SYNQC_ENABLE_METRICS", "false")
    monkeypatch.delenv("SYNQC_API_KEY", raising=False)
    app = _reload_app(monkeypatch)
    status, _, _ = asyncio.run(
        _send_request(
            app,
            "POST",
            "/experiments/run",
            headers=[(b"content-type", b"application/json")],
            body=b'{"preset":"health","hardware_target":"sim_local","shot_budget":8}',
        )
    )

    assert status == 401


def test_cors_prod_rejects_unknown_origin(monkeypatch):
    monkeypatch.setenv("SYNQC_ENV", "prod")
    monkeypatch.setenv("SYNQC_ALLOWED_ORIGINS", "https://allowed.example")
    monkeypatch.setenv("SYNQC_AUTH_REQUIRED", "true")
    monkeypatch.setenv("SYNQC_JWKS_URL", "https://auth.example.com/jwks")
    monkeypatch.setenv("SYNQC_AUTH_ISSUER", "https://auth.example.com/")
    monkeypatch.setenv("SYNQC_AUTH_AUDIENCE", "synqc")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    monkeypatch.setenv("SYNQC_API_KEY", "secret")
    monkeypatch.setenv("SYNQC_ENABLE_METRICS", "false")
    app = _reload_app(monkeypatch)
    status, _, _ = asyncio.run(
        _send_request(
            app,
            "OPTIONS",
            "/experiments/run",
            headers=[
                (b"origin", b"https://evil.example"),
                (b"access-control-request-method", b"POST"),
            ],
        )
    )

    assert status == 400


def test_request_size_limit(monkeypatch):
    monkeypatch.setenv("SYNQC_ENV", "prod")
    monkeypatch.setenv("SYNQC_ALLOWED_ORIGINS", "https://allowed.example")
    monkeypatch.setenv("SYNQC_AUTH_REQUIRED", "true")
    monkeypatch.setenv("SYNQC_JWKS_URL", "https://auth.example.com/jwks")
    monkeypatch.setenv("SYNQC_AUTH_ISSUER", "https://auth.example.com/")
    monkeypatch.setenv("SYNQC_AUTH_AUDIENCE", "synqc")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    monkeypatch.setenv("SYNQC_API_KEY", "secret")
    monkeypatch.setenv("SYNQC_MAX_REQUEST_BYTES", "10")
    monkeypatch.setenv("SYNQC_ENABLE_METRICS", "false")
    app = _reload_app(monkeypatch)
    status, _, _ = asyncio.run(
        _send_request(
            app,
            "POST",
            "/auth/register",
            headers=[(b"content-length", b"50"), (b"content-type", b"application/json")],
            body=b"x" * 50,
        )
    )

    assert status == 413


def test_request_size_limit_streaming_without_length(monkeypatch):
    monkeypatch.setenv("SYNQC_ENV", "prod")
    monkeypatch.setenv("SYNQC_ALLOWED_ORIGINS", "https://allowed.example")
    monkeypatch.setenv("SYNQC_AUTH_REQUIRED", "true")
    monkeypatch.setenv("SYNQC_JWKS_URL", "https://auth.example.com/jwks")
    monkeypatch.setenv("SYNQC_AUTH_ISSUER", "https://auth.example.com/")
    monkeypatch.setenv("SYNQC_AUTH_AUDIENCE", "synqc")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    monkeypatch.setenv("SYNQC_API_KEY", "secret")
    monkeypatch.setenv("SYNQC_MAX_REQUEST_BYTES", "16")
    monkeypatch.setenv("SYNQC_ENABLE_METRICS", "false")
    app = _reload_app(monkeypatch)

    status, _, _ = asyncio.run(
        _send_request(
            app,
            "POST",
            "/auth/register",
            headers=[(b"content-type", b"application/octet-stream")],
            body_chunks=[b"x" * 10, b"y" * 10],
        )
    )

    assert status == 413


def test_multipart_streaming_uses_spooled_body(monkeypatch):
    app = Starlette()

    @app.route("/echo", methods=["POST"])
    async def echo(request):
        body = await request.body()
        return PlainTextResponse(body)

    wrapped_app = MaxRequestSizeMiddleware(app, max_size=1024 * 1024)

    boundary = "----synqc-boundary"
    multipart_body = (
        f"--{boundary}\r\n"
        "Content-Disposition: form-data; name=\"file\"; filename=\"echo.txt\"\r\n"
        "Content-Type: text/plain\r\n\r\n"
        "hello world from multipart guardrail test\r\n"
        f"--{boundary}--\r\n"
    ).encode()

    status, _, body = asyncio.run(
        _send_request(
            wrapped_app,
            "POST",
            "/echo",
            headers=[
                (b"content-type", f"multipart/form-data; boundary={boundary}".encode()),
                (b"content-length", str(len(multipart_body)).encode()),
            ],
            body=multipart_body,
        )
    )

    assert status == 200
    assert body == multipart_body
