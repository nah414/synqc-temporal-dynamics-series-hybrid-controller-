"""Pydantic models + helpers for SynQc's Physics Contract.

This module is designed to be *added* to the existing codebase with minimal churn.

Integration strategy (recommended):
  - Keep your existing KPI surface so the UI doesn't break.
  - Add a new field on experiment records/responses:
        physics_contract: {...}
    and optionally:
        kpi_details: [...]
  - Provide a /physics/definitions endpoint (see physics_router.py)
    so UIs can render precise meanings and show SIM_ONLY / PROXY labels.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

try:
    # Pydantic v1/v2 compatible import
    from pydantic import BaseModel, Field
except Exception:  # pragma: no cover
    BaseModel = object  # type: ignore
    def Field(default=None, **kwargs):  # type: ignore
        return default

from .physics_definitions import all_kpi_definitions

PlantKind = Literal["quantum_device", "simulator", "unknown"]
StateModel = Literal["statevector", "density_matrix", "hardware_unknown", "unknown"]
MeasurementModel = Literal["projective", "povm", "unknown"]
NoiseModel = Literal["ideal", "channel", "lindblad", "hardware_empirical", "unknown"]

class SamplingSpec(BaseModel):
    model: Literal["multinomial"] = "multinomial"
    shots_requested: int = Field(..., ge=1)
    shots_executed: int = Field(..., ge=0)

class MeasurementSpec(BaseModel):
    model: MeasurementModel = "unknown"
    basis: Optional[str] = None  # e.g. "Z", "X", "Y", or "custom"
    povm: Optional[str] = None   # human-readable name if POVM
    notes: Optional[str] = None

class NoiseSpec(BaseModel):
    model: NoiseModel = "unknown"
    params: Dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None

class PlantSpec(BaseModel):
    kind: PlantKind = "unknown"
    target: str = "unknown"       # e.g. "local_sim", "aws_braket", "ibm_quantum"
    backend_id: Optional[str] = None  # provider job id if any

class StateSpec(BaseModel):
    model: StateModel = "unknown"
    n_qubits: Optional[int] = None
    hilbert_dim: Optional[int] = None
    notes: Optional[str] = None

class PhysicsContract(BaseModel):
    """The declared model under which KPIs are computed."""
    version: str = "physics_contract_v0_1"
    plant: PlantSpec
    state: StateSpec
    measurement: MeasurementSpec
    sampling: SamplingSpec
    noise: NoiseSpec
    assumptions: List[str] = Field(default_factory=list)
    kpi_definitions_version: str = "kpi_defs_v0_1"

def _model_dump(obj: Any) -> Any:
    """pydantic v1/v2 compat"""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    return obj

def contract_to_dict(contract: PhysicsContract) -> Dict[str, Any]:
    return _model_dump(contract)

def infer_contract(
    *,
    target: str,
    shots_requested: int,
    shots_executed: int,
    n_qubits: Optional[int] = None,
    backend_id: Optional[str] = None,
    measurement_basis: Optional[str] = "Z",
) -> PhysicsContract:
    """Heuristic contract builder.

    You can replace this with preset-specific and provider-specific logic.
    """
    t = (target or "unknown").lower()

    if "sim" in t or "local" in t:
        plant_kind: PlantKind = "simulator"
        state_model: StateModel = "statevector"
        noise_model: NoiseModel = "ideal"
        assumptions = ["SIMULATOR_IDEAL_UNLESS_DECLARED", "MEASUREMENT_PROJECTIVE_UNLESS_DECLARED"]
    elif "ibm" in t or "ionq" in t or "rigetti" in t or "braket" in t or "azure" in t:
        plant_kind = "quantum_device"
        state_model = "hardware_unknown"
        noise_model = "hardware_empirical"
        assumptions = ["HARDWARE_STATE_UNOBSERVED", "READOUT_ERROR_UNMODELED_UNLESS_DECLARED"]
    else:
        plant_kind = "unknown"
        state_model = "unknown"
        noise_model = "unknown"
        assumptions = ["UNSPECIFIED_TARGET"]

    meas_model: MeasurementModel = "projective" if measurement_basis else "unknown"

    contract = PhysicsContract(
        plant=PlantSpec(kind=plant_kind, target=target, backend_id=backend_id),
        state=StateSpec(model=state_model, n_qubits=n_qubits, hilbert_dim=(2**n_qubits) if n_qubits else None),
        measurement=MeasurementSpec(model=meas_model, basis=measurement_basis),
        sampling=SamplingSpec(shots_requested=int(shots_requested), shots_executed=int(shots_executed)),
        noise=NoiseSpec(model=noise_model),
        assumptions=assumptions,
    )
    return contract

def kpi_definition_id_for_name(kpi_name: str) -> str:
    """Map a KPI field name to a definition id.

    Keep this mapping conservative: if you can't confidently map it, return a generic id.
    """
    n = (kpi_name or "").lower()
    if "fidelity" in n:
        return "fidelity_dist_v1"
    if "latency" in n:
        return "latency_us_v1"
    if "backaction" in n:
        return "backaction_proxy_v1"
    # fallback: treat unknown KPIs as system-level with no formal claim yet
    return "unknown_kpi_v1"

def kpi_definitions_payload() -> Dict[str, Any]:
    return {
        "version": "kpi_defs_v0_1",
        "definitions": all_kpi_definitions(),
    }
