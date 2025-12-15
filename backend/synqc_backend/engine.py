from __future__ import annotations

import time
import uuid
from typing import Tuple

from .config import settings
from .hardware_backends import get_backend
from .models import (
    ExperimentPreset,
    ExperimentStatus,
    KpiBundle,
    RunExperimentRequest,
    RunExperimentResponse,
)
from .storage import ExperimentStore


class SynQcEngine:
    """Core engine for SynQc Temporal Dynamics Series backend.

    Responsibilities:
      - Apply configuration and guardrails (shot limits, basic policies).
      - Translate high-level presets into backend calls.
      - Aggregate KPIs and store experiment records.
    """

    def __init__(self, store: ExperimentStore) -> None:
        self._store = store
        self._session_shots_used = 0

    def _apply_shot_guardrails(self, req: RunExperimentRequest) -> Tuple[int, bool]:
        """Determine effective shot budget and whether to flag a warning.

        Returns:
            (effective_shot_budget, warn_for_target)
        """
        shot_budget = req.shot_budget or settings.default_shot_budget
        if shot_budget > settings.max_shots_per_experiment:
            shot_budget = settings.max_shots_per_experiment

        warn_for_target = False
        if req.hardware_target != "sim_local" and shot_budget > settings.default_shot_budget:
            warn_for_target = True

        if self._session_shots_used + shot_budget > settings.max_shots_per_session:
            # In a more advanced implementation, we might reject the request.
            # Here we clamp down to the remaining budget.
            remaining = max(settings.max_shots_per_session - self._session_shots_used, 0)
            shot_budget = max(remaining, 0)

        return shot_budget, warn_for_target

    def run_experiment(self, req: RunExperimentRequest) -> RunExperimentResponse:
        """Run a high-level SynQc experiment according to the request."""
        effective_shot_budget, warn_for_target = self._apply_shot_guardrails(req)

        backend = get_backend(req.hardware_target)
        start = time.time()
        kpis = backend.run_experiment(req.preset, effective_shot_budget)
        end = time.time()

        # Update session shot usage
        self._session_shots_used += kpis.shots_used

        # Fill missing KPI fields and tweak status if guardrails were hit
        if kpis.shot_budget == 0:
            kpis.shot_budget = effective_shot_budget

        # If we had to clamp or warn on target, bump status to WARN (if not already FAIL)
        if warn_for_target and kpis.status is not ExperimentStatus.FAIL:
            kpis.status = ExperimentStatus.WARN

        # If latency is missing, approximate with wall-clock delta
        if kpis.latency_us is None:
            kpis.latency_us = (end - start) * 1e6

        run_id = str(uuid.uuid4())
        run = RunExperimentResponse(
            id=run_id,
            preset=req.preset,
            hardware_target=req.hardware_target,
            kpis=kpis,
            created_at=end,
            notes=req.notes,
        )
        self._store.add(run)
        return run
