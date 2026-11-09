"""用户自带模型凭证：只落在本地 data 目录，对外只回显掩码。"""

from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class CredentialStore:
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
                """CREATE TABLE IF NOT EXISTS harness_model_credential (
                       credential_id INTEGER PRIMARY KEY CHECK(credential_id=1),
                       provider TEXT NOT NULL DEFAULT '',
                       base_url TEXT NOT NULL DEFAULT '',
                       model TEXT NOT NULL DEFAULT '',
                       api_key TEXT NOT NULL DEFAULT '',
                       updated_at TEXT NOT NULL
                   )"""
            )
            db.commit()

    @staticmethod
    def _now() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    @staticmethod
    def mask(api_key: str) -> str:
        """只回显首尾片段，中间用固定掩码替代。"""
        if not api_key:
            return ''
        if len(api_key) <= 8:
            return '***'
        return f"{api_key[:3]}***{api_key[-4:]}"

    def get(self) -> dict[str, Any] | None:
        """内部使用：返回明文凭证。"""
        with self._db() as db:
            row = db.execute("SELECT * FROM harness_model_credential WHERE credential_id=1").fetchone()
        if not row:
            return None
        item = dict(row)
        item['hasKey'] = bool(item.get('api_key'))
        return item

    def public(self) -> dict[str, Any] | None:
        """对外使用：apiKey 只给掩码。"""
        item = self.get()
        if not item:
            return None
        item['apiKey'] = self.mask(item.get('api_key') or '')
        item['api_key'] = ''
        return item

    def save(self, values: dict[str, Any]) -> dict[str, Any]:
        current = self.get() or {}
        payload = {
            'provider': (values.get('provider') or '').strip(),
            'base_url': (values.get('base_url') or '').strip(),
            'model': (values.get('model') or '').strip(),
            'api_key': (values.get('api_key') or '').strip() or current.get('api_key', ''),
        }
        with self._db() as db:
            db.execute(
                """INSERT INTO harness_model_credential
                   (credential_id,provider,base_url,model,api_key,updated_at) VALUES(1,?,?,?,?,?)
                   ON CONFLICT(credential_id) DO UPDATE SET provider=excluded.provider,
                       base_url=excluded.base_url, model=excluded.model, api_key=excluded.api_key,
                       updated_at=excluded.updated_at""",
                (payload['provider'], payload['base_url'], payload['model'], payload['api_key'], self._now()),
            )
            db.commit()
        return self.public() or {}

    def delete(self) -> bool:
        with self._db() as db:
            cursor = db.execute("DELETE FROM harness_model_credential WHERE credential_id=1")
            db.commit()
        return cursor.rowcount > 0
