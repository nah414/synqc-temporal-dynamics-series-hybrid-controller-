# SynQc TDS Console — Sleek Repo v0.4

This repository combines:

- The **approved SynQc TDS frontend console look** (single-file UI).
- A **FastAPI backend** that runs SynQc experiment presets and returns KPIs.
- The **SynQc Temporal Dynamics Series technical archive** (for engineering + GPT context).
- A **GPT Pro context instruction file** for configuring a SynQc Guide assistant.
- A **five-vendor hardware target roster** (AWS Braket, IBM Quantum, Microsoft Azure
  Quantum, IonQ Cloud, Rigetti Forest) plus the local simulator, illustrating how
  SynQc TDS plugs into a consumer hardware stack and software pipeline while
  preserving correction/accuracy and prediction workflows.

## What’s new in v0.4

- Primary nav is now **fully functional** and maps to real backend capability:
  - **Console**: run presets + KPIs + inline history
  - **Experiments**: read-only list from `GET /experiments/recent` (click a row to open Details)
  - **Hardware**: list from `GET /hardware/targets`
  - **Details**: record view from `GET /experiments/{id}` (replaces misleading “Logs”)
- Fixed a JavaScript brace issue so the UI script executes reliably.
- Filters now work independently on both Console history and the Experiments page.

## What’s new in v0.3

- Frontend visuals upgraded (still single-file, no external assets):
  - Bloch “atmosphere”, rotating rings, animated trace paths, and a DPD timeline spark.
  - KPIs now drive subtle animation cues (fidelity ↔ glow, latency ↔ spin speed, backaction ↔ noise).
- Setup panel pulls backend guardrails from `GET /health`:
  - `max_shots_per_experiment` drives the **Shot budget max** label and input clamp.
  - `default_shot_budget` is used when the field is empty/invalid.
- `GET /hardware/targets` respects `allow_remote_hardware` (filters non-sim targets when disabled).
- Added a single-file, fullstack review artifact: `SYNQC_FULLSTACK_ONEFILE_v0.4.md`.
- Control panel includes the credit line: **Developed by eVision Enterprises**.

## What’s new in v0.2

- Frontend chat logging is now **XSS-safe** (no `innerHTML`; all message text is rendered via `textContent`).
- Frontend now includes a **Run preset** action wired to the backend:
  - Calls `POST /experiments/run`
  - Updates KPI tiles + run history
  - Pulls `/hardware/targets` + `/experiments/recent` on load
- Backend CORS is adjusted for sanity: wildcard origins allowed for local dev, **credentials disabled**.
- Backend includes **production-targeted provider shells** (AWS / IBM / Microsoft / IonQ / Rigetti) plus the simulator so the UI and API remain stable while credentials and live SDKs are wired in.

---

## Repo layout

- `web/index.html`
  - The console UI (portable, no external assets).  
  - By default it assumes the backend is running at `http://localhost:8001`.
  - Override with `?api=http://HOST:PORT` (example below).

- `backend/`
  - Python package `synqc_backend` (FastAPI + engine + storage).

- `docs/SynQc_Temporal_Dynamics_Series_Technical_Archive_v0_1.md`
  - Full technical archive (design + guardrails + workflow reference).

- `gpt/SynQc_GPT_Pro_Context_Instructions_v0_1.md`
  - Copy/paste instructions for building a GPT called **SynQc Guide** using the knowledge file above.

---

## Run it locally (Windows-friendly)

### 1) Start the backend

From the repo root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .\backend
uvicorn synqc_backend.api:app --host 127.0.0.1 --port 8001 --reload
```

Open backend docs:
- `http://127.0.0.1:8001/docs`

### 2) Open the frontend

Option A (fastest): open `web/index.html` directly in your browser.

Option B (recommended): serve it so the browser origin is clean:

```powershell
cd web
py -m http.server 8080
```

Then open:
- `http://127.0.0.1:8080/`

### 3) (Optional) Point the UI at a different backend URL

If your backend isn’t on `localhost:8001`, open:

- `http://127.0.0.1:8080/?api=http://127.0.0.1:8001`

---

## Security note (why the XSS fix matters)

Any time user text or backend text touches the DOM, treat it as hostile input.  
This repo’s UI now renders message and table text using DOM nodes + `textContent`, not HTML injection.

---

Version tag:
- **Sleek Repo v0.4 (2025-12-12)**