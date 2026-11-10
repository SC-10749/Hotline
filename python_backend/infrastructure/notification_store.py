from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4


class NotificationStore:
    """审批决定的本地通知记录；外发通道失败不影响决定本身。"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout = 30000")
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
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS harness_notification (
                    notification_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL DEFAULT '',
                    event TEXT NOT NULL,
                    channel TEXT NOT NULL DEFAULT 'local',
                    status TEXT NOT NULL DEFAULT 'recorded',
                    detail TEXT NOT NULL DEFAULT '',
                    payload TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_harness_notification_request
                    ON harness_notification(request_id, created_at);
                """
            )

    def record(self, *, request_id: str, event: str, payload: dict[str, Any],
               channel: str = 'local', status: str = 'recorded', detail: str = '') -> dict[str, Any]:
        notification_id = f"note-{uuid4().hex[:12]}"
        with self._db() as db:
            db.execute(
                """INSERT INTO harness_notification
                   (notification_id, request_id, event, channel, status, detail, payload)
                   VALUES (?,?,?,?,?,?,?)""",
                (notification_id, request_id, event, channel, status, detail,
                 json.dumps(payload, ensure_ascii=False)),
            )
            row = db.execute("SELECT * FROM harness_notification WHERE notification_id=?",
                             (notification_id,)).fetchone()
        return self._row(row)

    def list(self, request_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._db() as db:
            if request_id:
                rows = db.execute(
                    "SELECT * FROM harness_notification WHERE request_id=? ORDER BY created_at DESC LIMIT ?",
                    (request_id, max(1, min(int(limit), 500))),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM harness_notification ORDER BY created_at DESC LIMIT ?",
                    (max(1, min(int(limit), 500)),),
                ).fetchall()
        return [self._row(row) for row in rows]

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        try:
            item["payload"] = json.loads(item.get("payload") or "{}")
        except json.JSONDecodeError:
            item["payload"] = {}
        return item
