from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from .security import normalize_email


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=12, max_length=256)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = normalize_email(v)
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email format")
        return v


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return normalize_email(v)


class UserOut(BaseModel):
    id: int
    email: str
    is_admin: bool
    created_at: float


class MeResponse(BaseModel):
    kind: str
    user: Optional[UserOut] = None
    scopes: list[str] = Field(default_factory=list)


class TokenCreateRequest(BaseModel):
    label: str | None = Field(default=None, max_length=80)
    scopes: list[str] = Field(default_factory=lambda: ["*"])
    # seconds from now; null => no expiration
    expires_in_seconds: int | None = Field(default=None, ge=60)

    @field_validator("scopes")
    @classmethod
    def _scopes(cls, v: list[str]) -> list[str]:
        if not v:
            return ["*"]
        out = [s.strip() for s in v if s and s.strip()]
        return out or ["*"]


class TokenOut(BaseModel):
    id: str
    label: str | None = None
    prefix: str
    scopes: list[str]
    created_at: float
    expires_at: float | None = None
    last_used_at: float | None = None
    revoked_at: float | None = None


class TokenCreateResponse(BaseModel):
    token: str
    token_id: str
    prefix: str
    scopes: list[str]
    expires_at: float | None = None
