# SynQc Physics Contract Patch Pack v0.1 — Integration Notes

This pack adds *new files only* (no existing files modified) so you can merge safely.

## What you get

- `docs/SynQc_Definitions_and_Measurement_Model_v0_1.md`
  - The spec/contract that prevents "decorative noun" KPIs.

- `backend/synqc_backend/physics_router.py`
  - New endpoints:
    - `GET /physics/definitions`
    - `GET /physics/contract`

- `backend/synqc_backend/physics_contract.py`
  - Pydantic models + helpers to attach a per-experiment contract.

- `backend/synqc_backend/kpi_estimators.py` + `backend/synqc_backend/stats.py`
  - Distribution fidelity + bootstrap CI utilities (shot-sampled, hardware-valid).

- `backend/tests/test_shot_scaling.py`
  - A sanity test proving CI width shrinks ~ N^{-1/2} for a sampling-based KPI.

## Minimal code changes you still need to make (manual)

1) Register the physics router in your FastAPI app

In `backend/synqc_backend/api.py` (or wherever `app = FastAPI(...)` lives):

```py
from synqc_backend.physics_router import router as physics_router
app.include_router(physics_router)
```

2) Attach a physics contract to experiment records (recommended)

In the handler for `POST /experiments/run`, after you determine:
  - target
  - shots requested/executed
  - n_qubits (if known)
  - backend job id (if any)

add:

```py
from synqc_backend.physics_contract import infer_contract

record["physics_contract"] = infer_contract(
    target=target,
    shots_requested=shots_requested,
    shots_executed=shots_executed,
    n_qubits=n_qubits,
    backend_id=backend_job_id,
)
```

Store `physics_contract` in SQLite alongside the rest of the experiment record.

3) (Optional) Add per-KPI CI + definition_id

Keep your existing KPI surface for the UI, but add a `kpi_details` field:

```py
from synqc_backend.physics_contract import kpi_definition_id_for_name
from synqc_backend.kpi_estimators import fidelity_dist_ci95_from_counts

kpi_details = []
for name, value in kpis.items():
    definition_id = kpi_definition_id_for_name(name)
    detail = {"name": name, "value": value, "definition_id": definition_id}

    if definition_id == "fidelity_dist_v1" and raw_counts is not None:
        lo, hi = fidelity_dist_ci95_from_counts(raw_counts, expected_q, n_boot=200)
        detail["ci95"] = [lo, hi]

    kpi_details.append(detail)

record["kpi_details"] = kpi_details
```

## Running the added tests

From `backend/` (once your packaging/test setup is in place):

```bash
pytest -q
```

If you don't currently have pytest wired, you can still run the test file directly
(it will behave like a smoke test).
