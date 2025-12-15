from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


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


class RunExperimentResponse(BaseModel):
    """Response returned after an experiment run has been accepted and executed."""

    id: str
    preset: ExperimentPreset
    hardware_target: str
    kpis: KpiBundle
    created_at: float
    notes: Optional[str] = None


class ExperimentSummary(BaseModel):
    """Lightweight summary for listing experiment runs."""

    id: str
    preset: ExperimentPreset
    hardware_target: str
    kpis: KpiBundle
    created_at: float


class HardwareTargetsResponse(BaseModel):
    """List wrapper for hardware targets."""

    targets: List[HardwareTarget]
