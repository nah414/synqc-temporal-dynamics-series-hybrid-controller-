from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from .control_profiles import ControlProfile
from .physics_contract import PhysicsContract


class ExperimentPreset(str, Enum):
    """High-level experiment presets supported by the SynQc engine."""

    HELLO_QUANTUM_SIM = "hello_quantum_sim"
    HEALTH = "health"
    LATENCY = "latency"
    BACKEND_COMPARE = "backend_compare"
    DPD_DEMO = "dpd_demo"
    GROVER_DEMO = "grover_demo"
    MULTICALL_DUAL_CLOCKING = "multicall_dual_clocking"


class ExperimentStatus(str, Enum):
    """Coarse-grained status for a completed experiment bundle."""

    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


class ErrorCode(str, Enum):
    """Structured error code taxonomy for operator visibility."""

    AUTH_REQUIRED = "AUTH_REQUIRED"
    REMOTE_DISABLED = "REMOTE_DISABLED"
    PROVIDER_SIM_DISABLED = "PROVIDER_SIM_DISABLED"
    PROVIDER_CREDENTIALS = "PROVIDER_CREDENTIALS"
    PROVIDER_CAPACITY = "PROVIDER_CAPACITY"
    PROVIDER_QUEUE_BACKPRESSURE = "PROVIDER_QUEUE_BACKPRESSURE"
    INVALID_TARGET = "INVALID_TARGET"
    INVALID_REQUEST = "INVALID_REQUEST"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    BUDGET_GUARDRAIL = "BUDGET_GUARDRAIL"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    PROVIDER_ERROR = "PROVIDER_ERROR"


class ErrorReport(BaseModel):
    """Uniform error payload surfaced to the UI, logs, and metrics."""

    error_code: ErrorCode
    error_message: str
    error_detail: Optional[dict] = None
    action_hint: Optional[str] = Field(
        default=None,
        description="Operator hint for recovering from the failure.",
    )

    def as_legacy_detail(self) -> dict:
        """Preserve compatibility with existing clients expecting error_detail.code."""

        detail = dict(self.error_detail or {})
        detail.setdefault("code", self.error_code)
        detail.setdefault("message", self.error_message)
        if self.action_hint:
            detail.setdefault("action_hint", self.action_hint)
        return detail


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
    capabilities: Optional["ProviderCapabilities"] = Field(
        default=None,
        description="Hardware/provider capability descriptor (queueing, limits, gates).",
    )


class ProviderCapabilities(BaseModel):
    """Provider capability descriptor for API discovery."""

    max_shots: Optional[int] = Field(
        default=None, description="Maximum allowed shots for a single execution."
    )
    queue_behavior: str = Field(
        default="inline",
        description="How work is scheduled: inline, queued, batched, priority, etc.",
    )
    supported_gates: List[str] = Field(
        default_factory=list,
        description="Gate set available for circuit-style submissions.",
    )
    notes: Optional[str] = Field(
        default=None, description="Optional free-form capability notes or caveats."
    )


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
    definition_ref: Optional[str] = Field(
        default=None,
        description="Stable definition reference id (e.g., F_dist_v1).",
    )
    kind: Optional[str] = Field(
        default="scalar",
        description="Classification for rendering (e.g., scalar, probability, latency).",
    )
    units: Optional[str] = Field(
        default=None,
        description="Unit string for the KPI value, if applicable.",
    )
    ci95: Optional[List[float]] = Field(
        default=None,
        description="Optional [lo, hi] confidence interval when sampling-based KPIs are estimated.",
    )
    ci_95: Optional[List[float]] = Field(
        default=None,
        description="Alias for ci95 for UI-facing payloads.",
        alias="ci_95",
    )
    stderr: Optional[float] = Field(
        default=None,
        description="Standard error for estimates when available.",
    )

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:  # type: ignore[override]
        data = super().model_dump(*args, **kwargs)
        if data.get("ci_95") is None and data.get("ci95") is not None:
            data["ci_95"] = data["ci95"]
        if data.get("definition_ref") is None:
            data["definition_ref"] = data.get("definition_id")
        return data


class ShotUsage(BaseModel):
    """Requested/executed shot counts for an experiment."""

    requested: Optional[int] = None
    executed: Optional[int] = None


class MeasurementDescriptor(BaseModel):
    """Measurement model descriptor for transparency in KPI interpretation."""

    model: str
    basis: Optional[str] = None
    povm: Optional[str] = None
    descriptor: Optional[str] = Field(
        default=None, description="Human-readable POVM descriptor or measurement notes."
    )


class NoiseDescriptor(BaseModel):
    """Noise model descriptor for experiment metadata."""

    model: str
    params: Dict[str, Any] = Field(default_factory=dict)
    descriptor: Optional[str] = Field(
        default=None, description="Optional human-readable description of the noise model."
    )

class RunExperimentResponse(BaseModel):
    """Response returned after an experiment run has been accepted and executed."""

    id: str
    preset: ExperimentPreset
    hardware_target: str
    kpis: KpiBundle
    created_at: float
    shots: Optional[ShotUsage] = Field(
        default=None,
        description="Requested/executed shot counts for this experiment.",
    )
    measurement: Optional[MeasurementDescriptor] = Field(
        default=None,
        description="Measurement model descriptor (projective basis or POVM).",
    )
    noise: Optional[NoiseDescriptor] = Field(
        default=None,
        description="Noise model descriptor for transparency in KPIs.",
    )
    assumptions: List[str] = Field(
        default_factory=list,
        description="Human-readable flags clarifying modeling assumptions.",
    )
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
    kpi_observations: Optional[List[KpiDetail]] = Field(
        default=None,
        description=(
            "UI-friendly KPI descriptors with names, kinds, units, references, and uncertainty bounds."
        ),
    )
    artifacts: Optional[dict] = Field(
        default=None,
        description="Raw provider artifacts captured alongside KPIs (counts, logs, traces).",
    )
    error_code: Optional[ErrorCode] = Field(
        default=None,
        description="Structured error code taxonomy for failed runs.",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="User-visible error message clarifying the failure.",
    )
    error_detail: Optional[dict] = Field(
        default=None, description="Provider- or guardrail-specific error metadata."
    )
    action_hint: Optional[str] = Field(
        default=None,
        description="Operator hint that explains how to remediate the failure.",
    )
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
    error_code: Optional[ErrorCode] = None
    error_message: Optional[str] = None
    error_detail: Optional[dict] = None
    action_hint: Optional[str] = None


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
    shots: Optional[ShotUsage] = None
    measurement: Optional[MeasurementDescriptor] = None
    noise: Optional[NoiseDescriptor] = None
    assumptions: List[str] = Field(default_factory=list)
    qubits_used: int = Field(
        default=0,
        description="Estimated number of qubits entangled/active during the run.",
    )
    control_profile: Optional[ControlProfile] = None
    physics_contract: Optional[PhysicsContract] = None
    kpi_details: Optional[List[KpiDetail]] = None
    kpi_observations: Optional[List[KpiDetail]] = None
    error_code: Optional[ErrorCode] = None
    error_message: Optional[str] = None
    error_detail: Optional[dict] = None
    action_hint: Optional[str] = None


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
