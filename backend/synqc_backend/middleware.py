from __future__ import annotations

import os
import time
import uuid
from typing import Callable, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .redis_client import get_redis


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, api_key: Optional[str]):
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request: Request, call_next: Callable):
        if not self.api_key:
            return await call_next(request)

        provided = request.headers.get("X-API-Key", "")
        if provided != self.api_key:
            return JSONResponse(status_code=401, content={"error": {"code": "unauthorized", "message": "Missing or invalid API key."}})

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
            return JSONResponse(status_code=429, content={"error": {"code": "rate_limited", "message": "Too many requests. Slow down."}})

        return await call_next(request)


def add_default_middlewares(app: FastAPI) -> None:
    app.add_middleware(RequestIdMiddleware)
    api_key = os.environ.get("SYNQC_API_KEY") or None
    app.add_middleware(ApiKeyAuthMiddleware, api_key=api_key)
    rpm = _env_int("SYNQC_RATE_LIMIT_PER_MINUTE", 120)
    app.add_middleware(RateLimitMiddleware, requests_per_minute=rpm)
