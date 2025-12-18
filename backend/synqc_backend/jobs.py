from __future__ import annotations

import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, wait
from threading import Lock
from typing import Callable, Dict, Optional

from .engine import BudgetExceeded
from .models import (
    ExperimentStatus,
    KpiBundle,
    RunExperimentRequest,
    RunExperimentResponse,
    WorkflowStep,
)
from .storage import ExperimentStore


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
        self.error_detail: dict | None = None


class JobQueue:
    """Simple thread-pool-backed job queue for experiment execution."""

    def __init__(
        self,
        worker_fn: Callable[[RunExperimentRequest, str], object],
        max_workers: int,
        store: ExperimentStore | None = None,
    ) -> None:
        self._worker_fn = worker_fn
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._jobs: Dict[str, JobRecord] = {}
        self._futures: Dict[str, Future] = {}
        self._lock = Lock()
        self._store = store

    def enqueue(self, req: RunExperimentRequest, session_id: str) -> JobRecord:
        job_id = str(uuid.uuid4())
        record = JobRecord(job_id=job_id, request=req)
        with self._lock:
            self._jobs[job_id] = record
            self._futures.pop(job_id, None)

        future = self._executor.submit(self._run_job, record, session_id)
        with self._lock:
            self._futures[job_id] = future
        return record

    def shutdown(self, timeout: float | None = None) -> None:
        """Attempt a graceful shutdown so in-flight jobs can finish."""

        futures: list[Future]
        with self._lock:
            futures = list(self._futures.values())

        if timeout is None:
            self._executor.shutdown(wait=True)
            return

        # Stop accepting new tasks, then wait up to timeout for currently tracked tasks.
        self._executor.shutdown(wait=False)
        wait(futures, timeout=timeout)

    def _persist_failure(self, record: JobRecord) -> None:
        if not self._store:
            return
        req = record.request
        kpis = KpiBundle(
            fidelity=None,
            latency_us=None,
            backaction=None,
            shots_used=0,
            shot_budget=req.shot_budget or 0,
            status=ExperimentStatus.FAIL,
        )
        run = RunExperimentResponse(
            id=record.id,
            preset=req.preset,
            hardware_target=req.hardware_target,
            kpis=kpis,
            created_at=record.finished_at or time.time(),
            notes=req.notes,
            control_profile=req.control_overrides,
            error_detail=record.error_detail,
            workflow_trace=[
                WorkflowStep(
                    id="ingest",
                    label="Ingest",
                    description="Submission rejected before execution; see error_detail.",
                    percent_complete=20,
                    dwell_ms=300,
                ),
                WorkflowStep(
                    id="commit",
                    label="Guardrail",
                    description="Budget/validation guardrail halted the workflow.",
                    percent_complete=100,
                    dwell_ms=300,
                ),
            ],
        )
        try:
            self._store.add(run)
        except Exception:
            # Persistence failures should not crash the worker.
            pass

    def _run_job(self, record: JobRecord, session_id: str) -> None:
        with self._lock:
            record.status = JobStatus.RUNNING
            record.started_at = time.time()
        try:
            record.result = self._worker_fn(record.request, session_id)
            with self._lock:
                record.status = JobStatus.SUCCEEDED
        except BudgetExceeded as exc:
            record.error = str(exc)
            record.error_detail = {
                "code": "session_budget_exhausted",
                "message": str(exc),
                "remaining": getattr(exc, "remaining", None),
            }
            with self._lock:
                record.status = JobStatus.FAILED
        except ValueError as exc:
            record.error = str(exc)
            record.error_detail = {
                "code": "invalid_request",
                "message": str(exc),
            }
            with self._lock:
                record.status = JobStatus.FAILED
        except Exception as exc:  # noqa: BLE001 - we capture and expose errors
            record.error = str(exc)
            record.error_detail = {
                "code": "internal_error",
                "message": str(exc),
            }
            with self._lock:
                record.status = JobStatus.FAILED
        finally:
            with self._lock:
                record.finished_at = time.time()
            if record.status == JobStatus.FAILED:
                self._persist_failure(record)

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
