from __future__ import annotations

import atexit
import logging
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware

from .budget import BudgetTracker
from .config import settings
from .control_profiles import ControlProfileStore, ControlProfileUpdate, ControlProfile
from .engine import SynQcEngine
from .auth import auth_router
from .auth.store import AuthStore
from .auth.deps import require_scopes
from .providers import capabilities as provider_capabilities
from .providers import list_targets as list_provider_targets
from .providers import validate_credentials as validate_provider_credentials
from .physics_router import router as physics_router
from .jobs import JobQueue
from .run_queue import build_run_queue
from .metrics import MetricsExporter
from .models import (
    ExperimentPreset,
    ExperimentStatus,
    ErrorCode,
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
from .redis_bus import close_redis, redis_ping
from .logging_utils import configure_json_logging, log_context, set_log_context, get_logger
from .metrics_recorder import provider_metrics, run_metrics
from importlib import metadata


# Instantiate storage, budget tracker, engine, and queue
configure_json_logging()

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
_embedded_queue = JobQueue(
    engine.run_experiment,
    max_workers=settings.worker_pool_size,
    store=store,
    persistence_path=settings.job_queue_db_path,
    job_timeout_seconds=settings.job_timeout_seconds,
    max_pending=settings.job_queue_max_pending,
)
queue = build_run_queue(_embedded_queue)
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

logger = get_logger(__name__)


def _seed_demo_runs() -> None:
    if not store.is_empty:
        return

    demo_requests = [
        RunExperimentRequest(
            preset=ExperimentPreset.HELLO_QUANTUM_SIM,
            hardware_target="sim_local",
            shot_budget=512,
            notes="Hello Quantum quickstart (sim)",
        ),
        RunExperimentRequest(
            preset=ExperimentPreset.HEALTH,
            hardware_target="sim_local",
            shot_budget=1024,
            notes="Stability smoke-check",
        ),
        RunExperimentRequest(
            preset=ExperimentPreset.LATENCY,
            hardware_target="sim_local",
            shot_budget=640,
            notes="Latency probe",
        ),
        RunExperimentRequest(
            preset=ExperimentPreset.BACKEND_COMPARE,
            hardware_target="aws_braket",
            shot_budget=1200,
            notes="A/B vs simulator",
        ),
        RunExperimentRequest(
            preset=ExperimentPreset.DPD_DEMO,
            hardware_target="sim_local",
            shot_budget=720,
            notes="Guided DPD trace",
        ),
        RunExperimentRequest(
            preset=ExperimentPreset.GROVER_DEMO,
            hardware_target="sim_local",
            shot_budget=640,
            notes="Grover energy-aware search",
        ),
        RunExperimentRequest(
            preset=ExperimentPreset.HEALTH,
            hardware_target="ibm_quantum",
            shot_budget=900,
            notes="Platform drift check",
        ),
    ]

    for req in demo_requests:
        try:
            engine.run_experiment(req, session_id="demo-seed")
        except Exception as exc:  # pragma: no cover - defensive bootstrap
            logger.warning("Demo seed failed for %s on %s: %s", req.preset, req.hardware_target, exc)


_seed_demo_runs()

app = FastAPI(
    title="SynQc Temporal Dynamics Series Backend",
    description=(
        "Backend API for SynQc TDS console — exposes high-level experiment presets "
        "(health, latency, backend comparison, DPD demo) and returns KPIs.")
)


def _backend_version() -> str:
    try:
        return metadata.version("synqc-tds-backend")
    except Exception:
        return "unknown"

auth_store = AuthStore(settings.auth_db_path)
app.state.auth_store = auth_store
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(physics_router)


@app.on_event("shutdown")
async def _shutdown() -> None:
    await close_redis()

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
                "code": ErrorCode.INTERNAL_ERROR.value,
                "error_code": ErrorCode.INTERNAL_ERROR.value,
                "error_message": (
                    "API key enforcement is enabled but no API key is configured on the server."
                ),
                "error_detail": {"code": ErrorCode.INTERNAL_ERROR.value},
                "action_hint": "Set SYNQC_API_KEY or disable require_api_key.",
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
            "code": ErrorCode.AUTH_REQUIRED.value,
            "error_code": ErrorCode.AUTH_REQUIRED.value,
            "error_message": "Missing or invalid API credentials. Use X-Api-Key or Authorization: Bearer <token>.",
            "error_detail": {"code": ErrorCode.AUTH_REQUIRED.value},
            "action_hint": "Pass X-Api-Key or Authorization: Bearer <token>.",
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


@app.middleware("http")
async def _inject_log_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    session_id = get_session_id(
        x_session_id=request.headers.get("X-Session-Id"),
        authorization=request.headers.get("Authorization"),
        x_api_key=request.headers.get("X-Api-Key"),
    )

    with log_context(request_id=request_id, session_id=session_id, path=request.url.path, method=request.method):
        response = await call_next(request)

    response.headers["X-Request-Id"] = request_id
    return response

_HEALTH_CACHE: dict[str, object] = {"expires_at": 0.0, "payload": None}
_HEALTH_CACHE_LOCK = Lock()


@app.get("/health", tags=["meta"])
async def health() -> dict:
    """Simple health check endpoint."""
    ttl_seconds = settings.health_cache_ttl_seconds
    if ttl_seconds > 0:
        now = monotonic()
        with _HEALTH_CACHE_LOCK:
            cached_payload = _HEALTH_CACHE.get("payload")
            expires_at = _HEALTH_CACHE.get("expires_at", 0.0)
            if cached_payload and expires_at > now:
                return cached_payload

    payload = {
        "status": "ok",
        "version": _backend_version(),
        "server_time": datetime.now(timezone.utc).isoformat(),
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
        "visible_target_count": len(list_provider_targets()),
        "budget_tracker": budget_tracker.health_summary(),
        "queue": queue.stats(),
        "queue_connectivity": getattr(queue, "health", lambda: {})(),
        "control_profile": control_store.get(),
        "qubit_usage": qubit_tracker.health(),
        "persistence": store.health_summary(),
        "provider_metrics": provider_metrics.health_summary(),
    }
    payload["redis"] = await redis_ping()
    if ttl_seconds > 0:
        with _HEALTH_CACHE_LOCK:
            _HEALTH_CACHE["payload"] = payload
            _HEALTH_CACHE["expires_at"] = monotonic() + ttl_seconds
    return payload


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
    for target_id, target in list_provider_targets().items():
        if (not settings.allow_remote_hardware) and target.kind != "sim":
            continue
        targets.append(
            HardwareTarget(
                id=target_id,
                name=target.name,
                kind=target.kind,
                description=(
                    "Local SynQc simulator" if target.kind == "sim" else "Production hardware backend"
                ),
                capabilities=provider_capabilities(target_id),
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
        raise HTTPException(
            status_code=404,
            detail={
                "code": ErrorCode.INVALID_REQUEST.value,
                "error_code": ErrorCode.INVALID_REQUEST.value,
                "error_message": "Run not found",
                "error_detail": {"code": ErrorCode.INVALID_REQUEST.value},
                "action_hint": "Verify the run id and try again.",
            },
        )

    return RunStatusResponse(
        id=record.get("id"),
        status=RunJobStatus(record.get("status", RunJobStatus.QUEUED)),
        created_at=record.get("created_at"),
        started_at=record.get("started_at"),
        finished_at=record.get("finished_at"),
        error=record.get("error"),
        error_code=record.get("error_code"),
        error_message=record.get("error_message"),
        error_detail=record.get("error_detail"),
        action_hint=record.get("action_hint"),
        result=record.get("result"),
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
                "code": ErrorCode.REMOTE_DISABLED.value,
                "error_code": ErrorCode.REMOTE_DISABLED.value,
                "error_message": "Remote hardware is disabled on this deployment",
                "error_detail": {"code": ErrorCode.REMOTE_DISABLED.value},
                "action_hint": "Enable remote hardware or target sim_local.",
            },
        )
    targets = list_provider_targets()
    if req.hardware_target not in targets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": ErrorCode.INVALID_TARGET.value,
                "error_code": ErrorCode.INVALID_TARGET.value,
                "error_message": f"Unknown hardware_target '{req.hardware_target}'",
                "error_detail": {"code": ErrorCode.INVALID_TARGET.value},
                "action_hint": "Pick a hardware target from /hardware/targets.",
            },
        )
    target = targets[req.hardware_target]
    credentials_ok = validate_provider_credentials(req.hardware_target)
    if target.kind != "sim" and not (credentials_ok or settings.allow_provider_simulation):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": ErrorCode.PROVIDER_SIM_DISABLED.value,
                "error_code": ErrorCode.PROVIDER_SIM_DISABLED.value,
                "error_message": (
                    "Provider simulation is disabled for this deployment"
                ),
                "error_detail": {"code": ErrorCode.PROVIDER_SIM_DISABLED.value},
                "action_hint": "Enable SYNQC_ALLOW_PROVIDER_SIMULATION=true or supply provider credentials.",
            },
        )

    job_id, created_at = queue.enqueue(req, session_id)
    logger.info(
        "Run submitted",
        extra={
            "job_id": job_id,
            "experiment_id": job_id,
            "hardware_target": req.hardware_target,
            "session_id": session_id,
            "preset": req.preset.value if req.preset else None,
        },
    )
    return RunSubmissionResponse(
        id=job_id,
        status=RunJobStatus.QUEUED,
        created_at=created_at,
    )


@app.get("/experiments/{experiment_id}", response_model=RunExperimentResponse, tags=["experiments"])
def get_experiment(experiment_id: str, _: None = Depends(require_api_key)) -> RunExperimentResponse:
    """Return a specific experiment run by id."""
    run = store.get(experiment_id)
    if not run:
        raise HTTPException(
            status_code=404,
            detail={
                "code": ErrorCode.INVALID_REQUEST.value,
                "error_code": ErrorCode.INVALID_REQUEST.value,
                "error_message": "Experiment not found",
                "error_detail": {"code": ErrorCode.INVALID_REQUEST.value},
                "action_hint": "Verify the experiment id and refresh.",
            },
        )
    return run


@app.get("/experiments/recent", response_model=list[ExperimentSummary], tags=["experiments"])
def list_recent_experiments(limit: int = 50, _: None = Depends(require_api_key)) -> list[ExperimentSummary]:
    """Return the most recent experiment summaries (bounded)."""
    if limit <= 0:
        raise HTTPException(
            status_code=400,
            detail={
                "code": ErrorCode.INVALID_REQUEST.value,
                "error_code": ErrorCode.INVALID_REQUEST.value,
                "error_message": "limit must be positive",
                "error_detail": {"code": ErrorCode.INVALID_REQUEST.value},
                "action_hint": "Use a positive limit value.",
            },
        )
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
