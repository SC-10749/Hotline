from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4


DEFAULT_RELEASE_CONFIG: dict[str, Any] = {
    "rolloutErrorThreshold": 0.05,
    "rolloutMinSamples": 30,
    "autoRollback": True,
    "e2ePassRate": 0.90,
    "ragFaithfulness": 0.85,
    "highRiskErrors": 0,
}

RELEASE_CONFIG_KEYS = ("rolloutErrorThreshold", "rolloutMinSamples", "autoRollback")
GATE_THRESHOLD_KEYS = ("e2ePassRate", "ragFaithfulness", "highRiskErrors")


class ApprovalStateError(RuntimeError):
    """Raised when an approval request can no longer be decided."""


class GovernanceStore:
    """Approval requests and decisions for high-impact tool calls."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
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

    def _initialize(self):
        with self._db() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS harness_approval (
                    request_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    tool TEXT NOT NULL,
                    risk TEXT NOT NULL DEFAULT 'high',
                    detail TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    reason TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    decided_at TEXT
                )
                ;
                CREATE TABLE IF NOT EXISTS release_gate (
                    gate_id TEXT PRIMARY KEY,
                    project TEXT NOT NULL,
                    name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    eval_run_id TEXT,
                    passed INTEGER NOT NULL,
                    checks TEXT NOT NULL,
                    thresholds TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS release_record (
                    record_id TEXT PRIMARY KEY,
                    project TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL DEFAULT '',
                    version TEXT NOT NULL DEFAULT '',
                    action TEXT NOT NULL,
                    percentage INTEGER NOT NULL DEFAULT 0,
                    gate_id TEXT,
                    eval_run_id TEXT,
                    detail TEXT NOT NULL DEFAULT '',
                    actor TEXT NOT NULL DEFAULT 'harness-operator',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS release_observation (
                    observation_id TEXT PRIMARY KEY,
                    project TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL DEFAULT '',
                    version TEXT NOT NULL DEFAULT '',
                    percentage INTEGER NOT NULL DEFAULT 0,
                    error_rate REAL NOT NULL DEFAULT 0,
                    sample_count INTEGER NOT NULL DEFAULT 0,
                    threshold REAL NOT NULL DEFAULT 0,
                    auto_rolled_back INTEGER NOT NULL DEFAULT 0,
                    detail TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_release_observation_rollout
                    ON release_observation(project, name, created_at);
                CREATE TABLE IF NOT EXISTS release_config (
                    config_id INTEGER PRIMARY KEY CHECK(config_id = 1),
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            db.execute("BEGIN IMMEDIATE")
            try:
                columns = {row["name"] for row in db.execute("PRAGMA table_info(harness_approval)")}
                if "expires_at" not in columns:
                    db.execute("ALTER TABLE harness_approval ADD COLUMN expires_at TEXT")
                if "operator" not in columns:
                    db.execute("ALTER TABLE harness_approval ADD COLUMN operator TEXT")
                record_columns = {row['name'] for row in db.execute('PRAGMA table_info(release_record)')}
                for column, ddl in (("error_rate", "REAL"), ("sample_count", "INTEGER"), ("threshold", "REAL")):
                    if column not in record_columns:
                        db.execute(f"ALTER TABLE release_record ADD COLUMN {column} {ddl}")
                db.commit()
            except Exception:
                db.rollback()
                raise

    def list(self, status: str | None = None) -> list[dict[str, Any]]:
        with self._db() as db:
            if status:
                rows = db.execute("SELECT * FROM harness_approval WHERE status=? ORDER BY created_at DESC", (status,)).fetchall()
            else:
                rows = db.execute("SELECT * FROM harness_approval ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def get(self, request_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM harness_approval WHERE request_id=?", (request_id,)).fetchone()
        return dict(row) if row else None

    def save_gate(self, payload: dict[str, Any]) -> dict[str, Any]:
        gate_id = f"gate-{uuid4().hex[:12]}"
        eval_run_id = payload.get("eval_run_id") or payload.get("evalRunId")
        with self._db() as db:
            db.execute("INSERT INTO release_gate(gate_id,project,name,version,eval_run_id,passed,checks,thresholds) VALUES(?,?,?,?,?,?,?,?)", (gate_id, payload.get('project',''), payload.get('name',''), payload.get('version',''), eval_run_id, int(bool(payload['passed'])), json.dumps(payload['checks'], ensure_ascii=False), json.dumps(payload['thresholds'], ensure_ascii=False)))
            row = db.execute("SELECT * FROM release_gate WHERE gate_id=?", (gate_id,)).fetchone()
        item = dict(row)
        item['passed'] = bool(item['passed'])
        item['checks'] = json.loads(item['checks'])
        item['thresholds'] = json.loads(item['thresholds'])
        return item

    def get_gate(self, gate_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM release_gate WHERE gate_id=?", (gate_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item['passed'] = bool(item['passed'])
        item['checks'] = json.loads(item['checks'])
        item['thresholds'] = json.loads(item['thresholds'])
        return item

    def list_gates(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute("SELECT * FROM release_gate ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 200)),)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item['passed'] = bool(item['passed'])
            item['checks'] = json.loads(item['checks'])
            item['thresholds'] = json.loads(item['thresholds'])
            result.append(item)
        return result

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        request_id = f"approval-{uuid4().hex[:12]}"
        timeout = int(payload.get("timeout_seconds") or 3600)
        expires_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + timeout))
        with self._db() as db:
            db.execute("INSERT INTO harness_approval(request_id,run_id,tool,risk,detail,expires_at,operator) VALUES(?,?,?,?,?,?,?)", (request_id, payload['run_id'], payload['tool'], payload.get('risk','high'), payload.get('detail',''), expires_at, payload.get('operator','')))
            return dict(db.execute("SELECT * FROM harness_approval WHERE request_id=?", (request_id,)).fetchone())

    def expire_pending(self) -> int:
        """Mark pending approvals whose deadline passed as expired."""
        with self._db() as db:
            cursor = db.execute(
                """UPDATE harness_approval SET status='expired', decided_at=CURRENT_TIMESTAMP
                   WHERE status='pending' AND expires_at IS NOT NULL AND datetime(expires_at) <= datetime('now')"""
            )
            return cursor.rowcount

    def decide(self, request_id: str, decision: str, reason: str = '',
               operator: str = 'harness-operator') -> dict[str, Any] | None:
        if decision not in {'approved', 'rejected'}:
            raise ValueError('审批决定无效')
        with self._db() as db:
            current = db.execute("SELECT status FROM harness_approval WHERE request_id=?", (request_id,)).fetchone()
            if not current:
                return None
            if current['status'] != 'pending':
                message = '该审批请求已超时过期' if current['status'] == 'expired' else '该审批请求已决定'
                raise ApprovalStateError(message)
            db.execute("UPDATE harness_approval SET status=?,reason=?,operator=?,decided_at=CURRENT_TIMESTAMP WHERE request_id=? AND status='pending'", (decision, reason, operator, request_id))
            row = db.execute("SELECT * FROM harness_approval WHERE request_id=?", (request_id,)).fetchone()
        return dict(row) if row else None

    def save_record(self, payload: dict[str, Any]) -> dict[str, Any]:
        record_id = f"record-{uuid4().hex[:12]}"
        with self._db() as db:
            db.execute(
                """INSERT INTO release_record(record_id,project,name,version,action,percentage,gate_id,eval_run_id,detail,actor,error_rate,sample_count,threshold)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (record_id, payload.get('project', ''), payload.get('name', ''), payload.get('version', ''),
                 payload.get('action', ''), int(payload.get('percentage') or 0), payload.get('gate_id'),
                 payload.get('eval_run_id'), payload.get('detail', ''), payload.get('actor') or 'harness-operator',
                 payload.get('error_rate'), payload.get('sample_count'), payload.get('threshold')),
            )
            row = db.execute("SELECT * FROM release_record WHERE record_id=?", (record_id,)).fetchone()
        return dict(row) if row else {}

    def save_observation(self, payload: dict[str, Any]) -> dict[str, Any]:
        observation_id = f"observation-{uuid4().hex[:12]}"
        with self._db() as db:
            db.execute(
                """INSERT INTO release_observation(observation_id,project,name,version,percentage,error_rate,sample_count,threshold,auto_rolled_back,detail)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (observation_id, payload.get('project', ''), payload.get('name', ''), payload.get('version', ''),
                 int(payload.get('percentage') or 0), float(payload.get('error_rate') or 0),
                 int(payload.get('sample_count') or 0), float(payload.get('threshold') or 0),
                 1 if payload.get('auto_rolled_back') else 0, payload.get('detail', '')),
            )
            row = db.execute("SELECT * FROM release_observation WHERE observation_id=?", (observation_id,)).fetchone()
        return dict(row) if row else {}

    def list_observations(self, project: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._db() as db:
            if project:
                rows = db.execute(
                    "SELECT * FROM release_observation WHERE project=? ORDER BY created_at DESC, rowid DESC LIMIT ?",
                    (project, max(1, min(limit, 200))),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM release_observation ORDER BY created_at DESC, rowid DESC LIMIT ?",
                    (max(1, min(limit, 200)),),
                ).fetchall()
        return [dict(row) for row in rows]

    def list_records(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute(
                "SELECT * FROM release_record ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_release_config(self) -> dict[str, Any]:
        with self._db() as db:
            row = db.execute("SELECT payload,updated_at FROM release_config WHERE config_id=1").fetchone()
        payload = dict(DEFAULT_RELEASE_CONFIG)
        if row:
            payload.update(json.loads(row["payload"]))
        payload["updated_at"] = row["updated_at"] if row else None
        return payload

    def save_release_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.get_release_config()
        current.pop("updated_at", None)
        current.update({key: value for key, value in payload.items() if value is not None})
        encoded = json.dumps(current, ensure_ascii=False)
        with self._db() as db:
            db.execute(
                """INSERT INTO release_config(config_id,payload) VALUES(1,?)
                   ON CONFLICT(config_id) DO UPDATE SET payload=excluded.payload, updated_at=CURRENT_TIMESTAMP""",
                (encoded,),
            )
        return self.get_release_config()
