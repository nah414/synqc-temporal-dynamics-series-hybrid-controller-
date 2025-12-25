from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from typing import Optional

import redis

from .config import settings
from .jobs import JobStatus
from .models import ErrorCode, RunExperimentRequest, RunExperimentResponse
from .metrics_recorder import run_metrics


@dataclass
class QueuedRun:
    id: str
    request: RunExperimentRequest
    session_id: str
    created_at: float
    started_at: Optional[float] = None
    finished_at: Optional[float] = None


class RedisRunQueue:
    """Redis-backed run queue shared between the API and worker processes."""

    def __init__(self, url: str, *, max_workers: int) -> None:
        self._redis = redis.Redis.from_url(url, decode_responses=True)
        self._queue_key = "synqc:runq:pending"
        self._status_counts_key = "synqc:runq:status_counts"
        self._recent_key = "synqc:runq:recent"
        self._failure_code_key = "synqc:runq:failure_codes"
        self._failure_target_key = "synqc:runq:failures_by_target"
        self._max_workers = max_workers

    def health(self) -> dict:
        try:
            self._redis.ping()
            connected = True
        except Exception:
            connected = False
        stats = self.stats()
        return {
            "backend": "redis",
            "connected": connected,
            "queue_depth": stats.get("queued", 0),
            "oldest_queued_age_s": stats.get("oldest_queued_age_s"),
            "max_workers": self._max_workers,
        }

    def _job_key(self, job_id: str) -> str:
        return f"synqc:runq:job:{job_id}"

    def enqueue(self, req: RunExperimentRequest, session_id: str):
        job_id = str(uuid.uuid4())
        created_at = time.time()
        payload = {
            "status": JobStatus.QUEUED,
            "created_at": created_at,
            "session_id": session_id,
            "request_json": req.model_dump_json(),
        }
        pipe = self._redis.pipeline()
        pipe.hset(self._job_key(job_id), mapping=payload)
        pipe.rpush(self._queue_key, job_id)
        pipe.zadd(self._recent_key, {job_id: created_at})
        pipe.hincrby(self._status_counts_key, JobStatus.QUEUED, 1)
        pipe.execute()
        run_metrics.record_submission(req.hardware_target)
        return job_id, created_at

    def claim_next(self, timeout: int = 1) -> Optional[QueuedRun]:
        item = self._redis.blpop(self._queue_key, timeout=timeout)
        if not item:
            return None
        _q, job_id = item
        data = self._redis.hgetall(self._job_key(job_id))
        if not data:
            return None
        req_json = data.get("request_json")
        session_id = data.get("session_id", "")
        try:
            req = RunExperimentRequest.model_validate_json(req_json or "{}")
        except Exception:
            return None
        created_at = float(data.get("created_at", time.time()))
        return QueuedRun(id=job_id, request=req, session_id=session_id, created_at=created_at)

    def mark_running(self, job: QueuedRun) -> None:
        now = time.time()
        job.started_at = now
        self._redis.hset(
            self._job_key(job.id),
            mapping={"status": JobStatus.RUNNING, "started_at": now, "created_at": job.created_at},
        )
        pipe = self._redis.pipeline()
        pipe.hincrby(self._status_counts_key, JobStatus.QUEUED, -1)
        pipe.hincrby(self._status_counts_key, JobStatus.RUNNING, 1)
        pipe.execute()

    def complete_success(self, job: QueuedRun, result: RunExperimentResponse) -> None:
        now = time.time()
        job.finished_at = now
        payload = {
            "status": JobStatus.SUCCEEDED,
            "finished_at": now,
            "result_json": result.model_dump_json(),
            "created_at": job.created_at,
        }
        pipe = self._redis.pipeline()
        pipe.hset(self._job_key(job.id), mapping=payload)
        pipe.hincrby(self._status_counts_key, JobStatus.RUNNING, -1)
        pipe.hincrby(self._status_counts_key, JobStatus.SUCCEEDED, 1)
        pipe.execute()

    def complete_failure(
        self,
        job: QueuedRun,
        *,
        code: ErrorCode,
        message: str,
        action_hint: str | None = None,
        detail: dict | None = None,
    ) -> None:
        now = time.time()
        job.finished_at = now
        detail_payload = dict(detail or {})
        detail_payload.setdefault("code", code.value)
        detail_payload.setdefault("message", message)
        if action_hint:
            detail_payload.setdefault("action_hint", action_hint)

        payload = {
            "status": JobStatus.FAILED,
            "finished_at": now,
            "error": message,
            "error_code": code.value,
            "error_message": message,
            "error_detail": json.dumps(detail_payload, separators=(",", ":")),
            "action_hint": action_hint or "",
            "created_at": job.created_at,
        }
        pipe = self._redis.pipeline()
        pipe.hset(self._job_key(job.id), mapping=payload)
        pipe.hincrby(self._status_counts_key, JobStatus.RUNNING, -1)
        pipe.hincrby(self._status_counts_key, JobStatus.FAILED, 1)
        pipe.hincrby(self._failure_code_key, code.value, 1)
        if job.request.hardware_target:
            pipe.hincrby(self._failure_target_key, job.request.hardware_target, 1)
        pipe.execute()

    def get(self, job_id: str) -> Optional[dict]:
        data = self._redis.hgetall(self._job_key(job_id))
        if not data:
            return None
        result_json = data.get("result_json")
        result = None
        if result_json:
            try:
                result = RunExperimentResponse.model_validate_json(result_json)
            except Exception:
                result = None
        detail_json = data.get("error_detail")
        detail = None
        if detail_json:
            try:
                detail = json.loads(detail_json)
            except Exception:
                detail = None
        return {
            "id": job_id,
            "status": data.get("status", JobStatus.QUEUED),
            "created_at": float(data.get("created_at", 0) or 0),
            "started_at": _as_float(data.get("started_at")),
            "finished_at": _as_float(data.get("finished_at")),
            "error": data.get("error"),
            "error_code": data.get("error_code"),
            "error_message": data.get("error_message"),
            "error_detail": detail,
            "action_hint": data.get("action_hint"),
            "result": result,
        }

    def stats(self) -> dict:
        pipe = self._redis.pipeline()
        pipe.hgetall(self._status_counts_key)
        pipe.llen(self._queue_key)
        pipe.hgetall(self._failure_code_key)
        pipe.hgetall(self._failure_target_key)
        queued_oldest = self._redis.lindex(self._queue_key, 0)
        status_counts, pending_len, failure_codes, failure_targets = pipe.execute()

        queued = int(status_counts.get(JobStatus.QUEUED, 0) or 0)
        running = int(status_counts.get(JobStatus.RUNNING, 0) or 0)
        succeeded = int(status_counts.get(JobStatus.SUCCEEDED, 0) or 0)
        failed = int(status_counts.get(JobStatus.FAILED, 0) or 0)

        oldest_age = None
        if queued_oldest:
            created_at = self._redis.hget(self._job_key(queued_oldest), "created_at")
            if created_at:
                oldest_age = max(0.0, time.time() - float(created_at))

        return {
            "backend": "redis",
            "total": queued + running + succeeded + failed,
            "queued": queued,
            "running": running,
            "succeeded": succeeded,
            "failed": failed,
            "oldest_queued_age_s": oldest_age,
            "max_workers": self._max_workers,
            "failure_codes": {k: int(v) for k, v in (failure_codes or {}).items()},
            "failures_by_target": {k: int(v) for k, v in (failure_targets or {}).items()},
        }

    def shutdown(self, timeout: float | None = None) -> None:  # pragma: no cover - compatibility hook
        return


class EmbeddedRunQueue:
    """Adapter that exposes the JobQueue API when Redis is not configured."""

    def __init__(self, job_queue):
        self._queue = job_queue

    def enqueue(self, req: RunExperimentRequest, session_id: str):
        run_metrics.record_submission(req.hardware_target)
        record = self._queue.enqueue(req, session_id)
        return record.id, record.created_at

    def claim_next(self, timeout: int = 1) -> Optional[QueuedRun]:
        # Embedded mode never uses the external worker.
        return None

    def mark_running(self, job: QueuedRun) -> None:
        return None

    def complete_success(self, job: QueuedRun, result: RunExperimentResponse) -> None:
        return None

    def complete_failure(
        self,
        job: QueuedRun,
        *,
        code: ErrorCode,
        message: str,
        action_hint: str | None = None,
        detail: dict | None = None,
    ) -> None:
        return None

    def get(self, job_id: str):
        record = self._queue.get(job_id)
        if not record:
            return None
        return {
            "id": record.id,
            "status": record.status,
            "created_at": record.created_at,
            "started_at": record.started_at,
            "finished_at": record.finished_at,
            "error": record.error,
            "error_code": record.error_code.value if record.error_code else None,
            "error_message": record.error_message,
            "error_detail": record.error_detail,
            "action_hint": record.action_hint,
            "result": record.result,
        }

    def stats(self) -> dict:
        stats = self._queue.stats()
        stats["backend"] = "embedded"
        stats.setdefault("failures_by_target", {})
        return stats

    def health(self) -> dict:
        stats = self.stats()
        return {
            "backend": "embedded",
            "connected": True,
            "queue_depth": stats.get("queued", 0),
            "oldest_queued_age_s": stats.get("oldest_queued_age_s"),
            "max_workers": stats.get("max_workers"),
        }

    def shutdown(self, timeout: float | None = None) -> None:
        return self._queue.shutdown(timeout=timeout)


def _as_float(val: str | None) -> Optional[float]:
    try:
        if val is None:
            return None
        return float(val)
    except Exception:
        return None


def build_run_queue(job_queue) -> object:
    if settings.redis_url:
        return RedisRunQueue(settings.redis_url, max_workers=settings.worker_pool_size)
    return EmbeddedRunQueue(job_queue)
