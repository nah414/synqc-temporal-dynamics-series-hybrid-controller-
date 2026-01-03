from __future__ import annotations

import argparse
import logging
import os
import socket
import time
import traceback
from multiprocessing import Process, Queue
from typing import Any, Dict, Optional

from .agents.base import AgentRunInput
from .agents.registry import get_agent, list_agents
from .job_store import JobStatus, get_job, increment_attempts, set_error, set_result, update_status
from .queueing import dequeue, pump_delayed, schedule_delayed
from .redis_client import get_redis


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _heartbeat_key(worker_id: str) -> str:
    return f"synqc:worker:{worker_id}"


def _write_heartbeat(worker_id: str, *, current_job: Optional[str] = None) -> None:
    r = get_redis()
    ttl = _env_int("SYNQC_WORKER_HEARTBEAT_TTL_SECONDS", 30)
    payload = {
        "worker_id": worker_id,
        "ts_unix": time.time(),
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
        "current_job": current_job,
        "agents": [a.name for a in list_agents()],
    }
    r.setex(_heartbeat_key(worker_id), ttl, str(payload))


def _run_agent_in_subprocess(agent_name: str, run_input: Dict[str, Any], out_q: Queue):
    try:
        agent = get_agent(agent_name)
        parsed = AgentRunInput.model_validate(run_input)
        out = agent.run(parsed)
        out_q.put({"ok": True, "result": out.model_dump()})
    except Exception as e:
        out_q.put({"ok": False, "error": {"type": type(e).__name__, "message": str(e), "traceback": traceback.format_exc()}})


def _is_transient_error(err_type: str, message: str) -> bool:
    transient_markers = ["Timeout", "timed out", "temporarily unavailable", "connection reset", "connection refused", "503", "429"]
    blob = f"{err_type}: {message}".lower()
    return any(m.lower() in blob for m in transient_markers)


def process_one(queue_name: str, worker_id: str, *, job_timeout_seconds: int) -> bool:
    pump_delayed(queue_name)

    job_id = dequeue(queue_name, block_seconds=5)
    if not job_id:
        _write_heartbeat(worker_id, current_job=None)
        return False

    _write_heartbeat(worker_id, current_job=job_id)

    job = get_job(job_id)
    if not job:
        return True

    if job.cancel_requested:
        update_status(job_id, JobStatus.cancelled, finished=True)
        return True

    update_status(job_id, JobStatus.running, started=True)
    attempt = increment_attempts(job_id)

    out_q: Queue = Queue()
    p = Process(target=_run_agent_in_subprocess, args=(job.agent, job.run_input, out_q), daemon=True)
    p.start()
    p.join(timeout=job_timeout_seconds)

    if p.is_alive():
        p.terminate()
        p.join(timeout=2)
        set_error(job_id, code="timeout", message=f"Job exceeded {job_timeout_seconds}s and was terminated.")
        update_status(job_id, JobStatus.failed, finished=True)
        return True

    if out_q.empty():
        set_error(job_id, code="worker_error", message="Worker finished without returning a result.")
        update_status(job_id, JobStatus.failed, finished=True)
        return True

    payload = out_q.get()
    if payload.get("ok"):
        set_result(job_id, payload["result"])
        update_status(job_id, JobStatus.succeeded, finished=True)
        return True

    err = payload.get("error", {})
    err_type = str(err.get("type", "Exception"))
    msg = str(err.get("message", "Unknown error"))
    tb = str(err.get("traceback", ""))

    max_attempts = int(job.max_attempts or 3)
    if attempt < max_attempts and _is_transient_error(err_type, msg):
        delay = min(60.0, float(2 ** (attempt - 1)))
        set_error(job_id, code="retry_scheduled", message=f"Transient error; retrying in {delay:.1f}s (attempt {attempt}/{max_attempts}).", details={"err_type": err_type, "message": msg})
        update_status(job_id, JobStatus.queued)
        schedule_delayed(queue_name, job_id, delay_seconds=delay)
        return True

    set_error(job_id, code="agent_failed", message=msg, details={"err_type": err_type, "traceback": tb})
    update_status(job_id, JobStatus.failed, finished=True)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="SynQc worker service (Redis queue).")
    parser.add_argument("--queue", default=os.environ.get("SYNQC_QUEUE_NAME", "default"))
    args = parser.parse_args()

    worker_id = os.environ.get("SYNQC_WORKER_ID") or f"{socket.gethostname()}-{os.getpid()}"
    job_timeout_seconds = _env_int("SYNQC_JOB_TIMEOUT_SECONDS", 60)

    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO)

    while True:
        try:
            did = process_one(args.queue, worker_id, job_timeout_seconds=job_timeout_seconds)
        except Exception:
            logger.exception("worker loop crashed; continuing after backoff")
            time.sleep(1.0)
            continue
        if not did:
            time.sleep(0.2)


if __name__ == "__main__":
    main()
