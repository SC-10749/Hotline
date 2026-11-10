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
WORKER_STATES = ("online", "draining", "offline")


def event_level(event: dict[str, Any]) -> str:
    """Event severity: explicit level wins, otherwise inferred from type/status."""
    level = event.get("level")
    if isinstance(level, str) and level:
        return level
    if event.get("type") == "error":
        return "error"
    if event.get("type") == "tool_end" and event.get("status") == "error":
        return "error"
    return "info"


def event_tool(event: dict[str, Any]) -> str:
    for key in ("tool", "toolName"):
        value = event.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


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
                    error TEXT,
                    agent_id TEXT NOT NULL DEFAULT '',
                    workspace_id TEXT NOT NULL DEFAULT ''
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
                    current_run_id TEXT,
                    capacity INTEGER NOT NULL DEFAULT 1,
                    runtime_version TEXT NOT NULL DEFAULT '',
                    state TEXT NOT NULL DEFAULT 'online'
                );
            """)
            self._ensure_columns(db, "execution_run", {
                "agent_id": "TEXT NOT NULL DEFAULT ''",
                "workspace_id": "TEXT NOT NULL DEFAULT ''",
            })
            self._ensure_columns(db, "execution_worker", {
                "capacity": "INTEGER NOT NULL DEFAULT 1",
                "runtime_version": "TEXT NOT NULL DEFAULT ''",
                "state": "TEXT NOT NULL DEFAULT 'online'",
            })

    @staticmethod
    def _ensure_columns(db: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
        existing = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
        for name, definition in columns.items():
            if name not in existing:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    @staticmethod
    def _now_iso() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    @staticmethod
    def _run_dict(row: sqlite3.Row) -> dict[str, Any]:
        return dict(row)

    def enqueue(self, conversation_id: str, agent: str, query: str, file_id: str | None,
                agent_id: str = "", workspace_id: str = "") -> dict[str, Any]:
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            active = db.execute(
                "SELECT * FROM execution_run WHERE conversation_id=? AND status IN ('queued','running')",
                (conversation_id,),
            ).fetchone()
            if active:
                if (active["agent"], active["query"], active["file_id"], active["workspace_id"], active["agent_id"]) == (agent, query, file_id, workspace_id, agent_id):
                    db.commit()
                    return self._run_dict(active)
                raise ActiveExecutionError("该会话正在执行中，请稍后再试")

            run_id = uuid4().hex
            db.execute(
                """INSERT INTO execution_run
                   (run_id,conversation_id,agent,query,file_id,status,created_at,agent_id,workspace_id)
                   VALUES (?,?,?,?,?,'queued',?,?,?)""",
                (run_id, conversation_id, agent, query, file_id, self._now_iso(), agent_id, workspace_id),
            )
            row = db.execute("SELECT * FROM execution_run WHERE run_id=?", (run_id,)).fetchone()
            db.commit()
            return self._run_dict(row)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def retry_run(self, run_id: str) -> dict[str, Any] | None:
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            source = db.execute("SELECT conversation_id,agent,query,file_id,status,agent_id,workspace_id FROM execution_run WHERE run_id=?", (run_id,)).fetchone()
            if not source or source["status"] not in TERMINAL_STATUSES:
                db.commit()
                return None
            active = db.execute("SELECT run_id FROM execution_run WHERE conversation_id=? AND status IN ('queued','running')", (source["conversation_id"],)).fetchone()
            if active:
                raise ActiveExecutionError("该会话正在执行中，请稍后再试")
            new_run_id = uuid4().hex
            db.execute(
                "INSERT INTO execution_run(run_id,conversation_id,agent,query,file_id,status,created_at,agent_id,workspace_id) VALUES(?,?,?,?,?,'queued',?,?,?)",
                (new_run_id, source["conversation_id"], source["agent"], source["query"], source["file_id"],
                 self._now_iso(), source["agent_id"], source["workspace_id"]),
            )
            row = db.execute("SELECT * FROM execution_run WHERE run_id=?", (new_run_id,)).fetchone()
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

    def events_after(self, run_id: str, event_id: int = 0, *, level: str | None = None,
                     tool: str | None = None, has_error: bool | None = None,
                     since: str | None = None, until: str | None = None,
                     event_type: str | None = None) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute(
                "SELECT event_id,event_json,created_at FROM execution_event WHERE run_id=? AND event_id>? ORDER BY event_id",
                (run_id, event_id),
            ).fetchall()
        items = [{"event_id": row["event_id"], "created_at": row["created_at"],
                  "event": json.loads(row["event_json"])} for row in rows]
        for item in items:
            item["level"] = event_level(item["event"])
        if level:
            items = [item for item in items if item["level"] == level]
        if tool:
            items = [item for item in items if event_tool(item["event"]) == tool]
        if has_error:
            items = [item for item in items if item["level"] == "error"]
        if event_type:
            items = [item for item in items if item["event"].get("type") == event_type]
        if since:
            items = [item for item in items if item["created_at"] >= since]
        if until:
            items = [item for item in items if item["created_at"] <= until]
        return items

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

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM execution_run WHERE run_id=?", (run_id,)).fetchone()
        return self._run_dict(row) if row else None

    def list_runs(self, status: str | None = None, search: str | None = None,
                  limit: int = 100, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status=?")
            params.append(status)
        if search:
            clauses.append("(run_id LIKE ? OR conversation_id LIKE ? OR agent LIKE ? OR query LIKE ?)")
            term = f"%{search}%"
            params.extend([term, term, term, term])
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        safe_limit = max(1, min(int(limit), 200))
        safe_offset = max(0, int(offset))
        with self._db() as db:
            total = int(db.execute(f"SELECT COUNT(*) FROM execution_run{where}", params).fetchone()[0])
            rows = db.execute(
                f"SELECT * FROM execution_run{where} ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?",
                [*params, safe_limit, safe_offset],
            ).fetchall()
        return [self._run_dict(row) for row in rows], total

    def daily_stats(self, day: str | None = None) -> dict[str, Any]:
        """今日运行统计：运行数、完成数与模型用量，按 UTC 日期聚合。"""
        today = day or time.strftime("%Y-%m-%d", time.gmtime())
        with self._db() as db:
            rows = db.execute(
                "SELECT run_id,status,created_at,finished_at FROM execution_run "
                "WHERE created_at>=? OR finished_at>=?",
                (today, today),
            ).fetchall()
            events = db.execute(
                "SELECT e.event_json FROM execution_event e JOIN execution_run r ON r.run_id=e.run_id "
                "WHERE r.created_at>=? OR r.finished_at>=?",
                (today, today),
            ).fetchall()
        stats = {"day": today, "activeRuns": 0, "runsToday": 0, "completedToday": 0,
                 "failedToday": 0, "cancelledToday": 0, "tokensToday": 0, "toolCallsToday": 0}
        for row in rows:
            if row["status"] in ACTIVE_STATUSES:
                stats["activeRuns"] += 1
            if str(row["created_at"]).startswith(today):
                stats["runsToday"] += 1
            finished = str(row["finished_at"] or "")
            if finished.startswith(today):
                if row["status"] == "completed":
                    stats["completedToday"] += 1
                elif row["status"] == "failed":
                    stats["failedToday"] += 1
                elif row["status"] == "cancelled":
                    stats["cancelledToday"] += 1
        for row in events:
            try:
                event = json.loads(row["event_json"])
            except (TypeError, ValueError):
                continue
            if not isinstance(event, dict):
                continue
            if event.get("type") == "usage":
                usage = event.get("usage") or {}
                stats["tokensToday"] += int(usage.get("totalTokens") or 0)
            elif event.get("type") == "tool_start":
                stats["toolCallsToday"] += 1
        return stats

    def get_events(self, run_id: str, event_id: int = 0, **filters: Any) -> list[dict[str, Any]]:
        return self.events_after(run_id, event_id, **filters)

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

    def request_cancel_run(self, run_id: str) -> bool:
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT run_id,status FROM execution_run WHERE run_id=? AND status IN ('queued','running')",
                (run_id,),
            ).fetchone()
            if not row:
                db.commit()
                return False
            if row["status"] == "queued":
                self._append_event(db, run_id, {"type": "error", "content": "任务已停止"})
                db.execute(
                    "UPDATE execution_run SET status='cancelled',cancel_requested=1,finished_at=? WHERE run_id=?",
                    (self._now_iso(), run_id),
                )
            else:
                db.execute("UPDATE execution_run SET cancel_requested=1 WHERE run_id=?", (run_id,))
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

    def heartbeat_worker(self, worker_id: str, process_id: int, current_run_id: str | None = None,
                         capacity: int | None = None, runtime_version: str | None = None) -> None:
        updates = ["process_id=excluded.process_id", "last_seen=excluded.last_seen",
                   "current_run_id=excluded.current_run_id",
                   "state=CASE WHEN execution_worker.state='draining' THEN 'draining' ELSE 'online' END"]
        if capacity is not None:
            updates.append("capacity=excluded.capacity")
        if runtime_version is not None:
            updates.append("runtime_version=excluded.runtime_version")
        values: dict[str, Any] = {
            "worker_id": worker_id, "process_id": int(process_id), "last_seen": time.time(),
            "current_run_id": current_run_id,
            "capacity": max(1, int(capacity)) if capacity is not None else 1,
            "runtime_version": str(runtime_version) if runtime_version is not None else "",
        }
        sql = ("INSERT INTO execution_worker"
               "(worker_id,process_id,last_seen,current_run_id,capacity,runtime_version,state)"
               " VALUES(:worker_id,:process_id,:last_seen,:current_run_id,:capacity,:runtime_version,'online')"
               " ON CONFLICT(worker_id) DO UPDATE SET " + ",".join(updates))
        with self._db() as db:
            db.execute(sql, values)

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

    def list_workers(self) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute("SELECT * FROM execution_worker ORDER BY last_seen DESC").fetchall()
        return [self._worker_dict(row) for row in rows]

    def list_worker_errors(self, worker_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """节点错误日志：该节点执行失败的运行及其错误事件。"""
        with self._db() as db:
            rows = db.execute(
                "SELECT run_id,status,error,created_at,finished_at FROM execution_run "
                "WHERE worker_id=? AND error IS NOT NULL AND error<>'' "
                "ORDER BY finished_at DESC, rowid DESC LIMIT ?",
                (worker_id, max(1, min(limit, 200))),
            ).fetchall()
        items = []
        for row in rows:
            errors = self.events_after(row["run_id"], has_error=True)
            items.append({
                "run_id": row["run_id"],
                "status": row["status"],
                "error": row["error"],
                "created_at": row["created_at"],
                "finished_at": row["finished_at"],
                "events": [{"event_id": item["event_id"], "created_at": item["created_at"],
                            "content": str(item["event"].get("content") or "")[:500],
                            "tool": event_tool(item["event"])} for item in errors],
            })
        return items

    def set_worker_state(self, worker_id: str, state: str) -> dict[str, Any] | None:
        if state not in WORKER_STATES:
            raise ValueError(f"Invalid worker state: {state}")
        with self._db() as db:
            db.execute("UPDATE execution_worker SET state=? WHERE worker_id=?", (state, worker_id))
            row = db.execute("SELECT * FROM execution_worker WHERE worker_id=?", (worker_id,)).fetchone()
        return self._worker_dict(row) if row else None

    def _worker_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        worker = self._run_dict(row)
        if worker["last_seen"] < time.time() - self.worker_stale_seconds:
            worker["state"] = "offline"
        worker["online"] = worker["state"] != "offline"
        return worker
