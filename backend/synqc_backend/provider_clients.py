from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Dict, Protocol

from .models import ExperimentPreset
from .stats import Counts


logger = logging.getLogger(__name__)


class ProviderClientError(RuntimeError):
    """Raised when provider client payloads cannot be loaded or validated."""


@dataclass
class ProviderLiveResult:
    """Structured response extracted from a provider SDK call."""

    raw_counts: Counts
    expected_distribution: Dict[str, float] | None = None
    fidelity: float | None = None
    latency_us: float | None = None
    backaction: float | None = None
    shots_used: int | None = None


class BaseProviderClient(Protocol):
    """Adapter that translates provider SDK results into SynQc-ready data."""

    def run(self, preset: ExperimentPreset, shot_budget: int) -> ProviderLiveResult:  # pragma: no cover - interface
        ...


class FilePayloadProviderClient:
    """Lightweight adapter that reads provider payloads from disk or env strings."""

    def __init__(self, payload: str) -> None:
        self._payload = payload

    def _load(self) -> dict:
        # If the payload points to a file, load it; otherwise treat as inline JSON
        try:
            if os.path.exists(self._payload):
                with open(self._payload, "r", encoding="utf-8") as f:
                    return json.load(f)
            return json.loads(self._payload)
        except (OSError, json.JSONDecodeError) as exc:
            raise ProviderClientError(f"Failed to load provider payload from {self._payload!r}") from exc

    def run(self, preset: ExperimentPreset, shot_budget: int) -> ProviderLiveResult:
        data = self._load()
        raw_counts = data.get("raw_counts") or {}
        expected_distribution = data.get("expected_distribution")
        fidelity = data.get("fidelity")
        latency_us = data.get("latency_us")
        backaction = data.get("backaction")
        shots_used = data.get("shots_used")

        # Normalize keys/values to expected types
        try:
            normalized_counts: Counts = {str(k): int(v) for k, v in raw_counts.items()}
        except Exception as exc:
            raise ProviderClientError("Invalid raw_counts in provider payload") from exc

        return ProviderLiveResult(
            raw_counts=normalized_counts,
            expected_distribution=expected_distribution,
            fidelity=fidelity,
            latency_us=latency_us,
            backaction=backaction,
            shots_used=shots_used,
        )


def load_provider_clients() -> dict[str, BaseProviderClient]:
    """Load provider adapters from environment configuration.

    Each provider backend id can be paired with an environment variable of the form
    ``SYNQC_PROVIDER_PAYLOAD_<BACKEND_ID>`` that points to either a JSON file path or
    an inline JSON string containing counts/expectations produced by the provider SDK.
    """

    clients: dict[str, BaseProviderClient] = {}
    prefix = "SYNQC_PROVIDER_PAYLOAD_"
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        backend_id = key[len(prefix) :].lower()
        if not value:
            continue
        try:
            clients[backend_id] = FilePayloadProviderClient(value)
        except Exception:
            # Keep failing entries isolated to avoid disrupting unrelated backends,
            # but surface the failure for observability.
            logger.exception(
                "Failed to initialize provider client for backend '%s' from env var '%s'",
                backend_id,
                key,
            )
            continue
    return clients
