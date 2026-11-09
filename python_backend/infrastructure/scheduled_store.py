"""定时任务存储：安排任务页面写入的真实数据。

调度线程只读这里，页面也只改这里，避免两套状态。
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4


COLUMNS = ("task_id", "name", "agent", "prompt", "interval_minutes", "enabled",
           "last_run_at", "last_run_id", "created_at", "updated_at")


class ScheduledStore:
    """User-level scheduled tasks; interval is in whole minutes."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    def _initialize(self) -> None:
        with self._db() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS harness_scheduled_task (
                    task_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    agent TEXT NOT NULL DEFAULT 'chat',
                    prompt TEXT NOT NULL,
                    interval_minutes INTEGER NOT NULL DEFAULT 60,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    last_run_at TEXT,
                    last_run_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)
            db.commit()

    @staticmethod
    def _now() -> str:
        import time
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def list(self, enabled_only: bool = False) -> list[dict[str, Any]]:
        query = "SELECT * FROM harness_scheduled_task"
        params: list[Any] = []
        if enabled_only:
            query += " WHERE enabled=1"
        query += " ORDER BY created_at DESC, rowid DESC"
        with self._db() as db:
            rows = db.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM harness_scheduled_task WHERE task_id=?", (task_id,)).fetchone()
        return dict(row) if row else None

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        task_id = f"schedule-{uuid4().hex[:12]}"
        now = self._now()
        with self._db() as db:
            db.execute(
                """INSERT INTO harness_scheduled_task
                   (task_id,name,agent,prompt,interval_minutes,enabled,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (task_id, payload["name"], payload.get("agent") or "chat", payload["prompt"],
                 int(payload.get("interval_minutes") or 60), 1 if payload.get("enabled", True) else 0, now, now),
            )
            db.commit()
        return self.get(task_id) or {}

    def update(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        fields = []
        params: list[Any] = []
        for key in ("name", "agent", "prompt", "interval_minutes", "enabled"):
            if key in payload:
                fields.append(f"{key}=?")
                value = payload[key]
                if key == "enabled":
                    value = 1 if value else 0
                params.append(value)
        if not fields:
            return self.get(task_id)
        params.append(self._now())
        params.append(task_id)
        with self._db() as db:
            db.execute(f"UPDATE harness_scheduled_task SET {','.join(fields)}, updated_at=? WHERE task_id=?", params)
            db.commit()
        return self.get(task_id)

    def delete(self, task_id: str) -> bool:
        with self._db() as db:
            cursor = db.execute("DELETE FROM harness_scheduled_task WHERE task_id=?", (task_id,))
            db.commit()
        return cursor.rowcount > 0

    def mark_run(self, task_id: str, run_id: str) -> None:
        with self._db() as db:
            db.execute("UPDATE harness_scheduled_task SET last_run_at=?, last_run_id=? WHERE task_id=?",
                       (self._now(), run_id, task_id))
            db.commit()
