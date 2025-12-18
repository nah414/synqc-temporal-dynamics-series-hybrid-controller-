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

    # CORS allowlist (comma-separated env var or list in code)
    cors_allow_origins: list[str] = Field(
        default_factory=lambda: ["http://127.0.0.1:8080", "http://localhost:8080"]
    )

    # Redis / job queue
    redis_url: str | None = Field(
        default=None, description="Redis connection URL for budgets and queues"
    )
    session_budget_ttl_seconds: int = Field(default=3600, ge=60)
    worker_pool_size: int = Field(default=4, ge=1)
    job_graceful_shutdown_seconds: int = Field(default=5, ge=0)

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
