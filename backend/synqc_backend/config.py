from __future__ import annotations

from pydantic import BaseModel
from typing import Literal


class SynQcSettings(BaseModel):
    """Configuration settings for the SynQc backend.

    In a more advanced deployment this could be subclassed from pydantic.BaseSettings
    to read environment variables. For now we keep it simple and explicit.
    """

    env: Literal["dev", "prod"] = "dev"

    # Shot-related guardrails
    max_shots_per_experiment: int = 200_000
    max_shots_per_session: int = 1_000_000

    # Default shot budget if caller doesn't specify
    default_shot_budget: int = 2_048

    # Whether we allow non-simulator targets in this deployment
    allow_remote_hardware: bool = True


settings = SynQcSettings()
