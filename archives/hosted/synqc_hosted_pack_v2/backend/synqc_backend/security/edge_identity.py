"""Hosted-mode middleware (optional defense-in-depth).

Purpose:
- In hosted deployments, end-user auth is enforced at the edge (nginx + oauth2-proxy).
- This middleware rejects direct API calls that do NOT come through the edge
  by requiring oauth2-proxy identity headers to be present.

Headers expected (set by nginx from oauth2-proxy via auth_request):
- X-Auth-Request-User
- X-Auth-Request-Email

Enable with:
- SYNQC_REQUIRE_EDGE_IDENTITY=true

Wire into FastAPI app early, e.g.:

from fastapi import FastAPI
from synqc_backend.security.edge_identity import RequireEdgeIdentityHeaders, should_require_edge_identity

app = FastAPI(...)
app.add_middleware(RequireEdgeIdentityHeaders, enabled=should_require_edge_identity())

"""
from __future__ import annotations

import os
from typing import Iterable, Optional, Set

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


def should_require_edge_identity() -> bool:
    v = os.getenv("SYNQC_REQUIRE_EDGE_IDENTITY", "false")
    return v.strip().lower() in {"1", "true", "yes", "on"}


class RequireEdgeIdentityHeaders(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        enabled: bool = True,
        exempt_paths: Optional[Iterable[str]] = None,
    ) -> None:
        super().__init__(app)
        self.enabled = enabled
        # Allow health checks without auth, but you may choose to protect docs.
        self.exempt_paths: Set[str] = set(exempt_paths or {
            "/health",
        })

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self.enabled:
            return await call_next(request)

        path = request.url.path
        if path in self.exempt_paths:
            return await call_next(request)

        user = request.headers.get("X-Auth-Request-User") or request.headers.get("X-Auth-Request-Email")
        if not user:
            return JSONResponse(
                {
                    "error_message": "Missing edge identity headers",
                    "action_hint": "Access the API through the hosted edge proxy (UI origin).",
                },
                status_code=401,
            )

        # Make identity available to route handlers / logging.
        request.state.edge_user = request.headers.get("X-Auth-Request-User")
        request.state.edge_email = request.headers.get("X-Auth-Request-Email")
        return await call_next(request)
