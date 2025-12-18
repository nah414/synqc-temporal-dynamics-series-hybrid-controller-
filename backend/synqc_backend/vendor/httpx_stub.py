from __future__ import annotations

import asyncio
import json
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Any, Mapping, Optional


class HTTPStatusError(Exception):
    """Minimal substitute for httpx.HTTPStatusError."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.response = type("Obj", (), {"status_code": status_code})  # lightweight shim


@dataclass
class Timeout:
    """Compatibility shim for httpx.Timeout."""

    timeout: float

    def __init__(self, timeout: float | int) -> None:
        self.timeout = float(timeout)


class Response:
    def __init__(self, status_code: int, content: bytes, headers: Mapping[str, str] | None = None) -> None:
        self.status_code = status_code
        self.content = content
        self.headers = dict(headers or {})

    @property
    def text(self) -> str:
        try:
            return self.content.decode("utf-8")
        except Exception:
            return self.content.decode(errors="replace")

    def json(self) -> Any:
        return json.loads(self.text or "{}")

    def raise_for_status(self) -> None:
        if 200 <= self.status_code < 400:
            return
        raise HTTPStatusError(f"HTTP {self.status_code}", status_code=self.status_code)


class AsyncClient:
    """Tiny async HTTP client to mimic a subset of httpx.AsyncClient."""

    def __init__(self, timeout: Timeout | float | int = 5.0) -> None:
        self._timeout = timeout.timeout if isinstance(timeout, Timeout) else float(timeout)

    async def __aenter__(self) -> "AsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None

    async def get(self, url: str, headers: Optional[Mapping[str, str]] = None) -> Response:
        return await self._request("GET", url, None, headers)

    async def post(
        self,
        url: str,
        json: Any = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> Response:
        body: bytes | None = None
        req_headers = dict(headers or {})
        if json is not None:
            body = json_dumps(json)
            req_headers.setdefault("Content-Type", "application/json")
        return await self._request("POST", url, body, req_headers)

    async def _request(self, method: str, url: str, body: bytes | None, headers: Mapping[str, str] | None) -> Response:
        return await asyncio.to_thread(self._sync_request, method, url, body, headers)

    def _sync_request(self, method: str, url: str, body: bytes | None, headers: Mapping[str, str] | None) -> Response:
        request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as resp:
                content = resp.read()
                status = getattr(resp, "status", 200)
                return Response(status_code=status, content=content, headers=resp.headers)
        except urllib.error.HTTPError as exc:
            return Response(status_code=exc.code, content=exc.read(), headers=exc.headers)


def json_dumps(payload: Any) -> bytes:
    return json.dumps(payload).encode("utf-8")


__version__ = "0.0-stub"
