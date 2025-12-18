import json
import pytest
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sys
import zipfile

sys.path.append(str(Path(__file__).resolve().parents[1]))

from synqc_backend.vendor.httpx_loader import load_httpx


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - HTTP verb
        body = json.dumps({"ok": True}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A003
        return


def _clear_httpx():
    sys.modules.pop("httpx", None)
    for p in list(sys.path):
        if "httpx_wheels" in p:
            sys.path.remove(p)


def _run_server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, thread, f"http://{host}:{port}/health"


async def _call_url(httpx, url: str):
    async with httpx.AsyncClient(timeout=5) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


def test_loader_falls_back_to_stub(tmp_path, monkeypatch):
    _clear_httpx()
    import importlib.util

    if importlib.util.find_spec("httpx") is not None:
        pytest.skip("real httpx available; fallback path not exercised")
    # Point to an empty directory so cached wheels are ignored.
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.setenv("SYNQC_HTTPX_VENDOR", str(empty_dir))

    httpx = load_httpx()
    assert hasattr(httpx, "AsyncClient")
    assert getattr(httpx, "__version__", "") == "0.0-stub"

    server, thread, url = _run_server()

    import asyncio

    result = asyncio.get_event_loop().run_until_complete(_call_url(httpx, url))
    assert result == {"ok": True}

    server.shutdown()
    thread.join()


def test_loader_prefers_cached_wheel(tmp_path, monkeypatch):
    _clear_httpx()

    wheel_dir = tmp_path / "httpx_wheels"
    wheel_dir.mkdir()
    wheel_path = wheel_dir / "httpx-9.9.9-py3-none-any.whl"

    with zipfile.ZipFile(wheel_path, "w") as zf:
        zf.writestr(
            "httpx/__init__.py",
            "class BaseTransport: pass\n"
            "class Request: pass\n"
            "class Response: pass\n"
            "class Timeout:\n    def __init__(self, timeout): self.timeout=float(timeout)\n"
            "class AsyncClient:\n    def __init__(self, timeout=None): self.timeout=timeout\n"
            "    async def __aenter__(self): return self\n"
            "    async def __aexit__(self, exc_type, exc, tb): return None\n"
            "    async def get(self, url, headers=None):\n"
            "        import types\n"
            "        return types.SimpleNamespace(status_code=200, json=lambda: {'ok': True}, raise_for_status=lambda: None)\n"
            "    async def post(self, url, json=None, headers=None): return await self.get(url, headers=headers)\n"
            "__version__='9.9.9'\n",
        )

    monkeypatch.setenv("SYNQC_HTTPX_VENDOR", str(wheel_dir))

    httpx = load_httpx()
    assert getattr(httpx, "__version__", "") == "9.9.9"

    server, thread, url = _run_server()

    import asyncio

    result = asyncio.get_event_loop().run_until_complete(_call_url(httpx, url))
    assert result == {"ok": True}

    server.shutdown()
    thread.join()
