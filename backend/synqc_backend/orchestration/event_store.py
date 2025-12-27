from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock
from typing import Any, Dict, List


class EventStore:
    """Thread-safe in-memory event store keyed by experiment id."""

    def __init__(self) -> None:
        self._events: Dict[str, List[dict[str, Any]]] = defaultdict(list)
        self._lock = Lock()

    def append(self, experiment_id: str, event: Dict[str, Any]) -> dict[str, Any]:
        payload = dict(event)
        payload.setdefault("timestamp", time.time())
        with self._lock:
            self._events[experiment_id].append(payload)
        return payload

    def list(self, experiment_id: str, *, limit: int = 300) -> List[dict[str, Any]]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        with self._lock:
            items = list(self._events.get(experiment_id, ()))
        if limit >= len(items):
            return items
        return items[-limit:]

    def clear(self, experiment_id: str) -> None:
        with self._lock:
            self._events.pop(experiment_id, None)


def get_event_store() -> EventStore:
    """Return the process-wide event store."""

    global _EVENT_STORE  # type: ignore[global-variable-not-assigned]
    try:
        return _EVENT_STORE
    except NameError:
        _EVENT_STORE = EventStore()
        return _EVENT_STORE
