"""FastAPI router exposing physics contract definitions.

Add this router into your FastAPI app:

    from synqc_backend.physics_router import router as physics_router
    app.include_router(physics_router)

Endpoints:
  - GET /physics/definitions  -> KPI definition registry
  - GET /physics/contract     -> a template contract object + notes
"""

from __future__ import annotations

from fastapi import APIRouter

from .physics_contract import infer_contract, kpi_definitions_payload

router = APIRouter(prefix="/physics", tags=["physics"])

@router.get("/definitions")
def physics_definitions():
    return kpi_definitions_payload()

@router.get("/contract")
def physics_contract_template():
    # A reasonable default template (local sim, 1024 shots, 1 qubit)
    c = infer_contract(target="local_sim", shots_requested=1024, shots_executed=1024, n_qubits=1)
    return {
        "template": c.model_dump() if hasattr(c, "model_dump") else c.dict(),
        "notes": [
            "This is a *declaration* of the model + data assumptions under which KPIs were computed.",
            "Per-experiment contracts should be attached to experiment records and returned by /experiments endpoints.",
        ],
    }
