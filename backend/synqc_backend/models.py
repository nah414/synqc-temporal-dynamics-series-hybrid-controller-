from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from .control_profiles import ControlProfile
from .physics_contract import PhysicsContract


class ExperimentPreset(str, Enum):
    """High-level experiment presets supported by the SynQc engine."""

    HEALTH = "health"
    LATENCY = "latency"
    BACKEND_COMPARE = "backend_compare"
    DPD_DEMO = "dpd_demo"


class ExperimentStatus(str, Enum):
    """Coarse-grained status for a completed experiment bundle."""

    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


class KpiBundle(BaseModel):
    """Key performance indicators for a SynQc experiment run."""

    fidelity: Optional[float] = Field(
        default=None,
        description="Estimated state/process fidelity (0–1)."
    )
    latency_us: Optional[float] = Field(
        default=None,
        description="End-to-end latency in microseconds."
    )
    backaction: Optional[float] = Field(
        default=None,
        description="Scalar measure of probe-induced disturbance (0–1)."
    )
    raw_counts: Optional[Dict[str, int]] = Field(
        default=None,
        description="Shot-outcome counts backing sampling-based KPIs.",
    )
    expected_distribution: Optional[Dict[str, float]] = Field(
        default=None,
        description=(
            "Reference outcome probabilities used to evaluate sampling-based KPIs"
            " (e.g., fidelity to an expected distribution)."
        ),
    )
    shots_used: int = Field(
        default=0,
        description="Number of shots actually used by this run."
    )
    shot_budget: int = Field(
        default=0,
        description="Shot budget configured for this run."
    )
    status: ExperimentStatus = Field(
        default=ExperimentStatus.OK,
        description="Overall health/status classification for this run."
    )


class WorkflowStep(BaseModel):
    """Lightweight progress descriptor for the orchestration graph."""

    id: str = Field(description="Stable identifier for the workflow node")
    label: str = Field(description="User-visible label for the node")
    description: str = Field(description="Plain-language context for this stage")
    percent_complete: float = Field(
        default=0.0,
        description="Cumulative completion percentage when this node is lit.",
    )
    dwell_ms: int = Field(
        default=450,
        description="Suggested dwell time for UI animation of this node.",
    )


class HardwareTarget(BaseModel):
    """Description of a hardware backend target."""

    id: str
    name: str
    kind: str  # e.g. "sim", "superconducting", "trapped_ion", "fpga_lab"
    description: str


class RunExperimentRequest(BaseModel):
    """API-facing request model for running a SynQc experiment preset."""

    preset: ExperimentPreset
    hardware_target: str = Field(
        description="Backend identifier, e.g. 'sim_local', 'aws_braket', 'ibm_quantum'."
    )
    shot_budget: Optional[int] = Field(
        default=None,
        description="Maximum number of shots to use; if omitted, defaults are applied."
    )
    notes: Optional[str] = Field(
        default=None,
        description="Optional free-form notes from the client."
    )
    control_overrides: Optional[ControlProfile] = Field(
        default=None,
        description="Optional manual control profile to apply for this run.",
    )


class KpiDetail(BaseModel):
    """Rich KPI entry anchored to a formal definition id."""

    name: str
    value: Optional[Any] = None
    definition_id: str
    ci95: Optional[List[float]] = Field(
        default=None,
        description="Optional [lo, hi] confidence interval when sampling-based KPIs are estimated.",
    )

class RunExperimentResponse(BaseModel):
    """Response returned after an experiment run has been accepted and executed."""

    id: str
    preset: ExperimentPreset
    hardware_target: str
    kpis: KpiBundle
    created_at: float
    qubits_used: int = Field(
        default=0,
        description="Estimated number of qubits entangled/active during the run.",
    )
    notes: Optional[str] = None
    control_profile: Optional[ControlProfile] = None
    physics_contract: Optional[PhysicsContract] = Field(
        default=None,
        description="Declared physics/measurement contract under which KPIs were computed.",
    )
    kpi_details: Optional[List[KpiDetail]] = Field(
        default=None,
        description="Per-KPI definitions and optional uncertainty bounds.",
    )
    error_detail: Optional[dict] = None
    workflow_trace: List[WorkflowStep] = Field(
        default_factory=list,
        description="Ordered set of orchestration nodes that activated during the run.",
    )


class RunJobStatus(str, Enum):
    """Lifecycle status for a submitted run."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RunSubmissionResponse(BaseModel):
    """Acknowledgement returned immediately after enqueuing a run."""

    id: str
    status: RunJobStatus
    created_at: float
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error: Optional[str] = None
    error_detail: Optional[dict] = None


class RunStatusResponse(RunSubmissionResponse):
    """Extended status that optionally returns the completed run payload."""

    result: Optional[RunExperimentResponse] = None


class ExperimentSummary(BaseModel):
    """Lightweight summary for listing experiment runs."""

    id: str
    preset: ExperimentPreset
    hardware_target: str
    kpis: KpiBundle
    created_at: float
    qubits_used: int = Field(
        default=0,
        description="Estimated number of qubits entangled/active during the run.",
    )
    control_profile: Optional[ControlProfile] = None
    physics_contract: Optional[PhysicsContract] = None
    kpi_details: Optional[List[KpiDetail]] = None
    error_detail: Optional[dict] = None


class HardwareTargetsResponse(BaseModel):
    """List wrapper for hardware targets."""

    targets: List[HardwareTarget]


class QubitTelemetry(BaseModel):
    """Session-scoped qubit usage for UI telemetry."""

    session_total_qubits: int = Field(
        default=0,
        description="Cumulative qubits engaged for the current session (resets after TTL).",
    )
    last_run_qubits: Optional[int] = Field(
        default=None,
        description="Most recent run's entangled qubit count, if available.",
    )
    last_updated: Optional[float] = Field(
        default=None,
        description="Timestamp of the last update for this session.",
    )
    demo_min_qubits: int = Field(default=1, description="Lower bound for demo loop visualization.")
    demo_max_qubits: int = Field(default=25, description="Upper bound for demo loop visualization.")
