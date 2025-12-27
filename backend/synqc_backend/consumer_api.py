from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from .agents.base import AgentRunInput, AgentSelfTestResult
from .agents.registry import get_agent, list_agents
from .job_store import JobStatus, create_job, get_job, request_cancel
from .queueing import delayed_depth, enqueue, queue_depth
from .redis_client import get_redis

router = APIRouter(tags=["consumer"])


class JobSubmitResponse(BaseModel):
    job_id: str
    reused_existing: bool = False
    status: JobStatus


class JobPublic(BaseModel):
    job_id: str
    agent: str
    status: JobStatus
    created_at_unix: float
    started_at_unix: Optional[float] = None
    finished_at_unix: Optional[float] = None
    attempts: int
    max_attempts: int
    cancel_requested: bool = False
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@router.get("/agents")
def agents_list():
    return {"agents": [a.model_dump() for a in list_agents()]}


@router.get("/agents/health")
def agents_health():
    results: list[dict[str, Any]] = []
    for meta in list_agents():
        try:
            agent = get_agent(meta.name)
            res = agent.self_test()
            results.append(res.model_dump())
        except Exception as e:
            results.append(AgentSelfTestResult(agent=meta.name, ok=False, details={"error": str(e)}).model_dump())
    return {"results": results}


@router.post("/agents/{agent_name}/run", response_model=JobSubmitResponse)
def run_agent(
    agent_name: str,
    run_input: AgentRunInput,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    queue_name: str = Query(default="default"),
    wait: bool = Query(default=False),
    timeout_seconds: int = Query(default=20, ge=1, le=600),
):
    try:
        _ = get_agent(agent_name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

    job_id, reused = create_job(
        agent=agent_name,
        run_input=run_input.model_dump(),
        idempotency_key=idempotency_key,
        max_attempts=_env_int("SYNQC_JOB_MAX_ATTEMPTS", 3),
    )
    if not reused:
        enqueue(queue_name, job_id)

    if not wait:
        return JobSubmitResponse(job_id=job_id, reused_existing=reused, status=JobStatus.queued)

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        job = get_job(job_id)
        if not job:
            break
        if job.status in {JobStatus.succeeded, JobStatus.failed, JobStatus.cancelled}:
            return JobSubmitResponse(job_id=job_id, reused_existing=reused, status=job.status)
        time.sleep(0.25)

    return JobSubmitResponse(job_id=job_id, reused_existing=reused, status=JobStatus.running)


@router.get("/jobs/{job_id}", response_model=JobPublic)
def job_status(job_id: str, include_result: bool = Query(default=True)):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Unknown job id")

    error = job.error.model_dump() if job.error else None
    result = job.result if include_result else None
    return JobPublic(
        job_id=job.job_id,
        agent=job.agent,
        status=job.status,
        created_at_unix=job.created_at_unix,
        started_at_unix=job.started_at_unix,
        finished_at_unix=job.finished_at_unix,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        cancel_requested=job.cancel_requested,
        result=result,
        error=error,
    )


@router.post("/jobs/{job_id}/cancel")
def job_cancel(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Unknown job id")
    request_cancel(job_id)
    return {"ok": True, "job_id": job_id}


@router.get("/health/extended")
def health_extended(queue_name: str = Query(default="default")):
    r = get_redis()
    redis_ok = False
    try:
        redis_ok = (r.ping() is True)
    except Exception:
        redis_ok = False

    return {
        "ok": True,
        "redis_ok": redis_ok,
        "queue": {
            "name": queue_name,
            "depth": queue_depth(queue_name),
            "delayed_depth": delayed_depth(queue_name),
        },
    }
