from __future__ import annotations

import json
import time
import uuid
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from pydantic import BaseModel, Field

from .redis_client import get_redis


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class JobErrorInfo(BaseModel):
    code: str
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class JobRecord(BaseModel):
    job_id: str
    agent: str
    status: JobStatus
    created_at_unix: float
    started_at_unix: Optional[float] = None
    finished_at_unix: Optional[float] = None
    attempts: int = 0
    max_attempts: int = 3
    run_input: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    error: Optional[JobErrorInfo] = None
    cancel_requested: bool = False


def _key(job_id: str) -> str:
    return f"synqc:job:{job_id}"


def _idempotency_key(agent: str, key: str) -> str:
    return f"synqc:idempotency:{agent}:{key}"


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def _json_loads(s: str) -> Any:
    return json.loads(s)


def create_job(
    *,
    agent: str,
    run_input: Dict[str, Any],
    idempotency_key: Optional[str] = None,
    max_attempts: int = 3,
    job_ttl_seconds: int = 7 * 24 * 3600,
    idempotency_ttl_seconds: int = 24 * 3600,
) -> Tuple[str, bool]:
    r = get_redis()

    if idempotency_key:
        existing = r.get(_idempotency_key(agent, idempotency_key))
        if existing:
            return str(existing), True

    job_id = uuid.uuid4().hex
    now = time.time()
    record = JobRecord(
        job_id=job_id,
        agent=agent,
        status=JobStatus.queued,
        created_at_unix=now,
        attempts=0,
        max_attempts=max_attempts,
        run_input=run_input,
    )

    pipe = r.pipeline()
    pipe.hset(
        _key(job_id),
        mapping={
            "agent": record.agent,
            "status": record.status.value,
            "created_at_unix": str(record.created_at_unix),
            "started_at_unix": "",
            "finished_at_unix": "",
            "attempts": str(record.attempts),
            "max_attempts": str(record.max_attempts),
            "run_input_json": _json_dumps(record.run_input),
            "result_json": "",
            "error_json": "",
            "cancel_requested": "0",
        },
    )
    pipe.expire(_key(job_id), job_ttl_seconds)
    if idempotency_key:
        pipe.setex(_idempotency_key(agent, idempotency_key), idempotency_ttl_seconds, job_id)
    pipe.execute()

    return job_id, False


def get_job(job_id: str) -> Optional[JobRecord]:
    r = get_redis()
    data = r.hgetall(_key(job_id))
    if not data:
        return None

    def parse_float(raw: str) -> Optional[float]:
        raw = (raw or "").strip()
        if raw == "":
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    def parse_int(raw: str, default: int = 0) -> int:
        try:
            return int(raw)
        except Exception:
            return default

    error = None
    if data.get("error_json"):
        try:
            error = JobErrorInfo.model_validate(_json_loads(data["error_json"]))
        except Exception:
            error = JobErrorInfo(code="unknown_error", message="Failed to parse stored error.", details={})

    result = None
    if data.get("result_json"):
        try:
            result = _json_loads(data["result_json"])
        except Exception:
            result = {"_parse_error": True}

    return JobRecord(
        job_id=job_id,
        agent=data.get("agent", ""),
        status=JobStatus(data.get("status", JobStatus.failed.value)),
        created_at_unix=float(data.get("created_at_unix", "0") or "0"),
        started_at_unix=parse_float(data.get("started_at_unix", "")),
        finished_at_unix=parse_float(data.get("finished_at_unix", "")),
        attempts=parse_int(data.get("attempts", "0")),
        max_attempts=parse_int(data.get("max_attempts", "3"), 3),
        run_input=_json_loads(data.get("run_input_json", "{}") or "{}"),
        result=result,
        error=error,
        cancel_requested=(data.get("cancel_requested", "0") == "1"),
    )


def update_status(job_id: str, status: JobStatus, *, started: bool = False, finished: bool = False) -> None:
    r = get_redis()
    mapping: Dict[str, str] = {"status": status.value}
    now = str(time.time())
    if started:
        mapping["started_at_unix"] = now
    if finished:
        mapping["finished_at_unix"] = now
    r.hset(_key(job_id), mapping=mapping)


def increment_attempts(job_id: str) -> int:
    r = get_redis()
    return int(r.hincrby(_key(job_id), "attempts", 1))


def set_result(job_id: str, result: Dict[str, Any]) -> None:
    r = get_redis()
    r.hset(_key(job_id), mapping={"result_json": _json_dumps(result)})


def set_error(job_id: str, *, code: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
    r = get_redis()
    err = JobErrorInfo(code=code, message=message, details=details or {})
    r.hset(_key(job_id), mapping={"error_json": err.model_dump_json()})


def request_cancel(job_id: str) -> None:
    r = get_redis()
    r.hset(_key(job_id), mapping={"cancel_requested": "1"})
