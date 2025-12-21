from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any, Optional


class SqliteJobStore:
    """
    Minimal durable spool for jobs.
    - Survives process restart
    - Lets us requeue QUEUED jobs
    - Marks RUNNING jobs as "abandoned" on restart (safe default)
    """

    def __init__(self, path: str) -> None:
        self._path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")

        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
              job_id TEXT PRIMARY KEY,
              status TEXT NOT NULL,
              created_at REAL NOT NULL,
              started_at REAL,
              finished_at REAL,
              session_id TEXT,
              request_json TEXT NOT NULL,
              result_json TEXT,
              error TEXT,
              error_detail_json TEXT
            );
            """
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);")
        self._conn.commit()

    def upsert_queued(self, *, job_id: str, created_at: float, session_id: str, request: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO jobs (job_id, status, created_at, session_id, request_json)
                VALUES (?, 'queued', ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                  status='queued',
                  session_id=excluded.session_id,
                  request_json=excluded.request_json;
                """,
                (job_id, created_at, session_id, json.dumps(request, separators=(",", ":"))),
            )
            self._conn.commit()

    def mark_running(self, *, job_id: str, started_at: float) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE jobs SET status='running', started_at=? WHERE job_id=?;",
                (started_at, job_id),
            )
            self._conn.commit()

    def mark_finished(
        self,
        *,
        job_id: str,
        status: str,
        finished_at: float,
        result: Optional[dict[str, Any]] = None,
        error: Optional[str] = None,
        error_detail: Optional[dict[str, Any]] = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE jobs
                SET status=?,
                    finished_at=?,
                    result_json=?,
                    error=?,
                    error_detail_json=?
                WHERE job_id=?;
                """,
                (
                    status,
                    finished_at,
                    json.dumps(result, separators=(",", ":")) if result is not None else None,
                    error,
                    json.dumps(error_detail, separators=(",", ":")) if error_detail is not None else None,
                    job_id,
                ),
            )
            self._conn.commit()

    def load_incomplete(self, limit: int = 1000) -> list[dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT job_id, status, created_at, started_at, session_id, request_json
                FROM jobs
                WHERE status IN ('queued', 'running')
                ORDER BY created_at ASC
                LIMIT ?;
                """,
                (limit,),
            )
            rows = cur.fetchall()

        out: list[dict[str, Any]] = []
        for job_id, status, created_at, started_at, session_id, request_json in rows:
            out.append(
                {
                    "job_id": job_id,
                    "status": status,
                    "created_at": created_at,
                    "started_at": started_at,
                    "session_id": session_id or "",
                    "request": json.loads(request_json),
                }
            )
        return out

    def abandon_running_jobs(self) -> list[str]:
        """
        Mark running jobs as failed due to restart. Returns affected job_ids.
        """
        now = time.time()
        with self._lock:
            cur = self._conn.execute("SELECT job_id FROM jobs WHERE status='running';")
            ids = [r[0] for r in cur.fetchall()]

            for job_id in ids:
                self._conn.execute(
                    """
                    UPDATE jobs
                    SET status='failed',
                        finished_at=?,
                        error=?,
                        error_detail_json=?
                    WHERE job_id=? AND status='running';
                    """,
                    (
                        now,
                        "Abandoned due to worker restart",
                        json.dumps(
                            {
                                "code": "abandoned_by_restart",
                                "message": "Job was running when the process restarted; marked failed.",
                            },
                            separators=(",", ":"),
                        ),
                        job_id,
                    ),
                )
            self._conn.commit()
        return ids
