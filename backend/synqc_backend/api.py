from __future__ import annotations

from pathlib import Path
from typing import List

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
import atexit

from .budget import BudgetTracker
from .config import settings
from .engine import SynQcEngine
from .hardware_backends import list_backends
from .jobs import JobQueue
from .metrics import MetricsExporter
from .models import (
    ExperimentPreset,
    ExperimentStatus,
    HardwareTarget,
    HardwareTargetsResponse,
    RunExperimentRequest,
    RunExperimentResponse,
    RunJobStatus,
    RunStatusResponse,
    RunSubmissionResponse,
    ExperimentSummary,
)
from .storage import ExperimentStore


# Instantiate storage, budget tracker, engine, and queue
persist_path = Path("./synqc_experiments.json")
store = ExperimentStore(max_entries=512, persist_path=persist_path)
budget_tracker = BudgetTracker(
    redis_url=settings.redis_url, session_ttl_seconds=settings.session_budget_ttl_seconds
)
engine = SynQcEngine(store=store, budget_tracker=budget_tracker)
queue = JobQueue(engine.run_experiment, max_workers=settings.worker_pool_size)
queue = JobQueue(engine.run_experiment, max_workers=settings.worker_pool_size, store=store)
metrics_exporter = MetricsExporter(
    budget_tracker=budget_tracker,
    queue=queue,
    enabled=settings.enable_metrics,
    port=settings.metrics_port,
    bind_address=settings.metrics_bind_address,
    collection_interval_seconds=settings.metrics_collection_interval_seconds,
)
metrics_exporter.start()
atexit.register(queue.shutdown, timeout=settings.job_graceful_shutdown_seconds)

app = FastAPI(
    title="SynQc Temporal Dynamics Series Backend",
    description=(
        "Backend API for SynQc TDS console — exposes high-level experiment presets "
        "(health, latency, backend comparison, DPD demo) and returns KPIs.")
)

def _cors_origins() -> list[str]:
    # Ensures we never accidentally allow "*" when credentials are enabled.
    return settings.cors_allow_origins or []


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Simple API-key guard for execution and data endpoints."""

    if settings.env == "dev" and not settings.require_api_key:
        return

    if not settings.api_key:
        raise HTTPException(status_code=500, detail="Server missing API key configuration")

    if x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Unauthorized")


def get_session_id(x_session_id: str | None = Header(default=None)) -> str:
    """Derive a session identifier used for budgeting.

    Prefer an explicit X-Session-Id header; otherwise, fall back to a stable
    identifier derived from the API key or a local default so budgets are still
    applied per caller.
    """

    if x_session_id:
        return x_session_id
    if settings.api_key:
        return f"api_key:{settings.api_key}"
    return "local-session"


# CORS: allow only configured origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
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
        "require_api_key": settings.require_api_key,
        "redis_url": settings.redis_url,
        "worker_pool_size": settings.worker_pool_size,
        "cors_allow_origins": _cors_origins(),
        "metrics": {
            "enabled": settings.enable_metrics,
            "port": settings.metrics_port,
            "collection_interval_seconds": settings.metrics_collection_interval_seconds,
        },
        "presets": [p.value for p in ExperimentPreset],
        "budget_tracker": budget_tracker.health_summary(),
        "queue": queue.stats(),
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


@app.post(
    "/runs",
    response_model=RunSubmissionResponse,
    tags=["experiments"],
    status_code=status.HTTP_202_ACCEPTED,
)
def submit_run(
    req: RunExperimentRequest,
    _: None = Depends(require_api_key),
    session_id: str = Depends(get_session_id),
) -> RunSubmissionResponse:
    """Submit a run to the background queue and return a job handle."""

    return _enqueue_run(req, session_id)


@app.get("/runs/{run_id}", response_model=RunStatusResponse, tags=["experiments"])
def get_run_status(run_id: str, _: None = Depends(require_api_key)) -> RunStatusResponse:
    """Poll the status of a submitted run."""

    record = queue.get(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="Run not found")

    return RunStatusResponse(
        id=record.id,
        status=RunJobStatus(record.status),
        created_at=record.created_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
        error=record.error,
        error_detail=record.error_detail,
        result=record.result,
    )


@app.post(
    "/experiments/run",
    response_model=RunSubmissionResponse,
    tags=["experiments"],
    status_code=status.HTTP_202_ACCEPTED,
)
def run_experiment(
    req: RunExperimentRequest,
    _: None = Depends(require_api_key),
    session_id: str = Depends(get_session_id),
) -> RunSubmissionResponse:
    """Deprecated convenience wrapper for submitting runs to the queue."""

    return _enqueue_run(req, session_id)


def _enqueue_run(req: RunExperimentRequest, session_id: str) -> RunSubmissionResponse:
    if (not settings.allow_remote_hardware) and req.hardware_target != "sim_local":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "remote_hardware_disabled",
                "message": "Remote hardware is disabled on this deployment",
            },
        )
    backends = list_backends()
    if req.hardware_target not in backends:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "unknown_hardware_target",
                "message": f"Unknown hardware_target '{req.hardware_target}'",
            },
        )
    backend = backends[req.hardware_target]
    if (
        backend.kind != "sim"
        and not settings.allow_provider_simulation
        and settings.allow_remote_hardware
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "provider_simulation_disabled",
                "message": (
                    "Provider simulation is disabled; enable SYNQC_ALLOW_PROVIDER_SIMULATION=true or use sim_local."
                ),
            },
        )

    record = queue.enqueue(req, session_id)
    return RunSubmissionResponse(
        id=record.id,
        status=RunJobStatus.QUEUED,
        created_at=record.created_at,
    )


@app.get("/experiments/{experiment_id}", response_model=RunExperimentResponse, tags=["experiments"])
def get_experiment(experiment_id: str, _: None = Depends(require_api_key)) -> RunExperimentResponse:
    """Return a specific experiment run by id."""
    run = store.get(experiment_id)
    if not run:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return run


@app.get("/experiments/recent", response_model=list[ExperimentSummary], tags=["experiments"])
def list_recent_experiments(limit: int = 50, _: None = Depends(require_api_key)) -> list[ExperimentSummary]:
    """Return the most recent experiment summaries (bounded)."""
    if limit <= 0:
        raise HTTPException(status_code=400, detail="limit must be positive")
    return store.list_recent(limit=limit)
