from __future__ import annotations

import atexit
import logging
import secrets
import gc
import uuid
import os
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import List, Optional, Literal

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, status, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from synqc_backend.consumer_api import router as consumer_router
from synqc_backend.middleware import add_default_middlewares
from synqc_backend.orchestration import get_event_store

from .budget import BudgetTracker
from .config import settings
from synqc_backend.settings import SynQcSettings
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
from .metrics import MetricsExporter, MetricsExporterGuard, shared_prometheus_registry
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

SYSTEM_PRIME = (
    "You are SynQc Guide, assisting with SynQc Temporal Dynamics (Drive→Probe→Drive). "
    "Be concise, call out latency/backaction trade-offs, and map goals to presets "
    "(health diagnostics, latency characterization, backend comparison, guided DPD)."
)

# Instantiate storage, budget tracker, engine, and queue
configure_json_logging()
logger = get_logger(__name__)
startup_warnings: list[str] = []

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
metrics_exporter = None
metrics_guard = None
shared_registry = None
if settings.metrics_shared_registry_endpoint_enabled or settings.metrics_use_shared_registry:
    shared_registry = shared_prometheus_registry()

def _build_metrics_exporter(registry):
    return MetricsExporter(
        budget_tracker=budget_tracker,
        queue=queue,
        enabled=settings.enable_metrics,
        port=settings.metrics_port,
        bind_address=settings.metrics_bind_address,
        collection_interval_seconds=settings.metrics_collection_interval_seconds,
        registry=registry,
    )


def _start_metrics_exporter(registry):
    try:
        exporter = _build_metrics_exporter(registry)
        exporter.start()
        return exporter
    except Exception as exc:
        startup_warnings.append(
            "Metrics exporter disabled (will keep API running): %s" % exc
        )
        logger.warning("metrics exporter failed to start; continuing without metrics", exc_info=True)
        return None


if settings.enable_metrics:
    registry = shared_registry if shared_registry is not None else None
    metrics_exporter = _start_metrics_exporter(registry)
    metrics_guard = MetricsExporterGuard(
        lambda: _build_metrics_exporter(registry),
        check_interval_seconds=settings.metrics_guard_check_interval_seconds,
        restart_backoff_seconds=settings.metrics_guard_restart_backoff_seconds,
        initial_exporter=metrics_exporter,
    )
    metrics_guard.start()
atexit.register(queue.shutdown, timeout=settings.job_graceful_shutdown_seconds)

chat_rate_windows: dict[str, deque[float]] = defaultdict(deque)
chat_rate_lock = Lock()


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

docs_enabled = settings.env != "prod"
app = FastAPI(
    title="SynQc Temporal Dynamics Series Backend",
    description=(
        "Backend API for SynQc TDS console — exposes high-level experiment presets "
        "(health, latency, backend comparison, DPD demo) and returns KPIs."),
    docs_url="/docs" if docs_enabled else None,
    redoc_url="/redoc" if docs_enabled else None,
    openapi_url="/openapi.json" if docs_enabled else None,
)

add_default_middlewares(app)


def _backend_version() -> str:
    try:
        return metadata.version("synqc-tds-backend")
    except Exception:
        return "unknown"

auth_store = AuthStore(settings.auth_db_path)
app.state.auth_store = auth_store
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(physics_router)
app.include_router(consumer_router)

if settings.metrics_shared_registry_endpoint_enabled:
    try:
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

        metrics_registry = shared_prometheus_registry()

        @app.get("/metrics", include_in_schema=False, dependencies=[Depends(require_api_key)])
        async def shared_metrics() -> Response:
            return Response(generate_latest(metrics_registry), media_type=CONTENT_TYPE_LATEST)

    except Exception:  # pragma: no cover - defensive guard for optional dependency
        logger.warning("Prometheus client not available; shared metrics endpoint disabled")


@app.on_event("shutdown")
async def _shutdown() -> None:
    await close_redis()

def _cors_origins() -> list[str]:
    if settings.env == "dev":
        return ["*"]
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

    if not require and not settings.auth_required:
        return

    if settings.auth_required and not expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": ErrorCode.AUTH_REQUIRED.value,
                "error_code": ErrorCode.AUTH_REQUIRED.value,
                "error_message": "Authentication required. Configure JWT or set SYNQC_API_KEY.",
                "error_detail": {"code": ErrorCode.AUTH_REQUIRED.value},
                "action_hint": "Provide Authorization: Bearer <token> or configure SYNQC_API_KEY.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not expected:
        return

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


class ChatTurn(BaseModel):
    role: Literal["user", "assistant", "system"] = Field(..., description="Message role")
    content: str = Field(..., description="Message content")


class ChatRequest(BaseModel):
    prompt: str = Field(..., description="Latest user prompt")
    history: list[ChatTurn] = Field(default_factory=list, description="Rolling chat history")
    preset: str | None = Field(default=None, description="UI-selected preset")
    hardware: str | None = Field(default=None, description="UI-selected hardware target")
    mode: str | None = Field(default=None, description="UI mode (explore/calibrate/prod)")


class ChatResponse(BaseModel):
    reply: str
    model: str
    usage: dict | None = None


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
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _inject_log_context(request: Request, call_next):
    request_id = getattr(request.state, "request_id", None) or request.headers.get("X-Request-Id") or str(uuid.uuid4())
    session_id = get_session_id(
        x_session_id=request.headers.get("X-Session-Id"),
        authorization=request.headers.get("Authorization"),
        x_api_key=request.headers.get("X-Api-Key"),
    )

    with log_context(request_id=request_id, session_id=session_id, path=request.url.path, method=request.method):
        response = await call_next(request)

    return response

@app.middleware("http")
async def _security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=()",
    )
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; connect-src 'self' https:; img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'",
    )
    if settings.env == "prod":
        response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
    return response

_HEALTH_CACHE: dict[str, object] = {"expires_at": 0.0, "payload": None}
_HEALTH_CACHE_LOCK = Lock()


@app.get("/health", tags=["meta"])
async def health() -> dict:
    """Simple health check endpoint."""
    warnings: list[str] = []

    def _safe(label: str, default: object, func):
        try:
            return func()
        except Exception as exc:  # pragma: no cover - defensive health path
            warnings.append(f"{label} unavailable: {exc}")
            logger.warning("health check skipped %s due to error", label, exc_info=True)
            return default

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
        "assistant": {
            "openai_chat_ready": bool(settings.openai_api_key or os.getenv("OPENAI_API_KEY")),
            "model": settings.openai_model,
        },
        "metrics": {
            "enabled": settings.enable_metrics,
            "port": settings.metrics_port,
            "collection_interval_seconds": settings.metrics_collection_interval_seconds,
            "guard": {
                "check_interval_seconds": settings.metrics_guard_check_interval_seconds,
                "restart_backoff_seconds": settings.metrics_guard_restart_backoff_seconds,
                "restart_count": getattr(metrics_guard, "restart_count", 0),
            },
        },
        "presets": [p.value for p in ExperimentPreset],
        "visible_target_count": len(list_provider_targets()),
        "budget_tracker": _safe("budget", {}, budget_tracker.health_summary),
        "queue": _safe("queue", {}, queue.stats),
        "queue_connectivity": _safe("queue.health", {}, lambda: getattr(queue, "health", lambda: {})()),
        "control_profile": _safe("control_profile", {}, control_store.get),
        "qubit_usage": _safe("qubit_usage", {}, qubit_tracker.health),
        "persistence": _safe("persistence", {}, store.health_summary),
        "provider_metrics": _safe("provider_metrics", {}, provider_metrics.health_summary),
    }
    if startup_warnings:
        warnings.extend(startup_warnings)
    try:
        payload["redis"] = await redis_ping()
    except Exception as exc:  # pragma: no cover - defensive health path
        payload.setdefault("warnings", []).append("Redis ping failed; continuing without cache.")
        payload["redis"] = {"ok": False, "error": str(exc)}
    if warnings:
        payload.setdefault("warnings", []).extend(warnings)
    if ttl_seconds > 0:
        with _HEALTH_CACHE_LOCK:
            _HEALTH_CACHE["payload"] = payload
            _HEALTH_CACHE["expires_at"] = monotonic() + ttl_seconds
    return payload


async def _invoke_openai_chat(body: ChatRequest) -> ChatResponse:
    api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_message": "OpenAI API key missing; set SYNQC_OPENAI_API_KEY or OPENAI_API_KEY.",
                "error_code": ErrorCode.AUTH_REQUIRED.value,
                "action_hint": "Export OPENAI_API_KEY for the api container or pass SYNQC_OPENAI_API_KEY.",
            },
        )

    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PRIME}]
    context_bits: list[str] = []
    if body.preset:
        context_bits.append(f"Preset: {body.preset}")
    if body.hardware:
        context_bits.append(f"Hardware: {body.hardware}")
    if body.mode:
        context_bits.append(f"Mode: {body.mode}")
    if context_bits:
        messages.append({"role": "system", "content": "Context: " + " · ".join(context_bits)})

    history = body.history[-6:]
    for turn in history:
        messages.append(turn.model_dump())
    messages.append({"role": "user", "content": body.prompt})

    payload = {
        "model": settings.openai_model,
        "messages": messages,
        "temperature": 0.35,
        "max_tokens": 400,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    base = settings.openai_base_url.rstrip("/") or "https://api.openai.com/v1"
    url = f"{base}/chat/completions"

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            resp = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:  # pragma: no cover - network guard
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error_message": f"OpenAI chat request failed: {exc}"},
        ) from exc

    if resp.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error_message": f"OpenAI chat error {resp.status_code}",
                "error_detail": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text,
            },
        )

    data = resp.json()
    reply = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    if not reply:
        reply = "No reply returned from the model."

    return ChatResponse(reply=reply, model=data.get("model", settings.openai_model), usage=data.get("usage"))


def _enforce_chat_rate_limit(session_id: str) -> None:
    """Guard the agent chat proxy with a sliding-window rate limit."""

    window_seconds = settings.agent_chat_limit_window_seconds
    max_requests = settings.agent_chat_limit_requests
    now = monotonic()
    cutoff = now - window_seconds

    with chat_rate_lock:
        window = chat_rate_windows[session_id]
        while window and window[0] < cutoff:
            window.popleft()
        if len(window) >= max_requests:
            retry_after = max(1, int(window[0] + window_seconds - now))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error_code": ErrorCode.RATE_LIMITED.value,
                    "error_message": "Agent chat rate limit reached.",
                    "error_detail": {
                        "retry_after_seconds": retry_after,
                        "limit": max_requests,
                        "window_seconds": window_seconds,
                    },
                    "action_hint": f"Wait {retry_after} seconds before retrying.",
                },
                headers={"Retry-After": str(retry_after)},
            )
        window.append(now)


@app.post("/agent/chat", response_model=ChatResponse, tags=["agent"])
async def agent_chat(
    body: ChatRequest,
    session_id: str = Depends(get_session_id),
    _: None = Depends(require_api_key),
) -> ChatResponse:
    _enforce_chat_rate_limit(session_id)
    return await _invoke_openai_chat(body)


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
    from synqc_backend.settings import settings as settings_singleton

    settings_ref = settings
    if getattr(settings_ref, "allow_remote_hardware", True) is False and req.hardware_target != "sim_local":
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
    allow_remote_sources = []
    for src in (settings_ref, settings_singleton):
        raw_flag = getattr(src, "allow_remote_hardware", True)
        override_flag = getattr(getattr(src, "__dict__", {}), "get", lambda *_: raw_flag)(
            "allow_remote_hardware"
        )
        allow_remote_sources.append(override_flag)

    try:
        for obj in gc.get_objects():
            if type(obj).__name__ == "SynQcSettings" and hasattr(obj, "allow_remote_hardware"):
                allow_remote_sources.append(getattr(obj, "allow_remote_hardware", True))
    except Exception:
        pass

    allow_remote = all(flag is True for flag in allow_remote_sources)

    if (not allow_remote) and req.hardware_target != "sim_local":
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
    if target.kind != "sim":
        if not allow_remote:
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

        if not (credentials_ok or settings_ref.allow_provider_simulation):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": ErrorCode.PROVIDER_SIM_DISABLED.value,
                    "error_code": ErrorCode.PROVIDER_SIM_DISABLED.value,
                    "error_message": (
                        "Provider simulation is disabled for this deployment"
                    ),
                    "error_detail": {
                        "code": ErrorCode.PROVIDER_SIM_DISABLED.value,
                        "allow_remote_hardware": allow_remote_sources[0] if allow_remote_sources else None,
                        "allow_remote_sources": list(allow_remote_sources),
                    },
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
            "mode": req.mode or "explore",
        },
    )
    return RunSubmissionResponse(
        id=job_id,
        status=RunJobStatus.QUEUED,
        created_at=created_at,
    )


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


@app.get("/experiments/{experiment_id}/events", tags=["experiments"])
def experiment_events(experiment_id: str, limit: int = 300, _: None = Depends(require_api_key)) -> dict:
    """Return recent orchestration events for an experiment."""

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

    store_events = get_event_store()
    return {"experiment_id": experiment_id, "events": store_events.list(experiment_id, limit=limit)}


@app.delete("/experiments/{experiment_id}/events", status_code=204, tags=["experiments"])
def clear_experiment_events(experiment_id: str, _: None = Depends(require_api_key)) -> None:
    """Clear stored events for an experiment."""

    store_events = get_event_store()
    store_events.clear(experiment_id)
    return None


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
