from __future__ import annotations

import contextlib
import json
import os
import queue
import sqlite3
import threading
import time
from typing import Any, Iterator, Optional

from .security import (
    hash_password,
    make_prefixed_token,
    normalize_email,
    now_ts,
    sha256_hex,
    verify_password,
)


class AuthStore:
    """
    MVP-grade auth store backed by SQLite.

    Tables:
      - users
      - sessions (server-side sessions for cookie auth)
      - api_tokens (scoped tokens for automation)
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._pool_size = 4
        self._pool: queue.Queue[sqlite3.Connection] = queue.Queue(maxsize=self._pool_size)
        for _ in range(self._pool_size):
            self._pool.put(self._connect_new())
        self._token_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._token_cache_ttl_seconds = 30.0
        self._init_db()

    @property
    def db_path(self) -> str:
        return self._db_path

    def _connect_new(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(os.path.abspath(self._db_path)) or ".", exist_ok=True)
        conn = sqlite3.connect(self._db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        # WAL improves concurrency for many readers
        try:
            conn.execute("PRAGMA journal_mode = WAL")
        except sqlite3.DatabaseError:
            pass
        return conn

    @contextlib.contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = self._pool.get()
        try:
            yield conn
        finally:
            self._pool.put(conn)

    def _init_db(self) -> None:
        with self._lock, self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    is_admin INTEGER NOT NULL DEFAULT 0,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    csrf_token TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    last_seen_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    revoked_at REAL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);

                CREATE TABLE IF NOT EXISTS api_tokens (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    label TEXT,
                    prefix TEXT NOT NULL,
                    token_hash TEXT NOT NULL,
                    scopes TEXT NOT NULL, -- JSON list
                    created_at REAL NOT NULL,
                    expires_at REAL,
                    last_used_at REAL,
                    revoked_at REAL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_api_tokens_user_id ON api_tokens(user_id);

                """
            )

    # -------------------------
    # Users
    # -------------------------
    def user_count(self) -> int:
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
            return int(row["n"]) if row else 0

    def get_user_by_email(self, email: str) -> Optional[dict[str, Any]]:
        email_n = normalize_email(email)
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email_n,)).fetchone()
            return dict(row) if row else None

    def get_user_by_id(self, user_id: int) -> Optional[dict[str, Any]]:
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()
            return dict(row) if row else None

    def create_user(self, email: str, password_hash: str, is_admin: bool = False) -> dict[str, Any]:
        email_n = normalize_email(email)
        now = now_ts()
        with self._lock, self._conn() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO users(email, password_hash, is_admin, is_active, created_at)
                    VALUES(?,?,?,?,?)
                    """,
                    (email_n, password_hash, 1 if is_admin else 0, 1, now),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("User already exists") from exc
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email_n,)).fetchone()
            return dict(user)

    def verify_credentials(self, email: str, password: str) -> Optional[dict[str, Any]]:
        user = self.get_user_by_email(email)
        if not user or not user.get("is_active"):
            return None
        if not verify_password(password, user["password_hash"]):
            return None
        return user

    # -------------------------
    # Sessions (cookie auth)
    # -------------------------
    def create_session(self, user_id: int, ttl_seconds: int) -> tuple[str, str, float]:
        """
        Returns (session_id, csrf_token, expires_at)
        """
        session_token, session_id = make_prefixed_token("synqc_sess_")
        sid = session_id
        csrf_token, _ = make_prefixed_token("synqc_csrf_")
        now = now_ts()
        exp = now + float(ttl_seconds)

        with self._lock, self._conn() as conn:
            conn.execute(
                """
                INSERT INTO sessions(id, user_id, csrf_token, created_at, last_seen_at, expires_at, revoked_at)
                VALUES(?,?,?,?,?,?,NULL)
                """,
                (sid, int(user_id), csrf_token, now, now, exp),
            )
        return sid, csrf_token, exp

    def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if not row:
                return None
            data = dict(row)
            if data.get("revoked_at"):
                return None
            if float(data["expires_at"]) <= now_ts():
                conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
                return None
            conn.execute("UPDATE sessions SET last_seen_at = ? WHERE id = ?", (now_ts(), session_id))
            return data

    def revoke_session(self, session_id: str) -> None:
        with self._lock, self._conn() as conn:
            conn.execute("UPDATE sessions SET revoked_at = ? WHERE id = ?", (now_ts(), session_id))

    # -------------------------
    # API tokens (scoped)
    # -------------------------
    def create_api_token(
        self,
        user_id: int,
        scopes: list[str],
        *,
        label: str | None = None,
        expires_at: float | None = None,
    ) -> tuple[str, dict[str, Any]]:
        token, token_id = make_prefixed_token("synqc_at_")
        token_hash = sha256_hex(token)
        prefix = token.split(".", 1)[1][:8]

        now = now_ts()
        scopes_json = json.dumps(scopes, separators=(",", ":"))
        with self._lock, self._conn() as conn:
            conn.execute(
                """
                INSERT INTO api_tokens(id, user_id, label, prefix, token_hash, scopes, created_at, expires_at, last_used_at, revoked_at)
                VALUES(?,?,?,?,?,?,?,?,NULL,NULL)
                """,
                (token_id, int(user_id), label, prefix, token_hash, scopes_json, now, expires_at),
            )
            row = conn.execute("SELECT * FROM api_tokens WHERE id = ?", (token_id,)).fetchone()
            return token, dict(row)

    def list_api_tokens(self, user_id: int) -> list[dict[str, Any]]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, user_id, label, prefix, scopes, created_at, expires_at, last_used_at, revoked_at
                FROM api_tokens
                WHERE user_id = ?
                ORDER BY created_at DESC
                """,
                (int(user_id),),
            ).fetchall()
            out: list[dict[str, Any]] = []
            for r in rows:
                d = dict(r)
                try:
                    d["scopes"] = json.loads(d["scopes"]) if d.get("scopes") else []
                except Exception:
                    d["scopes"] = []
                out.append(d)
            return out

    def revoke_api_token(self, token_id: str, *, user_id: int | None = None) -> bool:
        with self._lock, self._conn() as conn:
            if user_id is None:
                cur = conn.execute("UPDATE api_tokens SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL", (now_ts(), token_id))
            else:
                cur = conn.execute(
                    "UPDATE api_tokens SET revoked_at = ? WHERE id = ? AND user_id = ? AND revoked_at IS NULL",
                    (now_ts(), token_id, int(user_id)),
                )
            return cur.rowcount > 0

    def verify_api_token(self, token: str) -> Optional[dict[str, Any]]:
        """
        Returns {user_id, scopes, is_admin?} principal info if valid.
        """
        if not token.startswith("synqc_at_"):
            return None
        token_hash = sha256_hex(token)
        now = time.time()
        with self._lock:
            cached = self._token_cache.get(token_hash)
            if cached:
                expires_at, payload = cached
                if expires_at > now:
                    return dict(payload)
                self._token_cache.pop(token_hash, None)
        try:
            id_part = token.split(".", 1)[0].removeprefix("synqc_at_")
        except Exception:
            return None

        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT * FROM api_tokens WHERE id = ?", (id_part,)).fetchone()
            if not row:
                return None
            data = dict(row)

            if data.get("revoked_at"):
                return None
            exp = data.get("expires_at")
            if exp is not None and float(exp) <= now_ts():
                return None

            if token_hash != data["token_hash"]:
                return None

            conn.execute("UPDATE api_tokens SET last_used_at = ? WHERE id = ?", (now_ts(), id_part))

            try:
                scopes = json.loads(data.get("scopes") or "[]")
            except Exception:
                scopes = []

            user = conn.execute("SELECT * FROM users WHERE id = ?", (int(data["user_id"]),)).fetchone()
            if not user or not int(user["is_active"]):
                return None

            payload = {
                "user_id": int(data["user_id"]),
                "email": str(user["email"]),
                "is_admin": bool(int(user["is_admin"])),
                "scopes": scopes,
            }
            with self._lock:
                self._token_cache[token_hash] = (now + self._token_cache_ttl_seconds, dict(payload))
            return payload
