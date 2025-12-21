from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SynQcSettings(BaseSettings):
    """Environment-backed configuration for the SynQc backend."""

    model_config = SettingsConfigDict(
        env_prefix="SYNQC_",
        env_file=".env",
        extra="ignore",
    )

    env: Literal["dev", "prod"] = "dev"

    # Shot-related guardrails
    max_shots_per_experiment: int = Field(default=200_000, ge=1)
    max_shots_per_session: int = Field(default=1_000_000, ge=1)

    # Default shot budget if caller doesn't specify
    default_shot_budget: int = Field(default=2_048, ge=1)

    # Whether we allow non-simulator targets in this deployment
    allow_remote_hardware: bool = False

    # API hardening
    require_api_key: bool = True
    api_key: str | None = None

    # Auth
    auth_required: bool = Field(
        default=False,
        description="When true, require auth even if SYNQC_API_KEY is unset (recommended for production).",
    )
    auth_db_path: str = Field(default="data/auth.sqlite3", description="SQLite path for auth/users/tokens")
    cookie_secure: bool = Field(default=False, description="Set cookies Secure=True (requires HTTPS)")
    cookie_samesite: str = Field(default="lax", description="Cookie SameSite: lax|strict|none")

    session_cookie_name: str = Field(default="synqc_session")
    csrf_cookie_name: str = Field(default="synqc_csrf")
    session_ttl_seconds: int = Field(default=60 * 60 * 24 * 7, ge=300)

    password_pbkdf2_iterations: int = Field(default=260_000, ge=100_000)

    refresh_cookie_name: str = Field(default="synqc_refresh")

    # CORS allowlist (comma-separated env var or list in code)
    cors_allow_origins: list[str] = Field(
        default_factory=lambda: ["http://127.0.0.1:8080", "http://localhost:8080"]
    )

    # Redis / job queue
    redis_url: str | None = Field(
        default=None, description="Redis connection URL for budgets and queues"
    )
    session_budget_ttl_seconds: int = Field(default=3600, ge=60)
    budget_fail_open_on_redis_error: bool = Field(
        default=False,
        description=(
            "If Redis budget backend fails, fallback to in-memory (dev). "
            "In prod, keep false to fail closed."
        ),
    )
    worker_pool_size: int = Field(default=4, ge=1)
    job_graceful_shutdown_seconds: int = Field(default=5, ge=0)
    job_timeout_seconds: int = Field(
        default=90,
        ge=0,
        description="Soft timeout for jobs; 0 disables",
    )
    job_queue_max_pending: int = Field(
        default=1000,
        ge=1,
        description="Backpressure limit for queued+running jobs",
    )
    job_queue_db_path: str = Field(
        default="data/jobs.sqlite3",
        description="SQLite path for persistent job spool",
    )

    # Metrics / observability
    enable_metrics: bool = Field(
        default=True, description="Expose Prometheus metrics for queue and budget health"
    )
    metrics_port: int = Field(default=9000, ge=1, le=65535)
    metrics_bind_address: str = Field(
        default="127.0.0.1",
        description="Interface to bind the Prometheus exporter (use 0.0.0.0 only when intentionally exposed)",
    )
    metrics_collection_interval_seconds: int = Field(default=15, ge=5)

    # Provider backends
    allow_provider_simulation: bool = Field(
        default=False,
        description="Allow provider backends to run in simulation mode. When false, only the local simulator is permitted.",
    )

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _parse_origins(cls, value: list[str] | str) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


settings = SynQcSettings()
