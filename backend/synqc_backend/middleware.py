from __future__ import annotations

import time
import uuid
from tempfile import SpooledTemporaryFile
from typing import Callable, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .redis_client import get_redis
from . import settings as settings_module


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


class MaxRequestSizeMiddleware(BaseHTTPMiddleware):
    """Reject requests larger than the configured byte limit."""

    def __init__(self, app: FastAPI, *, max_size: int):
        super().__init__(app)
        self.max_size = max_size
        self._safe_content_types = {
            "application/json",
            "application/x-www-form-urlencoded",
            "multipart/form-data",
            "text/plain",
        }
        # SpooledTemporaryFile keeps small payloads in memory and spills to disk for larger bodies.
        self._spool_threshold_bytes = min(self.max_size, 1_000_000)
        self._receive_chunk_size = 64 * 1024

    async def dispatch(self, request: Request, call_next: Callable):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.max_size:
                    return JSONResponse(status_code=413, content={"error": {"code": "too_large"}})
            except ValueError:  # pragma: no cover - malformed header
                return JSONResponse(status_code=400, content={"error": {"code": "invalid_content_length"}})

            content_type = request.headers.get("content-type", "").split(";")[0].strip()
            # For multipart bodies we still stream through a spooled file to avoid buffering large
            # uploads in memory even when the client provides an honest content-length.
            if content_type in self._safe_content_types and content_type != "multipart/form-data":
                return await call_next(request)

        spooled_body = SpooledTemporaryFile(max_size=self._spool_threshold_bytes)
        total = 0
        try:
            async for chunk in request.stream():
                total += len(chunk)
                if total > self.max_size:
                    return JSONResponse(status_code=413, content={"error": {"code": "too_large"}})
                spooled_body.write(chunk)

            spooled_body.seek(0)

            async def receive() -> dict:
                data = spooled_body.read(self._receive_chunk_size)
                if data:
                    return {"type": "http.request", "body": data, "more_body": True}
                return {"type": "http.request", "body": b"", "more_body": False}

            request._receive = receive  # type: ignore[attr-defined]
            if hasattr(request, "_body"):
                delattr(request, "_body")  # type: ignore[attr-defined]
            request._stream_consumed = False  # type: ignore[attr-defined]
            return await call_next(request)
        finally:
            spooled_body.close()


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, api_key: Optional[str]):
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request: Request, call_next: Callable):
        if not self.api_key:
            return await call_next(request)

        provided = request.headers.get("X-API-Key", "")
        if provided != self.api_key:
            return JSONResponse(
                status_code=401,
                content={"error": {"code": "unauthorized", "message": "Missing or invalid API key."}},
            )

        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, requests_per_minute: int):
        super().__init__(app)
        self.limit = requests_per_minute

    async def dispatch(self, request: Request, call_next: Callable):
        if self.limit <= 0:
            return await call_next(request)

        ident = request.headers.get("X-API-Key") or (request.client.host if request.client else "unknown")
        window = int(time.time() // 60)
        key = f"synqc:ratelimit:{ident}:{window}"

        r = get_redis()
        try:
            n = r.incr(key)
            if n == 1:
                r.expire(key, 90)
        except Exception:
            return await call_next(request)

        if n > self.limit:
            return JSONResponse(
                status_code=429,
                content={"error": {"code": "rate_limited", "message": "Too many requests. Slow down."}},
            )

        return await call_next(request)


def add_default_middlewares(app: FastAPI) -> None:
    app.add_middleware(RequestIdMiddleware)
    settings = settings_module.settings
    api_key = settings.api_key
    if api_key:
        app.add_middleware(ApiKeyAuthMiddleware, api_key=api_key)
    rpm = settings.rate_limit_per_minute
    app.add_middleware(RateLimitMiddleware, requests_per_minute=rpm)
    app.add_middleware(MaxRequestSizeMiddleware, max_size=settings.max_request_bytes)
