from __future__ import annotations

import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from typing import Callable, Dict, Optional

from .models import RunExperimentRequest


class JobStatus(str):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class JobRecord:
    def __init__(self, job_id: str, request: RunExperimentRequest) -> None:
        self.id = job_id
        self.request = request
        self.status: JobStatus = JobStatus.QUEUED
        self.created_at = time.time()
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self.result = None
        self.error: str | None = None


class JobQueue:
    """Simple thread-pool-backed job queue for experiment execution."""

    def __init__(self, worker_fn: Callable[[RunExperimentRequest, str], object], max_workers: int) -> None:
        self._worker_fn = worker_fn
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._jobs: Dict[str, JobRecord] = {}
        self._futures: Dict[str, Future] = {}
        self._lock = Lock()

    def enqueue(self, req: RunExperimentRequest, session_id: str) -> JobRecord:
        job_id = str(uuid.uuid4())
        record = JobRecord(job_id=job_id, request=req)
        with self._lock:
            self._jobs[job_id] = record

        future = self._executor.submit(self._run_job, record, session_id)
        with self._lock:
            self._futures[job_id] = future
        return record

    def shutdown(self, timeout: float | None = None) -> None:
        """Attempt a graceful shutdown so in-flight jobs can finish."""

        self._executor.shutdown(wait=True, timeout=timeout)

    def _run_job(self, record: JobRecord, session_id: str) -> None:
        with self._lock:
            record.status = JobStatus.RUNNING
            record.started_at = time.time()
        try:
            record.result = self._worker_fn(record.request, session_id)
            with self._lock:
                record.status = JobStatus.SUCCEEDED
        except Exception as exc:  # noqa: BLE001 - we capture and expose errors
            record.error = str(exc)
            with self._lock:
                record.status = JobStatus.FAILED
        finally:
            with self._lock:
                record.finished_at = time.time()

    def get(self, job_id: str) -> Optional[JobRecord]:
        with self._lock:
            return self._jobs.get(job_id)

    def stats(self) -> Dict[str, object]:
        """Return queue depth and status counts for health/metrics."""

        with self._lock:
            counts: Dict[str, int] = {
                JobStatus.QUEUED: 0,
                JobStatus.RUNNING: 0,
                JobStatus.SUCCEEDED: 0,
                JobStatus.FAILED: 0,
            }

            for record in self._jobs.values():
                counts[record.status] = counts.get(record.status, 0) + 1

            oldest_queued_age = None
            now = time.time()
            for record in self._jobs.values():
                if record.status == JobStatus.QUEUED:
                    age = now - record.created_at
                    if oldest_queued_age is None or age > oldest_queued_age:
                        oldest_queued_age = age

            return {
                "total": len(self._jobs),
                "queued": counts[JobStatus.QUEUED],
                "running": counts[JobStatus.RUNNING],
                "succeeded": counts[JobStatus.SUCCEEDED],
                "failed": counts[JobStatus.FAILED],
                "oldest_queued_age_s": oldest_queued_age,
                "max_workers": self._executor._max_workers,
            }
