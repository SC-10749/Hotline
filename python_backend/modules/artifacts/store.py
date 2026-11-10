from __future__ import annotations

import hashlib
import re
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from itertools import count
from pathlib import Path, PurePosixPath
from uuid import uuid4


def age_days(created_at: str, now: float | None = None) -> int:
    """Whole days since the artifact was registered; unparsable timestamps count as fresh."""
    text = str(created_at).strip()
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return 0
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    reference = datetime.now(timezone.utc) if now is None else datetime.fromtimestamp(now, timezone.utc)
    return max(0, int((reference - moment).total_seconds() // 86400))


class ArtifactStore:
    """Explicit run ownership; never infer it from filenames or directory scans."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript("""
                CREATE TABLE IF NOT EXISTS run_artifact (
                    artifact_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    storage_backend TEXT NOT NULL,
                    storage_key TEXT NOT NULL,
                    owner TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                    UNIQUE(run_id, storage_backend, storage_key)
                );
                CREATE INDEX IF NOT EXISTS idx_artifact_run ON run_artifact(run_id, created_at);
            """)
            # 老库没有 owner 列：补齐后历史记录归属为空串，下载行为不变。
            columns = {row['name'] for row in db.execute('PRAGMA table_info(run_artifact)')}
            if 'owner' not in columns:
                db.execute("ALTER TABLE run_artifact ADD COLUMN owner TEXT NOT NULL DEFAULT ''")

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def register(self, *, run_id: str, name: str, size: int, sha256: str,
                 content_type: str, storage_backend: str, storage_key: str,
                 owner: str = '') -> dict:
        key = PurePosixPath(storage_key)
        if (not run_id or not name or name != PurePosixPath(name).name or '\\' in name
                or any(ord(char) < 32 for char in name)
                or size < 0 or not re.fullmatch(r'[a-f0-9]{64}', sha256)
                or storage_backend not in {'local', 'minio'} or not storage_key
                or key.is_absolute() or '..' in key.parts or '\\' in storage_key or ':' in storage_key
                or not isinstance(owner, str) or len(owner) > 200):
            raise ValueError('无效的产物登记信息')
        fields = dict(run_id=run_id, name=name, size=size, sha256=sha256, content_type=content_type,
                      storage_backend=storage_backend, storage_key=storage_key, owner=owner)
        with self._db() as db:
            db.execute("""INSERT INTO run_artifact
                (artifact_id, run_id, name, size, sha256, content_type, storage_backend, storage_key, owner)
                VALUES (:artifact_id, :run_id, :name, :size, :sha256, :content_type, :storage_backend, :storage_key, :owner)
                ON CONFLICT(run_id, storage_backend, storage_key) DO NOTHING""",
                       {'artifact_id': uuid4().hex, **fields})
            row = dict(db.execute('SELECT * FROM run_artifact WHERE run_id=? AND storage_backend=? AND storage_key=?',
                                  (run_id, storage_backend, storage_key)).fetchone())
            if any(row[key] != value for key, value in fields.items()):
                raise ValueError('产物位置已登记，不能覆盖原始记录')
        return row

    def get(self, artifact_id: str) -> dict | None:
        with self._db() as db:
            row = db.execute('SELECT * FROM run_artifact WHERE artifact_id=?', (artifact_id,)).fetchone()
        return dict(row) if row else None

    def list(self, run_id: str | None = None, limit: int = 100, offset: int = 0,
             owner: str | None = None) -> tuple[list[dict], int]:
        clauses, params = [], []
        if run_id:
            clauses.append('run_id=?')
            params.append(run_id)
        if owner is not None:
            clauses.append('owner=?')
            params.append(owner)
        where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
        with self._db() as db:
            total = db.execute(f'SELECT COUNT(*) FROM run_artifact{where}', params).fetchone()[0]
            rows = db.execute(f'SELECT * FROM run_artifact{where} ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?',
                              [*params, max(1, min(limit, 200)), max(0, offset)]).fetchall()
        items = [dict(row) for row in rows]
        for item in items:
            item['ageDays'] = age_days(item['created_at'])
        return items, total

    def delete(self, artifact_id: str) -> bool:
        with self._db() as db:
            cursor = db.execute('DELETE FROM run_artifact WHERE artifact_id=?', (artifact_id,))
        return cursor.rowcount > 0

    def list_expired(self, older_than_days: int) -> list[dict]:
        days = max(1, int(older_than_days))
        now = time.time()
        with self._db() as db:
            rows = db.execute('SELECT * FROM run_artifact').fetchall()
        return [dict(row) for row in rows if age_days(row['created_at'], now) >= days]

    def expire(self, older_than_days: int) -> list[str]:
        """Drop registrations older than the retention window; files stay untouched."""
        removed = [row['artifact_id'] for row in self.list_expired(older_than_days)]
        if removed:
            with self._db() as db:
                db.executemany('DELETE FROM run_artifact WHERE artifact_id=?', [(item,) for item in removed])
        return removed


_legacy_sequence = count(1)


def legacy_run_id(identifier: str) -> str:
    """Run id for entries without one: the session id stands in, timestamped as fallback."""
    text = str(identifier or '').strip()
    if text:
        return text
    return f'legacy-{int(time.time())}-{next(_legacy_sequence)}'


def register_generated_file(store: ArtifactStore, path: Path, *, run_id: str, content_type: str,
                               storage_backend: str, storage_key: str, owner: str = '') -> tuple[dict | None, str]:
    """Register a freshly generated file by its on-disk size and digest.

    Never raises: a failed registration returns (None, reason) so the caller can still
    hand the file back to the user.
    """
    try:
        data = Path(path).read_bytes()
        record = store.register(run_id=run_id, name=Path(path).name, size=len(data),
                                sha256=hashlib.sha256(data).hexdigest(), content_type=content_type,
                                storage_backend=storage_backend, storage_key=storage_key, owner=owner)
        return record, ''
    except Exception as exc:
        return None, type(exc).__name__


def register_legacy_artifact(store: ArtifactStore, path: Path, *, conversation_id: str,
                                  storage_backend: str, content_type: str) -> tuple[dict | None, str]:
    """Register a file produced outside the run queue; the session id stands in for a run id."""
    name = Path(path).name
    storage_key = f'ppt/{conversation_id}/{name}' if storage_backend == 'minio' else name
    return register_generated_file(store, path, run_id=legacy_run_id(conversation_id),
                                   content_type=content_type, storage_backend=storage_backend,
                                   storage_key=storage_key)


def artifact_metadata(record: dict) -> dict:
    return {**{key: record[key] for key in ('artifact_id', 'run_id', 'name', 'size', 'sha256',
                                           'content_type', 'storage_backend', 'owner', 'created_at')},
            'ageDays': age_days(record['created_at']),
            'download': f"/harness/artifacts/{record['artifact_id']}/download"}
