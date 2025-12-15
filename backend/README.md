# SynQc TDS Backend v0.1

Backend API and engine for the **SynQc Temporal Dynamics Series (SynQc TDS)** console.

This package provides:

- A FastAPI application with endpoints for running **SynQc experiment presets**
  (health diagnostics, latency characterization, backend comparison, DPD demo).
- A `SynQcEngine` that:
  - Validates and normalizes requests,
  - Applies basic **safety and shot-limit guardrails**,
  - Routes to a hardware backend (local simulator by default),
  - Computes **KPIs** (fidelity, latency, backaction, shot usage, status).
- A simple in-memory (with optional JSON) **experiment store** for recent runs.
- A **hardware target registry** pre-populated with five production provider shells
  (AWS Braket, IBM Quantum, Microsoft Azure Quantum, IonQ Cloud, Rigetti Forest)
  plus the local simulator so consumers can point SynQc TDS at real hardware stacks
  while retaining the same API surface.

> This is a structured skeleton meant to be stable and extensible.
> Real hardware integration (AWS Braket, IBM Qiskit, Azure Quantum, IonQ native, Rigetti SDK)
> should be plugged into `synqc_backend.hardware_backends` in a controlled way, without
> touching the API contracts.

---

## Requirements

- Python **3.12+**
- Recommended: create a virtual environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

Or install just the runtime deps:

```bash
pip install fastapi uvicorn[standard] pydantic numpy
```

---

## How to Run the Backend (Local)

From the project root (where this README and `pyproject.toml` live):

```bash
uvicorn synqc_backend.api:app --host 0.0.0.0 --port 8001 --reload
```

Then you can access:

- API docs: http://localhost:8001/docs
- Health check: `GET /health`
- Hardware targets: `GET /hardware/targets`
- Run experiment: `POST /experiments/run`

---

## Core Concepts

### Presets (High-Level Experiments)

The backend currently supports four high-level **presets** that align with the SynQc TDS UI:

- `health` — Qubit Health Diagnostics (T1/T2*/echo/RB conceptual bundle).
- `latency` — Latency Characterization probes.
- `backend_compare` — Backend A/B Comparison (currently returns a single simulated result;
  future work will query multiple hardware backends).
- `dpd_demo` — Guided SynQc Drive–Probe–Drive demo (simulated only).

Each preset is a **recipe** that the backend turns into lower-level control sequences.
For now, the implementation is a **simulated KPI generator** tuned to reasonable ranges,
with the structure ready for real hardware integration.

### KPIs

For each experiment run, the backend returns a `KpiBundle` with:

- `fidelity` (float, 0–1),
- `latency_us` (float, approximate microseconds),
- `backaction` (float, 0–1),
- `shots_used` (int),
- `shot_budget` (int),
- `status` ("ok" | "warn" | "fail").

These map directly onto the tiles in the SynQc TDS frontend.

### Safety & Guardrails

The engine enforces:

- A **maximum shot budget per experiment** (configurable via settings),
- A soft warning if large shot budgets are used on non-simulator targets,
- A simple per-process **session shot counter** (resets on restart).

Future work can extend this into persistent, per-user quotas.

---

## File Layout

- `synqc_backend/__init__.py` — package marker.
- `synqc_backend/config.py` — configuration & settings.
- `synqc_backend/models.py` — Pydantic models and enums (presets, KPIs, requests, responses).
- `synqc_backend/hardware_backends.py` — abstraction and implementations for hardware backends.
- `synqc_backend/engine.py` — `SynQcEngine` orchestration and safety checks.
- `synqc_backend/storage.py` — simple in-memory (optional JSON) experiment store.
- `synqc_backend/api.py` — FastAPI application exposing the REST endpoints.

This structure is intentionally clear so that future additions (e.g., real QPU support)
can be isolated and reviewed.

---

## Notes for Future Hardware Integration

1. **Do not modify API contracts lightly.**  
   Frontends (SynQc TDS and others) rely on the `RunExperimentRequest` and
   `RunExperimentResponse` shapes defined in `models.py`.

2. **Add new backends by subclassing `BaseBackend`.**  
   Implement the `run_experiment` method and register the backend in
   `get_backend()` in `hardware_backends.py`.

3. **Keep risk and quota logic in `engine.py`.**  
   This isolates safety-related reasoning in one place, making audits and changes easier.

4. **Use clear version tags.**  
   Whenever major behavior changes, bump a version string somewhere visible (e.g. in `config.py`
   and the README) and log it.

---

This backend is versioned as:

> **SynQc TDS Backend v0.1 (2025-12-11, America/Chicago)**

and matches the SynQc TDS frontend console v0.1 you currently have.
