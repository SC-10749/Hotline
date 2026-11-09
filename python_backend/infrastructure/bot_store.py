"""轻量机器人存储：bot 页写入的真实数据。

机器人 = 名称 + 角色指令 + 绑定技能；与具体会话的绑定单独一张表，
这样 Worker 只需要会话编号就能取到对应人设。
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4


class BotStore:
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
                CREATE TABLE IF NOT EXISTS harness_bot (
                    bot_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    instruction TEXT NOT NULL DEFAULT '',
                    skills TEXT NOT NULL DEFAULT '[]',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS harness_bot_session (
                    conversation_id TEXT PRIMARY KEY,
                    bot_id TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)
            db.commit()

    @staticmethod
    def _now() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    @staticmethod
    def _view(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item['enabled'] = bool(item.get('enabled'))
        try:
            skills = json.loads(item.get('skills') or '[]')
        except (TypeError, ValueError):
            skills = []
        item['skills'] = [str(value) for value in skills if isinstance(value, str)] if isinstance(skills, list) else []
        return item

    def list(self) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute("SELECT * FROM harness_bot ORDER BY created_at DESC, rowid DESC").fetchall()
        return [self._view(row) for row in rows]

    def get(self, bot_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM harness_bot WHERE bot_id=?", (bot_id,)).fetchone()
        return self._view(row) if row else None

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        bot_id = f"bot-{uuid4().hex[:12]}"
        now = self._now()
        with self._db() as db:
            db.execute(
                """INSERT INTO harness_bot(bot_id,name,instruction,skills,enabled,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (bot_id, payload['name'], payload.get('instruction', ''),
                 json.dumps(payload.get('skills') or [], ensure_ascii=False),
                 1 if payload.get('enabled', True) else 0, now, now),
            )
            db.commit()
        return self.get(bot_id) or {}

    def update(self, bot_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        fields: list[str] = []
        params: list[Any] = []
        for key in ('name', 'instruction', 'skills', 'enabled'):
            if key in payload:
                fields.append(f"{key}=?")
                value = payload[key]
                if key == 'skills':
                    value = json.dumps(value or [], ensure_ascii=False)
                elif key == 'enabled':
                    value = 1 if value else 0
                params.append(value)
        if not fields:
            return self.get(bot_id)
        params.extend([self._now(), bot_id])
        with self._db() as db:
            db.execute(f"UPDATE harness_bot SET {','.join(fields)}, updated_at=? WHERE bot_id=?", params)
            db.commit()
        return self.get(bot_id)

    def delete(self, bot_id: str) -> bool:
        with self._db() as db:
            cursor = db.execute("DELETE FROM harness_bot WHERE bot_id=?", (bot_id,))
            db.execute("DELETE FROM harness_bot_session WHERE bot_id=?", (bot_id,))
            db.commit()
        return cursor.rowcount > 0

    def bind_session(self, conversation_id: str, bot_id: str) -> bool:
        """把会话绑定到机器人；绑定以会话编号为键，一个会话只对应一个人设。"""
        with self._db() as db:
            db.execute(
                """INSERT INTO harness_bot_session(conversation_id,bot_id,created_at) VALUES(?,?,?)
                   ON CONFLICT(conversation_id) DO UPDATE SET bot_id=excluded.bot_id""",
                (conversation_id, bot_id, self._now()))
            db.commit()
        return True

    def session_bot(self, conversation_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute(
                """SELECT b.* FROM harness_bot_session s JOIN harness_bot b ON b.bot_id=s.bot_id
                   WHERE s.conversation_id=?""", (conversation_id,)).fetchone()
        return self._view(row) if row else None
