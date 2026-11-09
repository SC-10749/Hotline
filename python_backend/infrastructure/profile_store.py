"""个人偏好存储：昵称、简介、回答风格与界面主题。"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any


DEFAULT_PROFILE = {
    'nickname': '',
    'bio': '',
    'answerStyle': 'default',
    'theme': 'system',
}


class ProfileStore:
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
            db.execute(
                """CREATE TABLE IF NOT EXISTS harness_profile (
                       profile_id INTEGER PRIMARY KEY CHECK(profile_id=1),
                       payload TEXT NOT NULL,
                       updated_at TEXT NOT NULL
                   )"""
            )
            db.commit()

    @staticmethod
    def _now() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def get(self) -> dict[str, Any]:
        with self._db() as db:
            row = db.execute("SELECT payload,updated_at FROM harness_profile WHERE profile_id=1").fetchone()
        if not row:
            return {**DEFAULT_PROFILE, 'updatedAt': None}
        try:
            saved = json.loads(row['payload'])
        except (TypeError, ValueError):
            saved = {}
        values = {**DEFAULT_PROFILE, **{key: saved[key] for key in DEFAULT_PROFILE if key in saved}}
        return {**values, 'updatedAt': row['updated_at']}

    def save(self, values: dict[str, Any]) -> dict[str, Any]:
        current = self.get()
        # 部分更新：没提交的字段沿用旧值，避免只改主题就把昵称清空。
        payload = {key: values[key] if key in values else current[key] for key in DEFAULT_PROFILE}
        with self._db() as db:
            db.execute(
                """INSERT INTO harness_profile(profile_id,payload,updated_at) VALUES(1,?,?)
                   ON CONFLICT(profile_id) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at""",
                (json.dumps(payload, ensure_ascii=False), self._now()),
            )
            db.commit()
        return self.get()
