from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from fastapi import Depends, Header, HTTPException, Request, status

from ..config import settings
from .store import AuthStore


@dataclass(frozen=True)
class Principal:
    kind: Literal["anonymous", "api_key_admin", "user_session", "api_token"]
    user_id: int | None
    email: str | None
    is_admin: bool
    scopes: set[str]


def get_auth_store(request: Request) -> AuthStore:
    store = getattr(request.app.state, "auth_store", None)
    if store is None:
        raise RuntimeError("AuthStore is not configured on app.state.auth_store")
    return store


def _parse_bearer(authorization: str | None) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2:
        return None
    if parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def auth_required() -> bool:
    # Keep backward compatibility: if SYNQC_API_KEY is set, auth is required.
    return bool(settings.api_key) or bool(getattr(settings, "auth_required", False))


def get_principal(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
    store: AuthStore = Depends(get_auth_store),
) -> Principal:
    bearer = _parse_bearer(authorization)

    # 1) Legacy/global API key (admin bypass)
    if settings.api_key:
        if x_api_key and x_api_key == settings.api_key:
            return Principal(kind="api_key_admin", user_id=None, email=None, is_admin=True, scopes={"*"})
        if bearer and bearer == settings.api_key:
            return Principal(kind="api_key_admin", user_id=None, email=None, is_admin=True, scopes={"*"})

    # 2) Session cookie auth
    sess_cookie = getattr(settings, "session_cookie_name", "synqc_session")
    session_id = request.cookies.get(sess_cookie)
    if session_id:
        sess = store.get_session(session_id)
        if sess:
            user = store.get_user_by_id(int(sess["user_id"]))
            if user:
                scopes = {"*"} if int(user["is_admin"]) else {"*"}
                return Principal(
                    kind="user_session",
                    user_id=int(user["id"]),
                    email=str(user["email"]),
                    is_admin=bool(int(user["is_admin"])),
                    scopes=scopes,
                )

    # 3) Bearer token: API token
    if bearer:
        info2 = store.verify_api_token(bearer)
        if info2:
            scopes = set(info2.get("scopes") or [])
            if info2.get("is_admin"):
                scopes.add("*")
            return Principal(
                kind="api_token",
                user_id=int(info2["user_id"]),
                email=str(info2["email"]),
                is_admin=bool(info2["is_admin"]),
                scopes=scopes,
            )

    # 4) If auth not required, allow anonymous
    if not auth_required():
        return Principal(kind="anonymous", user_id=None, email=None, is_admin=False, scopes=set())

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "unauthorized", "message": "Authentication required"},
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_scopes(*required: str):
    def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        if not auth_required():
            return principal
        if principal.kind == "anonymous":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "unauthorized", "message": "Authentication required"},
            )
        if "*" in principal.scopes:
            return principal
        missing = [s for s in required if s not in principal.scopes]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "missing_scope", "missing": missing},
            )
        return principal

    return _dep


def require_csrf(request: Request) -> None:
    """
    Enforce CSRF only for session-cookie authenticated requests and only for unsafe methods.
    (API token auth doesn't need CSRF protection.)
    """
    if request.method.upper() in ("GET", "HEAD", "OPTIONS"):
        return

    sess_cookie = getattr(settings, "session_cookie_name", "synqc_session")
    csrf_cookie_name = getattr(settings, "csrf_cookie_name", "synqc_csrf")
    session_id = request.cookies.get(sess_cookie)
    if not session_id:
        return

    csrf_cookie = request.cookies.get(csrf_cookie_name)
    csrf_header = request.headers.get("X-CSRF-Token")
    if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "csrf_failed", "message": "Missing/invalid CSRF token"},
        )
