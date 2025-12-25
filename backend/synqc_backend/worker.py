from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path
from time import sleep

from .budget import BudgetTracker
from .config import settings
from .control_profiles import ControlProfileStore
from .engine import BudgetExceeded, SynQcEngine
from .logging_utils import configure_json_logging, get_logger, log_context
from .metrics_recorder import run_metrics
from .models import ErrorCode
from .provider_clients import ProviderClientError
from .qubit_usage import SessionQubitTracker
from .run_queue import QueuedRun, RedisRunQueue
from .storage import ExperimentStore

configure_json_logging()
logger = get_logger(__name__)


def _execute_with_timeout(fn, timeout_seconds: int, *args):
    if timeout_seconds <= 0:
        return fn(*args)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fn, *args)
        return future.result(timeout=timeout_seconds)


def _build_engine() -> SynQcEngine:
    persist_path = Path("./synqc_experiments.json")
    store = ExperimentStore(max_entries=512, persist_path=persist_path)
    budget_tracker = BudgetTracker(
        redis_url=settings.redis_url,
        session_ttl_seconds=settings.session_budget_ttl_seconds,
        fail_open_on_redis_error=settings.budget_fail_open_on_redis_error,
    )
    control_store = ControlProfileStore(persist_path=Path("./synqc_controls.json"))
    qubit_tracker = SessionQubitTracker(ttl_seconds=settings.session_budget_ttl_seconds)
    return SynQcEngine(
        store=store,
        budget_tracker=budget_tracker,
        control_store=control_store,
        usage_tracker=qubit_tracker,
    )


def _handle_failure(
    queue: RedisRunQueue,
    job: QueuedRun,
    code: ErrorCode,
    message: str,
    *,
    action_hint: str | None = None,
    detail: dict | None = None,
) -> None:
    finished_at = time.time()
    job.finished_at = finished_at
    latency = max(0.0, finished_at - (job.started_at or job.created_at))
    run_metrics.record_failure(job.request.hardware_target, code.value, latency)

    logger.error(
        "Run failed",
        extra={
            "job_id": job.id,
            "experiment_id": job.id,
            "hardware_target": job.request.hardware_target,
            "session_id": job.session_id,
            "error_code": code.value,
            "error_message": message,
        },
    )
    queue.complete_failure(job, code=code, message=message, action_hint=action_hint, detail=detail)


def _process_job(engine: SynQcEngine, queue: RedisRunQueue, job: QueuedRun) -> None:
    queue.mark_running(job)
    start_time = job.started_at or time.time()
    with log_context(
        request_id=job.id,
        experiment_id=job.id,
        hardware_target=job.request.hardware_target,
        session_id=job.session_id,
    ):
        try:
            result = _execute_with_timeout(
                engine.run_experiment, settings.job_timeout_seconds, job.request, job.session_id
            )
            finished = time.time()
            job.finished_at = finished
            latency = max(0.0, finished - start_time)
            run_metrics.record_success(job.request.hardware_target, latency)
            queue.complete_success(job, result=result)
            logger.info(
                "Run succeeded",
                extra={
                    "job_id": job.id,
                    "experiment_id": job.id,
                    "hardware_target": job.request.hardware_target,
                    "latency_s": latency,
                },
            )
        except TimeoutError:
            _handle_failure(
                queue,
                job,
                ErrorCode.TIMEOUT,
                "Job exceeded timeout",
                action_hint="Reduce shot budget or wait for fewer concurrent jobs.",
                detail={"timeout_seconds": settings.job_timeout_seconds},
            )
        except BudgetExceeded as exc:
            _handle_failure(
                queue,
                job,
                ErrorCode.BUDGET_EXHAUSTED,
                str(exc),
                action_hint="Lower the shot budget or wait for the session budget to reset.",
                detail={"remaining": getattr(exc, "remaining", None)},
            )
        except ProviderClientError as exc:
            _handle_failure(
                queue,
                job,
                exc.code if hasattr(exc, "code") else ErrorCode.PROVIDER_ERROR,
                str(exc),
                action_hint=getattr(exc, "action_hint", None),
                detail=getattr(exc, "detail", None),
            )
        except ValueError as exc:
            _handle_failure(
                queue,
                job,
                ErrorCode.INVALID_REQUEST,
                str(exc),
                action_hint="Verify the request payload and try again.",
            )
        except Exception as exc:  # noqa: BLE001
            _handle_failure(
                queue,
                job,
                ErrorCode.INTERNAL_ERROR,
                str(exc),
                action_hint="Check worker logs for details and retry after remediation.",
            )


def main() -> None:
    if not settings.redis_url:
        raise RuntimeError("Redis URL is required for the dedicated worker")

    engine = _build_engine()
    queue = RedisRunQueue(settings.redis_url, max_workers=settings.worker_pool_size)

    logger.info("synqc-worker ready", extra={"redis_url": settings.redis_url, "max_workers": settings.worker_pool_size})
    try:
        while True:
            job = queue.claim_next(timeout=5)
            if not job:
                continue
            _process_job(engine, queue, job)
    except KeyboardInterrupt:  # pragma: no cover - manual shutdown
        logger.info("Worker stopping...")
        return
    except Exception:
        logger.exception("Worker crashed")
        raise


if __name__ == "__main__":
    main()
