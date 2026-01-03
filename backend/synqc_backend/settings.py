from __future__ import annotations

import base64
import os
from typing import Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SynQcSettings(BaseSettings):
    """Environment-backed configuration for the SynQc backend."""

    model_config = SettingsConfigDict(
        env_prefix="SYNQC_",
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )

    env: Literal["dev", "prod"] = "dev"
    api_prefix: str = Field(default="/api", description="Hosted API prefix")

    # CORS
    allowed_origins_raw: str | None = Field(default=None, validation_alias=AliasChoices("ALLOWED_ORIGINS"))
    cors_allow_credentials: bool = Field(default=False, description="Allow credentialed CORS")

    # Auth
    auth_required: bool = Field(default=False, description="Require auth in prod")
    jwks_url: str | None = Field(default=None, description="JWKS endpoint for JWT verification")
    auth_issuer: str | None = Field(default=None, description="JWT issuer")
    auth_audience: str | None = Field(default=None, description="JWT audience")

    # Rate limiting / size caps
    rate_limit_per_minute: int = Field(default=120, ge=0)
    rate_limit_per_minute_per_user: int = Field(default=120, ge=0)
    max_request_bytes: int = Field(default=1_000_000, ge=1)

    # Persistence
    database_url: str | None = Field(default=None, description="Database connection URI")
    redis_url: str | None = Field(default=None, description="Redis connection URL for budgets and queues")

    # Encryption
    master_key: str | None = Field(default=None, description="Base64 key for encrypting provider secrets")

    # Guardrails
    allow_remote_hardware: bool = True
    allow_remote_hardware_default: bool = Field(default=True, description="Default remote hardware allowance for orgs")
    max_shots_per_experiment: int = Field(default=200_000, ge=1)
    max_shots_per_session: int = Field(default=1_000_000, ge=1)
    default_shot_budget: int = Field(default=2_048, ge=1)

    # Budget/session tracking
    session_budget_ttl_seconds: int = Field(default=3600, ge=60)
    budget_fail_open_on_redis_error: bool = Field(default=False)

    # Worker / queue
    worker_pool_size: int = Field(default=4, ge=1)
    job_graceful_shutdown_seconds: int = Field(default=5, ge=0)
    job_timeout_seconds: int = Field(default=90, ge=0)
    job_queue_max_pending: int = Field(default=1000, ge=1)
    job_queue_db_path: str = Field(default="data/jobs.sqlite3")

    # Metrics / observability
    enable_metrics: bool = Field(default=True)
    metrics_port: int = Field(default=9000, ge=1, le=65535)
    metrics_bind_address: str = Field(default="127.0.0.1")
    metrics_collection_interval_seconds: int = Field(default=15, ge=5)
    metrics_use_shared_registry: bool = Field(
        default=False,
        description=(
            "Opt-in shared Prometheus registry so multiple exporters can expose a single"
            " scrape target in production while tests can keep isolated defaults"
        ),
    )
    metrics_shared_registry_endpoint_enabled: bool = Field(
        default=False,
        description=(
            "Expose a shared /metrics endpoint fed by the shared registry for hosted deployments"
        ),
    )
    metrics_worker_endpoint_enabled: bool = Field(
        default=False,
        description=(
            "Enable a standalone worker metrics scrape endpoint so workers can be scraped"
            " without co-locating with the API process"
        ),
    )
    metrics_worker_port: int = Field(default=9001, ge=1, le=65535)
    metrics_worker_bind_address: str = Field(default="127.0.0.1")
    metrics_worker_use_shared_registry: bool = Field(
        default=False,
        description=(
            "Opt-in to registering worker metrics against the shared registry to allow"
            " consolidated scraping across processes"
        ),
    )
    metrics_guard_check_interval_seconds: int = Field(
        default=60,
        ge=1,
        description="Cadence for verifying metrics exporters are still running",
    )
    metrics_guard_restart_backoff_seconds: int = Field(
        default=180,
        ge=1,
        description="Minimum time between exporter restart attempts",
    )
    health_cache_ttl_seconds: int = Field(default=3, ge=0)

    # Legacy auth/db knobs
    require_api_key: bool = True
    api_key: str | None = None
    auth_db_path: str = Field(default="data/auth.sqlite3")
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    session_cookie_name: str = "synqc_session"
    csrf_cookie_name: str = "synqc_csrf"
    session_ttl_seconds: int = Field(default=60 * 60 * 24 * 7, ge=300)
    password_pbkdf2_iterations: int = Field(default=260_000, ge=100_000)
    refresh_cookie_name: str = "synqc_refresh"

    # Provider simulation toggle
    allow_provider_simulation: bool = Field(default=False)

    # Agent chat (OpenAI proxy)
    openai_api_key: str | None = Field(default=None, description="API key for OpenAI-powered agent chat")
    openai_base_url: str = Field(default="https://api.openai.com/v1", description="Base URL for OpenAI-compatible API")
    openai_model: str = Field(default="gpt-4o-mini", description="Model to use for agent chat completions")
    agent_chat_limit_requests: int = Field(default=10, ge=1, description="Max agent chat calls per window")
    agent_chat_limit_window_seconds: int = Field(default=60, ge=1, description="Window (seconds) for agent chat rate limiting")

    def model_post_init(self, __context):
        if self.allowed_origins_raw is None:
            env_val = os.getenv("SYNQC_ALLOWED_ORIGINS") or os.getenv("SYNQC_CORS_ALLOW_ORIGINS")
            if env_val:
                object.__setattr__(self, "allowed_origins_raw", env_val)
        if self.database_url is None:
            env_db = os.getenv("DATABASE_URL")
            if env_db:
                object.__setattr__(self, "database_url", env_db)

    @field_validator("master_key")
    @classmethod
    def _validate_master_key(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            base64.urlsafe_b64decode(value)
        except Exception as exc:  # pragma: no cover - defensive validation
            raise ValueError("SYNQC_MASTER_KEY must be base64 urlsafe encoded") from exc
        return value

    def _require(self, condition: bool, message: str) -> None:
        if not condition:
            raise ValueError(message)

    def ensure_prod_safety(self) -> None:
        if self.env != "prod":
            return
        self._require(bool(self.allowed_origins), "SYNQC_ALLOWED_ORIGINS must be set in prod")
        self._require(self.auth_required, "SYNQC_AUTH_REQUIRED must be true in prod")
        self._require(bool(self.jwks_url), "SYNQC_JWKS_URL must be set in prod")
        self._require(bool(self.auth_issuer), "SYNQC_AUTH_ISSUER must be set in prod")
        self._require(bool(self.auth_audience), "SYNQC_AUTH_AUDIENCE must be set in prod")
        self._require(bool(self.database_url), "DATABASE_URL must be set in prod")

    @property
    def cors_allow_origins(self) -> list[str]:
        return self.allowed_origins

    @property
    def allowed_origins(self) -> list[str]:
        raw = self.allowed_origins_raw or ""
        return [origin.strip() for origin in raw.split(",") if origin.strip()]


settings = SynQcSettings()
settings.ensure_prod_safety()
