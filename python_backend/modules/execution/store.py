from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4


ACTIVE_STATUSES = ("queued", "running")
TERMINAL_STATUSES = ("completed", "failed", "cancelled")


class ActiveExecutionError(RuntimeError):
    pass


class ExecutionStore:
    """Single-host durable queue and replayable event log for Agent runs."""

    def __init__(self, path: Path, lease_seconds: int = 45, worker_stale_seconds: int = 15):
        self.path = Path(path)
        self.lease_seconds = lease_seconds
        self.worker_stale_seconds = worker_stale_seconds
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout = 30000")
        db.execute("PRAGMA foreign_keys = ON")
        return db

    @contextmanager
    def _db(self):
        db = self._connect()
        try:
            yield db
        finally:
            db.close()

    def _initialize(self) -> None:
        with self._db() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS execution_run (
                    run_id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    query TEXT NOT NULL,
                    file_id TEXT,
                    status TEXT NOT NULL,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    worker_id TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    lease_until REAL,
                    error TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS uq_execution_active_conversation
                    ON execution_run(conversation_id) WHERE status IN ('queued', 'running');
                CREATE INDEX IF NOT EXISTS idx_execution_run_status_created
                    ON execution_run(status, created_at);
                CREATE TABLE IF NOT EXISTS execution_event (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES execution_run(run_id)
                );
                CREATE INDEX IF NOT EXISTS idx_execution_event_run_id
                    ON execution_event(run_id, event_id);
                CREATE TABLE IF NOT EXISTS execution_worker (
                    worker_id TEXT PRIMARY KEY,
                    process_id INTEGER NOT NULL,
                    last_seen REAL NOT NULL,
                    current_run_id TEXT
                );
            """)

    @staticmethod
    def _now_iso() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    @staticmethod
    def _run_dict(row: sqlite3.Row) -> dict[str, Any]:
        return dict(row)

    def enqueue(self, conversation_id: str, agent: str, query: str, file_id: str | None) -> dict[str, Any]:
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            active = db.execute(
                "SELECT * FROM execution_run WHERE conversation_id=? AND status IN ('queued','running')",
                (conversation_id,),
            ).fetchone()
            if active:
                if (active["agent"], active["query"], active["file_id"]) == (agent, query, file_id):
                    db.commit()
                    return self._run_dict(active)
                raise ActiveExecutionError("该会话正在执行中，请稍后再试")

            run_id = uuid4().hex
            db.execute(
                """INSERT INTO execution_run
                   (run_id,conversation_id,agent,query,file_id,status,created_at)
                   VALUES (?,?,?,?,?,'queued',?)""",
                (run_id, conversation_id, agent, query, file_id, self._now_iso()),
            )
            row = db.execute("SELECT * FROM execution_run WHERE run_id=?", (run_id,)).fetchone()
            db.commit()
            return self._run_dict(row)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def claim_next(self, worker_id: str) -> dict[str, Any] | None:
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            now = time.time()
            expired = db.execute(
                "SELECT run_id FROM execution_run WHERE status='running' AND lease_until < ?",
                (now,),
            ).fetchall()
            for row in expired:
                run_id = row["run_id"]
                self._append_event(db, run_id, {
                    "type": "error",
                    "content": "Worker 意外中断，任务未完成。请重新提交。",
                })
                db.execute(
                    """UPDATE execution_run SET status='failed', finished_at=?, lease_until=NULL,
                       error='worker lease expired' WHERE run_id=? AND status='running'""",
                    (self._now_iso(), run_id),
                )

            row = db.execute(
                "SELECT * FROM execution_run WHERE status='queued' ORDER BY created_at, rowid LIMIT 1"
            ).fetchone()
            if not row:
                db.commit()
                return None
            db.execute(
                """UPDATE execution_run SET status='running', worker_id=?, started_at=?, lease_until=?
                   WHERE run_id=? AND status='queued'""",
                (worker_id, self._now_iso(), now + self.lease_seconds, row["run_id"]),
            )
            claimed = db.execute("SELECT * FROM execution_run WHERE run_id=?", (row["run_id"],)).fetchone()
            db.commit()
            return self._run_dict(claimed)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def append_event(self, run_id: str, event: dict[str, Any]) -> int:
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            event_id = self._append_event(db, run_id, event)
            db.commit()
            return event_id
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _append_event(self, db: sqlite3.Connection, run_id: str, event: dict[str, Any]) -> int:
        cursor = db.execute(
            "INSERT INTO execution_event(run_id,event_json,created_at) VALUES (?,?,?)",
            (run_id, json.dumps(event, ensure_ascii=False), self._now_iso()),
        )
        return int(cursor.lastrowid)

    def events_after(self, run_id: str, event_id: int = 0) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute(
                "SELECT event_id,event_json FROM execution_event WHERE run_id=? AND event_id>? ORDER BY event_id",
                (run_id, event_id),
            ).fetchall()
        return [{"event_id": row["event_id"], "event": json.loads(row["event_json"])} for row in rows]

    def find_run_by_event(self, conversation_id: str, agent: str, query: str,
                          file_id: str | None, event_id: int) -> dict[str, Any] | None:
        if event_id <= 0:
            return None
        with self._db() as db:
            row = db.execute(
                """SELECT r.* FROM execution_run r JOIN execution_event e ON e.run_id=r.run_id
                   WHERE r.conversation_id=? AND r.agent=? AND r.query=? AND r.file_id IS ?
                     AND e.event_id=?""",
                (conversation_id, agent, query, file_id, event_id),
            ).fetchone()
        return self._run_dict(row) if row else None

    def get_status(self, run_id: str) -> str | None:
        with self._db() as db:
            row = db.execute("SELECT status FROM execution_run WHERE run_id=?", (run_id,)).fetchone()
        return row["status"] if row else None

    def request_cancel(self, conversation_id: str) -> bool:
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT run_id,status FROM execution_run WHERE conversation_id=? AND status IN ('queued','running')",
                (conversation_id,),
            ).fetchone()
            if not row:
                db.commit()
                return False
            if row["status"] == "queued":
                self._append_event(db, row["run_id"], {"type": "error", "content": "任务已停止"})
                db.execute(
                    "UPDATE execution_run SET status='cancelled',cancel_requested=1,finished_at=? WHERE run_id=?",
                    (self._now_iso(), row["run_id"]),
                )
            else:
                db.execute("UPDATE execution_run SET cancel_requested=1 WHERE run_id=?", (row["run_id"],))
            db.commit()
            return True
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def is_cancel_requested(self, run_id: str) -> bool:
        with self._db() as db:
            row = db.execute("SELECT cancel_requested FROM execution_run WHERE run_id=?", (run_id,)).fetchone()
        return bool(row and row["cancel_requested"])

    def finish(self, run_id: str, status: str, error: str | None = None) -> None:
        if status not in TERMINAL_STATUSES:
            raise ValueError(f"Invalid terminal execution status: {status}")
        with self._db() as db:
            db.execute(
                """UPDATE execution_run SET status=?,finished_at=?,lease_until=NULL,error=?
                   WHERE run_id=? AND status IN ('queued','running')""",
                (status, self._now_iso(), error, run_id),
            )

    def heartbeat_worker(self, worker_id: str, process_id: int, current_run_id: str | None = None) -> None:
        with self._db() as db:
            db.execute(
                """INSERT INTO execution_worker(worker_id,process_id,last_seen,current_run_id)
                   VALUES (?,?,?,?) ON CONFLICT(worker_id) DO UPDATE SET
                   process_id=excluded.process_id,last_seen=excluded.last_seen,
                   current_run_id=excluded.current_run_id""",
                (worker_id, process_id, time.time(), current_run_id),
            )

    def heartbeat_run(self, run_id: str, worker_id: str) -> None:
        with self._db() as db:
            db.execute(
                "UPDATE execution_run SET lease_until=? WHERE run_id=? AND status='running' AND worker_id=?",
                (time.time() + self.lease_seconds, run_id, worker_id),
            )

    def remove_worker(self, worker_id: str) -> None:
        with self._db() as db:
            db.execute("DELETE FROM execution_worker WHERE worker_id=?", (worker_id,))

    def has_live_worker(self) -> bool:
        with self._db() as db:
            row = db.execute(
                "SELECT 1 FROM execution_worker WHERE last_seen >= ? LIMIT 1",
                (time.time() - self.worker_stale_seconds,),
            ).fetchone()
        return row is not None
