from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Optional

from pydantic import BaseModel, Field


class ControlProfile(BaseModel):
    """Manual engineering controls applied to SynQc runs.

    This profile is intentionally compact but expressive enough for engineers
    to influence the simulated KPIs and document runtime guardrails.
    """

    drive_bias: float = Field(
        default=1.0,
        ge=0.5,
        le=1.5,
        description="Global drive amplitude multiplier applied to pulses.",
    )
    probe_window_ns: int = Field(
        default=120,
        ge=10,
        le=10_000,
        description="Probe window length in nanoseconds for measurement phases.",
    )
    feedback_gain: float = Field(
        default=0.35,
        ge=0.0,
        le=3.0,
        description="Feedback gain used during the third DPD leg.",
    )
    safety_clamp_ns: int = Field(
        default=600,
        ge=0,
        le=20_000,
        description="Safety clamp that limits pulse trains above this nanosecond duration.",
    )
    thermal_guard_enabled: bool = Field(
        default=True,
        description="Whether thermal guards remain active for production hardware.",
    )
    tracer_persistence_ms: int = Field(
        default=420,
        ge=50,
        le=5_000,
        description="Visualization hint for how long particle tracers persist on the frontend.",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Optional operator notes for the current control profile.",
    )


class ControlProfileUpdate(BaseModel):
    """Partial update for control profiles."""

    drive_bias: Optional[float] = None
    probe_window_ns: Optional[int] = None
    feedback_gain: Optional[float] = None
    safety_clamp_ns: Optional[int] = None
    thermal_guard_enabled: Optional[bool] = None
    tracer_persistence_ms: Optional[int] = None
    notes: Optional[str] = None


class ControlProfileStore:
    """Thread-safe in-memory store with optional JSON persistence."""

    def __init__(self, persist_path: Optional[Path] = None) -> None:
        self._persist_path = persist_path
        self._lock = Lock()
        self._profile = ControlProfile()

        if self._persist_path and self._persist_path.exists():
            try:
                data = json.loads(self._persist_path.read_text())
                self._profile = ControlProfile.model_validate(data)
            except Exception:
                # Corrupt or missing data falls back to defaults.
                self._profile = ControlProfile()

    def get(self) -> ControlProfile:
        with self._lock:
            return self._profile.model_copy(deep=True)

    def update(self, patch: ControlProfileUpdate) -> ControlProfile:
        with self._lock:
            payload = self._profile.model_dump()
            for field, value in patch.model_dump(exclude_none=True).items():
                payload[field] = value
            self._profile = ControlProfile(**payload)
            self._persist()
            return self._profile.model_copy(deep=True)

    def _persist(self) -> None:
        if not self._persist_path:
            return
        try:
            self._persist_path.write_text(
                json.dumps(self._profile.model_dump(mode="json"), indent=2)
            )
        except Exception:
            # Persistence failures should not crash the server.
            pass
