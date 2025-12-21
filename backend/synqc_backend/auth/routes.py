from __future__ import annotations

import time
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from ..config import settings
from .deps import Principal, get_principal, get_auth_store, require_csrf, require_scopes
from .schemas import LoginRequest, MeResponse, RegisterRequest, TokenCreateRequest, TokenCreateResponse, TokenOut, UserOut
from .security import hash_password
from .store import AuthStore


router = APIRouter()


def _cookie_params() -> dict:
    secure = bool(getattr(settings, "cookie_secure", False))
    samesite = str(getattr(settings, "cookie_samesite", "lax")).lower()
    if samesite not in ("lax", "strict", "none"):
        samesite = "lax"
    return {"secure": secure, "samesite": samesite}


def _user_out(user: dict) -> UserOut:
    return UserOut(
        id=int(user["id"]),
        email=str(user["email"]),
        is_admin=bool(int(user["is_admin"])),
        created_at=float(user["created_at"]),
    )


@router.post("/register", response_model=UserOut)
def register(req: RegisterRequest, store: AuthStore = Depends(get_auth_store)) -> UserOut:
    """
    Bootstrap registration:
    - If no users exist yet: allow creating the first (admin) user.
    - Otherwise: reject (you can add an admin-only invite flow later).
    """
    if store.user_count() > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "registration_disabled", "message": "Registration is disabled after bootstrap"},
        )

    iters = int(getattr(settings, "password_pbkdf2_iterations", 260_000))
    pw_hash = hash_password(req.password, iters)
    user = store.create_user(req.email, pw_hash, is_admin=True)
    return _user_out(user)


@router.get("/me", response_model=MeResponse)
def me(principal: Principal = Depends(get_principal), store: AuthStore = Depends(get_auth_store)) -> MeResponse:
    if principal.kind == "anonymous":
        return MeResponse(kind="anonymous", user=None, scopes=[])

    if principal.user_id is not None:
        user = store.get_user_by_id(principal.user_id)
        if not user:
            raise HTTPException(status_code=401, detail={"code": "unauthorized", "message": "Invalid user"})
        return MeResponse(kind=principal.kind, user=_user_out(user), scopes=sorted(principal.scopes))

    return MeResponse(kind=principal.kind, user=None, scopes=sorted(principal.scopes))


# -------------------------
# Session-cookie auth
# -------------------------
@router.post("/session/login", response_model=UserOut)
def session_login(req: LoginRequest, response: Response, store: AuthStore = Depends(get_auth_store)) -> UserOut:
    user = store.verify_credentials(req.email, req.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "bad_credentials"})

    ttl = int(getattr(settings, "session_ttl_seconds", 60 * 60 * 24 * 7))
    sid, csrf_token, _ = store.create_session(int(user["id"]), ttl)

    params = _cookie_params()
    response.set_cookie(
        key=getattr(settings, "session_cookie_name", "synqc_session"),
        value=sid,
        httponly=True,
        max_age=ttl,
        path="/",
        **params,
    )
    response.set_cookie(
        key=getattr(settings, "csrf_cookie_name", "synqc_csrf"),
        value=csrf_token,
        httponly=False,
        max_age=ttl,
        path="/",
        **params,
    )
    return _user_out(user)


@router.post("/session/logout")
def session_logout(request: Request, response: Response, store: AuthStore = Depends(get_auth_store)) -> dict:
    sid = request.cookies.get(getattr(settings, "session_cookie_name", "synqc_session"))
    if sid:
        store.revoke_session(sid)

    params = _cookie_params()
    response.delete_cookie(getattr(settings, "session_cookie_name", "synqc_session"), path="/", **params)
    response.delete_cookie(getattr(settings, "csrf_cookie_name", "synqc_csrf"), path="/", **params)
    return {"ok": True}


# -------------------------
# API Tokens (scoped, rotatable)
# -------------------------
@router.post(
    "/tokens",
    response_model=TokenCreateResponse,
    dependencies=[Depends(require_csrf)],
)
def create_token(
    req: TokenCreateRequest,
    principal: Principal = Depends(require_scopes("tokens:write")),
    store: AuthStore = Depends(get_auth_store),
) -> TokenCreateResponse:
    if principal.user_id is None:
        raise HTTPException(status_code=401, detail={"code": "unauthorized"})

    expires_at = None
    if req.expires_in_seconds is not None:
        expires_at = time.time() + float(req.expires_in_seconds)

    token, row = store.create_api_token(
        user_id=int(principal.user_id),
        scopes=req.scopes,
        label=req.label,
        expires_at=expires_at,
    )

    return TokenCreateResponse(
        token=token,
        token_id=str(row["id"]),
        prefix=str(row["prefix"]),
        scopes=req.scopes,
        expires_at=expires_at,
    )


@router.get("/tokens", response_model=list[TokenOut])
def list_tokens(
    principal: Principal = Depends(require_scopes("tokens:read")),
    store: AuthStore = Depends(get_auth_store),
) -> list[TokenOut]:
    if principal.user_id is None:
        raise HTTPException(status_code=401, detail={"code": "unauthorized"})
    rows = store.list_api_tokens(int(principal.user_id))
    return [TokenOut(**r) for r in rows]


@router.post("/tokens/{token_id}/revoke", dependencies=[Depends(require_csrf)])
def revoke_token(
    token_id: str,
    principal: Principal = Depends(require_scopes("tokens:write")),
    store: AuthStore = Depends(get_auth_store),
) -> dict:
    if principal.user_id is None:
        raise HTTPException(status_code=401, detail={"code": "unauthorized"})
    ok = store.revoke_api_token(token_id, user_id=int(principal.user_id))
    return {"ok": ok}
