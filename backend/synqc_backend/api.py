from __future__ import annotations

from pathlib import Path
from typing import List, Optional
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
import atexit

from .budget import BudgetTracker
from .config import settings
from .control_profiles import ControlProfileStore, ControlProfileUpdate, ControlProfile
from .engine import SynQcEngine
from .auth import auth_router
from .auth.store import AuthStore
from .auth.deps import require_scopes
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
    QubitTelemetry,
)
from .qubit_usage import SessionQubitTracker
from .storage import ExperimentStore


# Instantiate storage, budget tracker, engine, and queue
persist_path = Path("./synqc_experiments.json")
store = ExperimentStore(max_entries=512, persist_path=persist_path)
budget_tracker = BudgetTracker(
    redis_url=settings.redis_url,
    session_ttl_seconds=settings.session_budget_ttl_seconds,
    fail_open_on_redis_error=settings.budget_fail_open_on_redis_error,
)
control_store = ControlProfileStore(persist_path=Path("./synqc_controls.json"))
qubit_tracker = SessionQubitTracker(ttl_seconds=settings.session_budget_ttl_seconds)
engine = SynQcEngine(
    store=store,
    budget_tracker=budget_tracker,
    control_store=control_store,
    usage_tracker=qubit_tracker,
)
queue = JobQueue(
    engine.run_experiment,
    max_workers=settings.worker_pool_size,
    store=store,
    persistence_path=settings.job_queue_db_path,
    job_timeout_seconds=settings.job_timeout_seconds,
    max_pending=settings.job_queue_max_pending,
)
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

auth_store = AuthStore(settings.auth_db_path)
app.state.auth_store = auth_store
app.include_router(auth_router, prefix="/auth", tags=["auth"])

def _cors_origins() -> list[str]:
    # Ensures we never accidentally allow "*" when credentials are enabled.
    return settings.cors_allow_origins or []


def _extract_bearer_token(authorization: str) -> Optional[str]:
    """
    Parse Authorization header. Accepts:
      Authorization: Bearer <token>
    Returns token or None.
    """
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return None
    token = token.strip()
    return token or None


def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-Api-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> None:
    """
    Enforce API auth.

    Accepted:
      - X-Api-Key: <secret>
      - Authorization: Bearer <secret>

    This uses the same configured secret for both header types.
    """
    # Be defensive about settings shape so this patch won't crash if names differ slightly.
    expected = getattr(settings, "api_key", None)
    require = getattr(settings, "require_api_key", None)

    # If the codebase has a boolean toggle, respect it.
    # Otherwise, require auth when an api_key is configured.
    if require is None:
        require = bool(expected)

    if not require:
        return

    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "api_key_not_configured",
                "message": "API key enforcement is enabled but no API key is configured on the server.",
            },
        )

    # 1) X-Api-Key header
    if x_api_key and secrets.compare_digest(x_api_key, expected):
        return

    # 2) Authorization: Bearer <token>
    token = _extract_bearer_token(authorization or "")
    if token and secrets.compare_digest(token, expected):
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "unauthorized",
            "message": "Missing or invalid API credentials. Use X-Api-Key or Authorization: Bearer <token>.",
        },
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_session_id(
    x_session_id: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-Api-Key"),
) -> str:
    """Derive a session identifier used for budgeting.

    Prefer an explicit X-Session-Id header; otherwise, fall back to a stable
    identifier derived from the API key or a local default so budgets are still
    applied per caller.
    """

    if x_session_id:
        return x_session_id
    token = x_api_key.strip() if x_api_key else None
    if not token:
        token = _extract_bearer_token(authorization or "")
    if token:
        return f"api_key:{token}"
    if settings.api_key:
        return "api_key:default"
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
        "control_profile": control_store.get(),
        "qubit_usage": qubit_tracker.health(),
    }


@app.get("/controls/profile", response_model=ControlProfile, tags=["controls"])
def get_control_profile(_: None = Depends(require_api_key)) -> ControlProfile:
    """Return the active manual control profile."""

    return control_store.get()


@app.post("/controls/profile", response_model=ControlProfile, tags=["controls"])
def update_control_profile(
    patch: ControlProfileUpdate,
    _: None = Depends(require_api_key),
) -> ControlProfile:
    """Update the manual control profile and persist it."""

    return control_store.update(patch)


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
    __: None = Depends(require_scopes("experiments:run")),
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


@app.get("/telemetry/qubits", response_model=QubitTelemetry, tags=["telemetry"])
def get_qubit_telemetry(
    _: None = Depends(require_api_key),
    session_id: str = Depends(get_session_id),
) -> QubitTelemetry:
    """Return session-scoped qubit usage for visualization."""

    snapshot = qubit_tracker.snapshot(session_id)
    # If no runs have been executed yet this session, fall back to latest stored run
    last_run_qubits = snapshot.last_run_qubits or None
    if last_run_qubits is None:
        recent = store.list_recent(limit=1)
        if recent:
            last_run_qubits = recent[0].qubits_used

    return QubitTelemetry(
        session_total_qubits=snapshot.session_total,
        last_run_qubits=last_run_qubits,
        last_updated=snapshot.last_updated,
    )
