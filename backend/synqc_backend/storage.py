from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Dict, List, Optional

from .models import RunExperimentResponse, ExperimentSummary


class ExperimentStore:
    """In-memory store for experiment runs, with optional JSON persistence.

    This is intentionally simple. It keeps a bounded number of recent experiments
    and can optionally persist them to a JSON file for inspection.
    """

    def __init__(self, max_entries: int = 512, persist_path: Optional[Path] = None) -> None:
        self._max_entries = max_entries
        self._persist_path = persist_path
        self._lock = threading.Lock()
        self._runs: Dict[str, RunExperimentResponse] = {}
        self._persist_mtime: float | None = None
        self._last_persist_ok: bool = True

        if self._persist_path and self._persist_path.exists():
            try:
                data = json.loads(self._persist_path.read_text())
                for entry in data:
                    run = RunExperimentResponse.model_validate(entry)
                    self._runs[run.id] = run
                self._persist_mtime = self._persist_path.stat().st_mtime
            except Exception:
                # If the file is corrupt or incompatible, we ignore it.
                pass

    def add(self, run: RunExperimentResponse) -> None:
        with self._lock:
            self._runs[run.id] = run
            if len(self._runs) > self._max_entries:
                # drop oldest
                oldest_id = sorted(self._runs.values(), key=lambda r: r.created_at)[0].id
                self._runs.pop(oldest_id, None)
            self._persist()

    def get(self, run_id: str) -> Optional[RunExperimentResponse]:
        self._refresh_from_disk()
        with self._lock:
            return self._runs.get(run_id)

    def list_recent(self, limit: int = 50) -> List[ExperimentSummary]:
        self._refresh_from_disk()
        with self._lock:
            runs_sorted = sorted(self._runs.values(), key=lambda r: r.created_at, reverse=True)
            return [
                ExperimentSummary(
                    id=r.id,
                    preset=r.preset,
                    hardware_target=r.hardware_target,
                    kpis=r.kpis,
                    created_at=r.created_at,
                    shots=r.shots,
                    measurement=r.measurement,
                    noise=r.noise,
                    assumptions=r.assumptions,
                    qubits_used=r.qubits_used,
                    control_profile=r.control_profile,
                    physics_contract=r.physics_contract,
                    kpi_details=r.kpi_details,
                    kpi_observations=r.kpi_observations,
                    error_code=r.error_code,
                    error_message=r.error_message,
                    error_detail=r.error_detail,
                    action_hint=r.action_hint,
                )
                for r in runs_sorted[:limit]
            ]

    @property
    def is_empty(self) -> bool:
        self._refresh_from_disk()
        with self._lock:
            return len(self._runs) == 0

    def _persist(self) -> None:
        if not self._persist_path:
            return
        try:
            data = [r.model_dump(mode="json") for r in self._runs.values()]
            self._persist_path.write_text(json.dumps(data, indent=2))
            self._persist_mtime = self._persist_path.stat().st_mtime
            self._last_persist_ok = True
        except Exception:
            # Persistence failures should not kill the engine.
            self._last_persist_ok = False

    def _refresh_from_disk(self) -> None:
        if not self._persist_path:
            return
        try:
            mtime = self._persist_path.stat().st_mtime
        except FileNotFoundError:
            return
        if self._persist_mtime and mtime <= self._persist_mtime:
            return

        try:
            data = json.loads(self._persist_path.read_text())
            with self._lock:
                self._runs.clear()
                for entry in data:
                    run = RunExperimentResponse.model_validate(entry)
                    self._runs[run.id] = run
                self._persist_mtime = mtime
                self._last_persist_ok = True
        except Exception:
            # If reload fails, keep existing in-memory cache.
            self._last_persist_ok = False
            return

    def health_summary(self) -> Dict[str, object]:
        return {
            "backend": "file" if self._persist_path else "memory",
            "persist_path": str(self._persist_path) if self._persist_path else None,
            "persist_ok": self._last_persist_ok,
            "entries": len(self._runs),
            "last_modified": self._persist_mtime,
        }
