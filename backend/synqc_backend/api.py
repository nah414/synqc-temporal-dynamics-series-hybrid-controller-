from __future__ import annotations

from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .engine import SynQcEngine
from .hardware_backends import list_backends
from .models import (
    ExperimentPreset,
    ExperimentStatus,
    HardwareTarget,
    HardwareTargetsResponse,
    RunExperimentRequest,
    RunExperimentResponse,
    ExperimentSummary,
)
from .storage import ExperimentStore


# Instantiate storage and engine
persist_path = Path("./synqc_experiments.json")
store = ExperimentStore(max_entries=512, persist_path=persist_path)
engine = SynQcEngine(store=store)

app = FastAPI(
    title="SynQc Temporal Dynamics Series Backend",
    description=(
        "Backend API for SynQc TDS console — exposes high-level experiment presets "
        "(health, latency, backend comparison, DPD demo) and returns KPIs.")
)

# CORS: allow localhost UIs and simple static frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # SECURITY: Do not combine allow_credentials=True with a wildcard origin.
    # For local dev, we keep origins open but disable credentials.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Simple health check endpoint."""
    return {
        "status": "ok",
        "env": settings.env,
        "max_shots_per_experiment": settings.max_shots_per_experiment,
        "max_shots_per_session": settings.max_shots_per_session,
        "default_shot_budget": settings.default_shot_budget,
        "allow_remote_hardware": settings.allow_remote_hardware,
        "presets": [p.value for p in ExperimentPreset],
    }


@app.get("/hardware/targets", response_model=HardwareTargetsResponse, tags=["hardware"])
def get_hardware_targets() -> HardwareTargetsResponse:
    """List available hardware targets.

    The registry surfaces production-grade providers plus the local simulator so
    deployments can drive real hardware or run dry-runs without credentials.
    """
    targets: List[HardwareTarget] = []
    for backend_id, backend in list_backends().items():
        if (not settings.allow_remote_hardware) and backend_id != "sim_local":
            continue
        targets.append(
            HardwareTarget(
                id=backend_id,
                name=backend.name,
                kind=backend.kind,
                description=("Local SynQc simulator" if backend.kind == "sim" else "Production hardware backend"),
            )
        )
    return HardwareTargetsResponse(targets=targets)


@app.post("/experiments/run", response_model=RunExperimentResponse, tags=["experiments"])
def run_experiment(req: RunExperimentRequest) -> RunExperimentResponse:
    """Run a SynQc experiment preset and return KPIs and metadata."""
    try:
        return engine.run_experiment(req)
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/experiments/{experiment_id}", response_model=RunExperimentResponse, tags=["experiments"])
def get_experiment(experiment_id: str) -> RunExperimentResponse:
    """Return a specific experiment run by id."""
    run = store.get(experiment_id)
    if not run:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return run


@app.get("/experiments/recent", response_model=list[ExperimentSummary], tags=["experiments"])
def list_recent_experiments(limit: int = 50) -> list[ExperimentSummary]:
    """Return the most recent experiment summaries (bounded)."""
    if limit <= 0:
        raise HTTPException(status_code=400, detail="limit must be positive")
    return store.list_recent(limit=limit)
