from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any


DEFAULT_HARNESS_SETTINGS = {
    'isolation': 'container',
    'auditRetentionDays': 30,
    'approvalPolicy': 'risk-based',
    'defaultBudgetUsd': 0.2,
    'defaultTimeoutSeconds': 900,
    'defaultRetryCount': 1,
    'approvalTimeoutSeconds': 3600,
    'artifactRetentionDays': 30,
    'defaultTokenBudget': 0,
    'approvalNotifyEnabled': True,
    'notificationWebhookUrl': '',
    'artifactOwnerHeader': 'X-Harness-Owner',
}


class SettingsStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA busy_timeout = 30000')
        return db

    @contextmanager
    def _db(self):
        db = self._connect()
        try:
            yield db
        finally:
            db.close()

    def _initialize(self):
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS harness_settings (settings_id INTEGER PRIMARY KEY CHECK(settings_id=1), payload TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')

    def get(self) -> dict[str, Any]:
        with self._db() as db:
            row = db.execute('SELECT payload,updated_at FROM harness_settings WHERE settings_id=1').fetchone()
        if not row:
            return {**DEFAULT_HARNESS_SETTINGS, 'updatedAt': None}
        return {**DEFAULT_HARNESS_SETTINGS, **json.loads(row['payload']), 'updatedAt': row['updated_at']}

    def save(self, values: dict[str, Any]) -> dict[str, Any]:
        payload = {key: values[key] for key in DEFAULT_HARNESS_SETTINGS if key in values}
        with self._db() as db:
            db.execute('INSERT INTO harness_settings(settings_id,payload) VALUES(1,?) ON CONFLICT(settings_id) DO UPDATE SET payload=excluded.payload,updated_at=CURRENT_TIMESTAMP', (json.dumps(payload, ensure_ascii=False),))
        return self.get()

