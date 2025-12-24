from __future__ import annotations

import time
import uuid
from typing import Tuple

import random

from .budget import BudgetTracker
from .config import settings
from .control_profiles import ControlProfile, ControlProfileStore
from .hardware_backends import get_backend
from .models import (
    ExperimentPreset,
    ExperimentStatus,
    KpiBundle,
    KpiDetail,
    RunExperimentRequest,
    RunExperimentResponse,
    WorkflowStep,
)
from .qubit_usage import SessionQubitTracker
from .kpi_estimators import fidelity_dist_ci95_from_counts
from .physics_contract import infer_contract, kpi_definition_id_for_name
from .storage import ExperimentStore


class BudgetExceeded(Exception):
    """Raised when a request exceeds the configured session budget."""

    def __init__(self, remaining: int):
        self.remaining = remaining
        super().__init__(f"Session shot budget exhausted; remaining={remaining}")


class SynQcEngine:
    """Core engine for SynQc Temporal Dynamics Series backend.

    Responsibilities:
      - Apply configuration and guardrails (shot limits, basic policies).
      - Translate high-level presets into backend calls.
      - Aggregate KPIs and store experiment records.
    """

    def __init__(
        self,
        store: ExperimentStore,
        budget_tracker: BudgetTracker,
        control_store: ControlProfileStore,
        usage_tracker: SessionQubitTracker | None = None,
    ) -> None:
        self._store = store
        self._budget_tracker = budget_tracker
        self._control_store = control_store
        self._usage_tracker = usage_tracker

    def _apply_shot_guardrails(self, req: RunExperimentRequest, session_id: str) -> Tuple[int, bool]:
        """Determine effective shot budget and whether to flag a warning.

        Returns:
            (effective_shot_budget, warn_for_target)
        """
        shot_budget = req.shot_budget or settings.default_shot_budget
        if shot_budget <= 0:
            raise ValueError("shot_budget must be positive")
        if shot_budget > settings.max_shots_per_experiment:
            shot_budget = settings.max_shots_per_experiment

        warn_for_target = False
        if req.hardware_target != "sim_local" and shot_budget > settings.default_shot_budget:
            warn_for_target = True

        accepted, usage = self._budget_tracker.reserve(
            session_id=session_id,
            requested=shot_budget,
            max_shots_per_session=settings.max_shots_per_session,
        )
        if not accepted:
            remaining = settings.max_shots_per_session - usage
            raise BudgetExceeded(remaining=max(remaining, 0))

        return shot_budget, warn_for_target

    def _apply_control_profile(self, kpis: KpiBundle, controls: ControlProfile) -> KpiBundle:
        """Map engineering controls to KPI adjustments.

        These adjustments are intentionally subtle so the simulated numbers stay
        within realistic bounds while still reflecting operator intent.
        """

        adjusted = kpis.model_copy(deep=True)

        # Drive bias can nudge fidelity upward (toward ceiling) but may add backaction
        if adjusted.fidelity is not None:
            fidelity_gain = 0.08 * (controls.drive_bias - 1.0)
            adjusted.fidelity = max(0.0, min(1.0, adjusted.fidelity + fidelity_gain))

        if adjusted.backaction is not None:
            backaction_delta = 0.05 * ((controls.probe_window_ns / 500.0) - 1.0)
            if not controls.thermal_guard_enabled:
                backaction_delta += 0.04
            adjusted.backaction = max(0.0, min(1.0, adjusted.backaction + backaction_delta))

        if adjusted.latency_us is not None:
            latency_scale = 1.0 - min(controls.feedback_gain * 0.04, 0.25)
            adjusted.latency_us = max(1.0, adjusted.latency_us * latency_scale)

        # Clamp status to WARN if safety clamp is disabled and backaction is high
        if adjusted.backaction is not None and adjusted.backaction > 0.32:
            if not controls.thermal_guard_enabled or controls.safety_clamp_ns == 0:
                adjusted.status = ExperimentStatus.WARN

        return adjusted

    def _estimate_qubits_used(
        self,
        req: RunExperimentRequest,
        kpis: KpiBundle,
        effective_shot_budget: int,
    ) -> int:
        """Estimate how many qubits were entangled for a run.

        The estimation is deterministic per request to keep UI/telemetry stable while
        still reacting to preset, hardware, and control intent.
        """

        bounds = {
            "sim_local": (6, 18),
            "aws_braket": (20, 48),
            "ibm_quantum": (16, 44),
            "azure_quantum": (14, 38),
            "ionq_labs": (12, 32),
            "rigetti_qcs": (18, 40),
        }
        min_q, max_q = bounds.get(req.hardware_target, (10, 36))

        # Scale by preset complexity
        preset_scale = {
            ExperimentPreset.LATENCY: 0.45,
            ExperimentPreset.HEALTH: 0.65,
            ExperimentPreset.DPD_DEMO: 0.5,
            ExperimentPreset.BACKEND_COMPARE: 0.9,
        }.get(req.preset, 0.65)

        # Entanglement/backaction can bump the footprint
        backaction = kpis.backaction if kpis.backaction is not None else 0.2
        backaction_scale = min(1.0, max(0.0, backaction / 0.6))

        # Shot budget hints at workload breadth
        shot_scale = min(1.0, (effective_shot_budget / max(1, settings.max_shots_per_experiment)))

        rng = random.Random()
        rng.seed(f"{req.hardware_target}:{req.preset}:{effective_shot_budget}:{backaction}")

        base_span = max_q - min_q
        scaled = min_q + int(base_span * (0.35 + preset_scale * 0.35 + backaction_scale * 0.2 + shot_scale * 0.1))
        jitter = rng.randint(-2, 3)

        return max(1, min(max_q, scaled + jitter))

    def _build_workflow_trace(
        self,
        req: RunExperimentRequest,
        kpis: KpiBundle,
        controls: ControlProfile,
    ) -> list[WorkflowStep]:
        """Generate a themed orchestration trace for UI visualization.

        The UI uses these nodes to light the neural-style network and narrate
        the orchestration story. Values are deterministic per request so the
        front-end can map them directly to animation timing.
        """

        hardware = req.hardware_target
        preset = req.preset.value.replace("_", " ")

        base = [
            WorkflowStep(
                id="ingest",
                label="Ingest",
                description=f"Budget + calibrations locked for {hardware} ({preset}).",
                percent_complete=12,
                dwell_ms=420,
            ),
            WorkflowStep(
                id="shape",
                label="Drive shaping",
                description=(
                    "Synthesizing composite drive envelope with bias="
                    f"{controls.drive_bias:.2f} and clamp={controls.safety_clamp_ns} ns."
                ),
                percent_complete=28,
                dwell_ms=520,
            ),
            WorkflowStep(
                id="probe",
                label="Probe readout",
                description=(
                    "Mid-circuit probe window set to "
                    f"{int(controls.probe_window_ns)} ns with feedback gain {controls.feedback_gain:.2f}."
                ),
                percent_complete=44,
                dwell_ms=560,
            ),
            WorkflowStep(
                id="adapt",
                label="Adaptive drive",
                description="Routing probe residuals into drive/feedback synthesis for stabilization.",
                percent_complete=63,
                dwell_ms=520,
            ),
            WorkflowStep(
                id="infer",
                label="Inference",
                description="Neural estimator aggregates traces to derive fidelity/latency envelope.",
                percent_complete=82,
                dwell_ms=600,
            ),
        ]

        final_note = ""
        if kpis.fidelity is not None:
            final_note += f"Fidelity ≈ {kpis.fidelity:.3f}. "
        if kpis.latency_us is not None:
            final_note += f"Latency ≈ {kpis.latency_us:.1f} µs. "
        if kpis.backaction is not None:
            final_note += f"Backaction {kpis.backaction:.2f}. "

        base.append(
            WorkflowStep(
                id="commit",
                label="Commit",
                description=(
                    final_note.strip()
                    or "Results recorded; waiting for downstream consumers."
                ),
                percent_complete=100,
                dwell_ms=700,
            )
        )

        return base

    def _build_kpi_details(self, kpis: KpiBundle) -> list[KpiDetail]:
        """Attach definition ids and uncertainty to KPIs when data is available."""

        kpi_details: list[KpiDetail] = []
        kpi_map = {
            "fidelity": kpis.fidelity,
            "latency_us": kpis.latency_us,
            "backaction": kpis.backaction,
        }

        for name, value in kpi_map.items():
            if value is None:
                continue
            definition_id = kpi_definition_id_for_name(name)
            detail_kwargs: dict[str, object] = {
                "name": name,
                "value": value,
                "definition_id": definition_id,
            }

            if (
                definition_id == "fidelity_dist_v1"
                and kpis.raw_counts
                and kpis.expected_distribution
            ):
                try:
                    lo, hi = fidelity_dist_ci95_from_counts(
                        kpis.raw_counts, kpis.expected_distribution, n_boot=200
                    )
                    detail_kwargs["ci95"] = [lo, hi]
                except ValueError:
                    # If the inputs are degenerate, skip CI instead of failing the run.
                    pass

            kpi_details.append(KpiDetail(**detail_kwargs))

        return kpi_details

    def run_experiment(self, req: RunExperimentRequest, session_id: str) -> RunExperimentResponse:
        """Run a high-level SynQc experiment according to the request."""
        effective_shot_budget, warn_for_target = self._apply_shot_guardrails(req, session_id)

        backend = get_backend(req.hardware_target)
        start = time.time()
        active_controls = req.control_overrides or self._control_store.get()
        kpis = backend.run_experiment(req.preset, effective_shot_budget)
        kpis = self._apply_control_profile(kpis, active_controls)
        end = time.time()

        qubits_used = self._estimate_qubits_used(req, kpis, effective_shot_budget)

        # Fill missing KPI fields and tweak status if guardrails were hit
        if kpis.shot_budget == 0:
            kpis.shot_budget = effective_shot_budget

        if kpis.raw_counts:
            measured = sum(int(v) for v in kpis.raw_counts.values())
            if measured > 0 and (
                kpis.shots_used in (None, 0) or measured > kpis.shots_used
            ):
                kpis.shots_used = measured

        # If we had to clamp or warn on target, bump status to WARN (if not already FAIL)
        if warn_for_target and kpis.status is not ExperimentStatus.FAIL:
            kpis.status = ExperimentStatus.WARN

        # If latency is missing, approximate with wall-clock delta
        if kpis.latency_us is None:
            kpis.latency_us = (end - start) * 1e6

        physics_contract = infer_contract(
            target=req.hardware_target,
            shots_requested=effective_shot_budget,
            shots_executed=kpis.shots_used,
            n_qubits=qubits_used,
            backend_id=None,
        )

        kpi_details = self._build_kpi_details(kpis)

        run_id = str(uuid.uuid4())
        run = RunExperimentResponse(
            id=run_id,
            preset=req.preset,
            hardware_target=req.hardware_target,
            kpis=kpis,
            created_at=end,
            qubits_used=qubits_used,
            notes=req.notes,
            control_profile=active_controls,
            physics_contract=physics_contract,
            kpi_details=kpi_details or None,
            workflow_trace=self._build_workflow_trace(req, kpis, active_controls),
        )

        if self._usage_tracker:
            try:
                self._usage_tracker.record(session_id=session_id, qubits_used=qubits_used)
            except Exception:
                # Usage telemetry should not block run completion.
                pass

        self._store.add(run)
        return run
