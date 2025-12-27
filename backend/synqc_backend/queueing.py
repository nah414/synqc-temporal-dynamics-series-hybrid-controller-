from __future__ import annotations

import time
from typing import Optional

from .redis_client import get_redis


def _queue_key(queue_name: str) -> str:
    return f"synqc:q:{queue_name}"


def _delayed_key(queue_name: str) -> str:
    return f"synqc:q:{queue_name}:delayed"


def enqueue(queue_name: str, job_id: str) -> None:
    r = get_redis()
    r.lpush(_queue_key(queue_name), job_id)


def dequeue(queue_name: str, *, block_seconds: int = 5) -> Optional[str]:
    r = get_redis()
    item = r.brpop(_queue_key(queue_name), timeout=block_seconds)
    if not item:
        return None
    _key, job_id = item
    return str(job_id)


def schedule_delayed(queue_name: str, job_id: str, *, delay_seconds: float) -> None:
    r = get_redis()
    due = time.time() + float(delay_seconds)
    r.zadd(_delayed_key(queue_name), {job_id: due})


def pump_delayed(queue_name: str, *, limit: int = 100) -> int:
    r = get_redis()
    moved = 0
    now = time.time()
    delayed = _delayed_key(queue_name)
    q = _queue_key(queue_name)

    for _ in range(limit):
        popped = r.zpopmin(delayed, count=1)
        if not popped:
            break
        job_id, score = popped[0]
        if float(score) > now:
            r.zadd(delayed, {job_id: float(score)})
            break
        r.lpush(q, job_id)
        moved += 1

    return moved


def queue_depth(queue_name: str) -> int:
    r = get_redis()
    return int(r.llen(_queue_key(queue_name)))


def delayed_depth(queue_name: str) -> int:
    r = get_redis()
    return int(r.zcard(_delayed_key(queue_name)))
