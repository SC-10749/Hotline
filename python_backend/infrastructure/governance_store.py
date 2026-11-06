from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4


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
            db.execute(
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
                )
                """
            )

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
        import json
        gate_id = f"gate-{uuid4().hex[:12]}"
        with self._db() as db:
            db.execute("INSERT INTO release_gate(gate_id,project,name,version,eval_run_id,passed,checks,thresholds) VALUES(?,?,?,?,?,?,?,?)", (gate_id, payload.get('project',''), payload.get('name',''), payload.get('version',''), payload.get('eval_run_id'), int(bool(payload['passed'])), json.dumps(payload['checks'], ensure_ascii=False), json.dumps(payload['thresholds'], ensure_ascii=False)))
            row = db.execute("SELECT * FROM release_gate WHERE gate_id=?", (gate_id,)).fetchone()
        item = dict(row)
        item['passed'] = bool(item['passed'])
        item['checks'] = json.loads(item['checks'])
        item['thresholds'] = json.loads(item['thresholds'])
        return item

    def list_gates(self, limit: int = 100) -> list[dict[str, Any]]:
        import json
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
        with self._db() as db:
            db.execute("INSERT INTO harness_approval(request_id,run_id,tool,risk,detail) VALUES(?,?,?,?,?)", (request_id, payload['run_id'], payload['tool'], payload.get('risk','high'), payload.get('detail','')))
            return dict(db.execute("SELECT * FROM harness_approval WHERE request_id=?", (request_id,)).fetchone())

    def decide(self, request_id: str, decision: str, reason: str = '') -> dict[str, Any] | None:
        if decision not in {'approved', 'rejected'}:
            raise ValueError('审批决定无效')
        with self._db() as db:
            db.execute("UPDATE harness_approval SET status=?,reason=?,decided_at=CURRENT_TIMESTAMP WHERE request_id=? AND status='pending'", (decision, reason, request_id))
            row = db.execute("SELECT * FROM harness_approval WHERE request_id=?", (request_id,)).fetchone()
        return dict(row) if row else None

