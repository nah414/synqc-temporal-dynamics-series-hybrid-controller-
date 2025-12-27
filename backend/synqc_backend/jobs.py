from __future__ import annotations

import inspect
import logging
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, wait
from threading import Event, Lock, Timer
from typing import Callable, Dict, Optional

from .engine import BudgetExceeded
try:  # pragma: no cover - optional persistence
    from .job_store import SqliteJobStore  # type: ignore
except Exception:  # pragma: no cover - allow runtime without sqlite spool
    SqliteJobStore = None  # type: ignore
from .provider_clients import ProviderClientError
from .models import (
    ErrorCode,
    ExperimentStatus,
    KpiBundle,
    RunExperimentRequest,
    RunExperimentResponse,
    WorkflowStep,
)
from .storage import ExperimentStore
from .metrics_recorder import run_metrics


logger = logging.getLogger(__name__)


class JobStatus(str):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class JobRecord:
    def __init__(self, job_id: str, request: RunExperimentRequest) -> None:
        self.id = job_id
        self.request = request
        self.status = JobStatus.QUEUED
        self.created_at = time.time()
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self.result = None
        self.error: str | None = None
        self.error_detail: dict | None = None
        self.error_code: ErrorCode | None = None
        self.error_message: str | None = None
        self.action_hint: str | None = None


def _model_dump(obj) -> dict:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    raise TypeError(f"Cannot serialize type: {type(obj)}")


def _model_validate(model_cls, data: dict):
    if hasattr(model_cls, "model_validate"):
        return model_cls.model_validate(data)
    return model_cls(**data)


class JobQueue:
    """
    Thread-pool-backed job queue with:
      - durable spool (sqlite) so QUEUED jobs survive restart
      - soft timeout (mark failed + set cancel flag)
      - best-effort cancellation (cancel flag + future.cancel if not started)
    """

    def __init__(
        self,
        worker_fn: Callable[..., object],
        max_workers: int,
        *,
        store: ExperimentStore | None = None,
        persistence_path: str | None = None,
        job_timeout_seconds: int = 0,
        max_pending: int = 1000,
        rehydrate: bool = True,
    ) -> None:
        self._worker_fn = worker_fn
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

        self._jobs: Dict[str, JobRecord] = {}
        self._futures: Dict[str, Future] = {}
        self._cancel_events: Dict[str, Event] = {}
        self._timers: Dict[str, Timer] = {}
        self._failure_counts: Dict[str, int] = {}

        self._lock = Lock()
        self._store = store

        self._job_timeout_seconds = int(job_timeout_seconds)
        self._max_pending = int(max_pending)
        self._shutdown = False

        self._persist: SqliteJobStore | None = None
        if persistence_path and SqliteJobStore:
            self._persist = SqliteJobStore(persistence_path)

        # Cooperative cancel support: if worker_fn accepts a 3rd arg, pass cancel_event
        sig = inspect.signature(worker_fn)
        self._supports_cancel_event = len(sig.parameters) >= 3

        if self._persist and rehydrate:
            # Mark "running" jobs as failed (safe default)
            self._persist.abandon_running_jobs()
            # Requeue queued jobs
            for row in self._persist.load_incomplete():
                if row["status"] != JobStatus.QUEUED:
                    continue
                req = _model_validate(RunExperimentRequest, row["request"])
                record = JobRecord(job_id=row["job_id"], request=req)
                record.created_at = float(row["created_at"])
                # keep queued; executor will pick it up
                self._rehydrate_enqueue(record, session_id=row["session_id"])

    def _rehydrate_enqueue(self, record: JobRecord, session_id: str) -> None:
        cancel_event = Event()
        with self._lock:
            self._jobs[record.id] = record
            self._cancel_events[record.id] = cancel_event
            self._futures[record.id] = self._executor.submit(self._run_job, record, session_id, cancel_event)

    def enqueue(self, req: RunExperimentRequest, session_id: str) -> JobRecord:
        with self._lock:
            if self._shutdown:
                raise RuntimeError("JobQueue is shutting down; cannot enqueue new jobs")
            # pending-ish = queued + running
            active = sum(1 for r in self._jobs.values() if r.status in (JobStatus.QUEUED, JobStatus.RUNNING))
            if active >= self._max_pending:
                raise RuntimeError("Queue is full; try again later")

        job_id = str(uuid.uuid4())
        record = JobRecord(job_id=job_id, request=req)

        cancel_event = Event()

        with self._lock:
            self._jobs[job_id] = record
            self._cancel_events[job_id] = cancel_event
            self._futures.pop(job_id, None)

        if self._persist:
            self._persist.upsert_queued(
                job_id=job_id,
                created_at=record.created_at,
                session_id=session_id,
                request=_model_dump(req),
            )

        future = self._executor.submit(self._run_job, record, session_id, cancel_event)
        with self._lock:
            self._futures[job_id] = future

        return record

    def cancel(self, job_id: str, reason: str = "Cancelled") -> bool:
        """
        Best-effort cancel:
          - If not started: future.cancel() should work.
          - If running: we set cancel_event (cooperative only), and mark record failed immediately.
        """
        now = time.time()
        with self._lock:
            record = self._jobs.get(job_id)
            if not record:
                return False
            if record.status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
                return False

            record.error = reason
            record.error_code = ErrorCode.CANCELLED
            record.error_message = reason
            record.action_hint = "Retry the run or clear the queue if the workflow is stuck."
            record.error_detail = {
                "code": record.error_code.value if record.error_code else None,
                "message": record.error_message,
                "action_hint": record.action_hint,
            }
            record.finished_at = now
            record.status = JobStatus.FAILED
            code = record.error_code.value if record.error_code else "UNKNOWN"
            self._failure_counts[code] = self._failure_counts.get(code, 0) + 1

            ev = self._cancel_events.get(job_id)
            if ev:
                ev.set()

            fut = self._futures.get(job_id)
            if fut:
                fut.cancel()

        if self._persist:
            self._persist.mark_finished(
                job_id=job_id,
                status=JobStatus.FAILED,
                finished_at=now,
                error=record.error,
                error_detail=record.error_detail,
            )
        self._persist_failure(record)
        return True

    def shutdown(self, timeout: float | None = None) -> None:
        """
        Graceful shutdown:
          - stop accepting new jobs
          - cancel futures that haven't started (so they remain QUEUED in sqlite and can rehydrate later)
          - wait up to timeout for running jobs
        """
        with self._lock:
            self._shutdown = True
            futures = list(self._futures.values())
            # signal cooperative cancellation to running tasks (if supported)
            for ev in self._cancel_events.values():
                ev.set()

        # cancel_futures=True prevents new queued tasks from starting
        self._executor.shutdown(wait=False, cancel_futures=True)

        if timeout is None:
            wait(futures)
            return
        wait(futures, timeout=timeout)

    def get(self, job_id: str) -> Optional[JobRecord]:
        with self._lock:
            return self._jobs.get(job_id)

    def _timeout_job(self, job_id: str) -> None:
        now = time.time()
        with self._lock:
            record = self._jobs.get(job_id)
            if not record:
                return
            if record.status != JobStatus.RUNNING:
                return

            record.error = "Timed out"
            record.error_code = ErrorCode.TIMEOUT
            record.error_message = "Job exceeded timeout"
            record.action_hint = "Try again with a smaller shot budget or fewer queued jobs."
            record.error_detail = {
                "code": record.error_code.value if record.error_code else None,
                "message": record.error_message,
                "timeout_seconds": self._job_timeout_seconds,
                "action_hint": record.action_hint,
            }
            record.status = JobStatus.FAILED
            record.finished_at = now
            code = record.error_code.value if record.error_code else "UNKNOWN"
            self._failure_counts[code] = self._failure_counts.get(code, 0) + 1

            ev = self._cancel_events.get(job_id)
            if ev:
                ev.set()

            fut = self._futures.get(job_id)
            if fut:
                fut.cancel()

        if self._persist:
            self._persist.mark_finished(
                job_id=job_id,
                status=JobStatus.FAILED,
                finished_at=now,
                error=record.error,
                error_detail=record.error_detail,
            )
        self._persist_failure(record)

    def _run_job(self, record: JobRecord, session_id: str, cancel_event: Event | None = None) -> None:
        # transition -> RUNNING
        if cancel_event is None:
            cancel_event = Event()
        with self._lock:
            # If someone cancelled before we started, exit fast.
            if record.status == JobStatus.FAILED:
                return
            record.status = JobStatus.RUNNING
            record.started_at = time.time()

        if self._persist:
            self._persist.mark_running(job_id=record.id, started_at=record.started_at or time.time())

        # start timeout timer (from *start*, not from enqueue)
        timer: Timer | None = None
        if self._job_timeout_seconds > 0:
            timer = Timer(self._job_timeout_seconds, self._timeout_job, args=(record.id,))
            timer.daemon = True
            with self._lock:
                self._timers[record.id] = timer
            timer.start()

        try:
            # cooperative cancel: only works if worker_fn checks cancel_event
            if self._supports_cancel_event:
                result = self._worker_fn(record.request, session_id, cancel_event)
            else:
                result = self._worker_fn(record.request, session_id)

            with self._lock:
                # If timeout/cancel already marked it failed, do not overwrite.
                if record.status != JobStatus.RUNNING:
                    return
                record.result = result
                record.status = JobStatus.SUCCEEDED

            if self._persist:
                # Store minimal result metadata; experiment storage handles full result history.
                self._persist.mark_finished(
                    job_id=record.id,
                    status=JobStatus.SUCCEEDED,
                    finished_at=time.time(),
                    result=_model_dump(result) if hasattr(result, "model_dump") or hasattr(result, "dict") else None,
                )

        except BudgetExceeded as exc:
            self._fail_record(
                record,
                code=ErrorCode.BUDGET_EXHAUSTED,
                message=str(exc),
                extra={"remaining": getattr(exc, "remaining", None)},
                action_hint="Lower the shot budget or wait for the session budget to reset.",
            )
        except ProviderClientError as exc:
            self._fail_record(
                record,
                code=getattr(exc, "code", ErrorCode.PROVIDER_ERROR),
                message=str(exc),
                action_hint=getattr(exc, "action_hint", None)
                or "Check provider credentials or select a simulator backend.",
                extra=getattr(exc, "detail", None),
            )
        except ValueError as exc:
            self._fail_record(
                record,
                code=ErrorCode.INVALID_REQUEST,
                message=str(exc),
                action_hint="Verify the request payload and try again.",
            )
        except Exception as exc:  # noqa: BLE001
            self._fail_record(
                record,
                code=ErrorCode.INTERNAL_ERROR,
                message=str(exc),
                action_hint="Check backend logs for details and retry after remediation.",
            )
        finally:
            # cleanup timer
            if timer:
                timer.cancel()
            with self._lock:
                self._timers.pop(record.id, None)
                if record.finished_at is None and record.status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
                    record.finished_at = time.time()

            self._observe_metrics(record)

    def _fail_record(
        self,
        record: JobRecord,
        *,
        code: ErrorCode,
        message: str,
        extra: dict | None = None,
        action_hint: str | None = None,
    ) -> None:
        now = time.time()
        detail = {"code": code.value, "message": message}
        if extra:
            detail.update(extra)
        if action_hint:
            detail["action_hint"] = action_hint

        with self._lock:
            # If timeout/cancel already marked it failed, do not overwrite.
            if record.status != JobStatus.RUNNING:
                return
            record.error = message
            record.error_code = code
            record.error_message = message
            record.action_hint = action_hint
            record.error_detail = detail
            record.status = JobStatus.FAILED
            record.finished_at = now
            self._failure_counts[code.value] = self._failure_counts.get(code.value, 0) + 1

        logger.error(
            "Job failed",
            extra={
                "job_id": record.id,
                "error_code": code.value,
                "error_message": message,
                "extra": extra or {},
            },
        )

        if self._persist:
            self._persist.mark_finished(
                job_id=record.id,
                status=JobStatus.FAILED,
                finished_at=now,
                error=record.error,
                error_detail=record.error_detail,
            )

        self._persist_failure(record)

    def _observe_metrics(self, record: JobRecord) -> None:
        target = record.request.hardware_target or "unknown"
        started = record.started_at or record.created_at or time.time()
        finished = record.finished_at or time.time()
        latency = max(0.0, finished - started)

        if record.status == JobStatus.SUCCEEDED:
            run_metrics.record_success(target, latency)
        elif record.status == JobStatus.FAILED:
            code = record.error_code.value if record.error_code else "unknown"
            run_metrics.record_failure(target, code, latency)

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
            qubits_used=0,
            notes=req.notes,
            control_profile=req.control_overrides,
            error_code=record.error_code,
            error_message=record.error_message,
            error_detail=record.error_detail,
            action_hint=record.action_hint,
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
            # persistence failures should never crash workers
            pass

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
                "max_pending": self._max_pending,
                "job_timeout_seconds": self._job_timeout_seconds,
                "failure_codes": dict(self._failure_counts),
            }
