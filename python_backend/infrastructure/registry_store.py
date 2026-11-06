from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4


class RegistryStore:
    """Registry metadata for MCP tools and model routes."""

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
                CREATE TABLE IF NOT EXISTS harness_tool (
                    tool_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'mcp',
                    scope TEXT NOT NULL DEFAULT 'workspace',
                    risk TEXT NOT NULL DEFAULT 'low',
                    status TEXT NOT NULL DEFAULT 'configured',
                    description TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS harness_model (
                    model_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT '',
                    route TEXT NOT NULL DEFAULT 'default',
                    status TEXT NOT NULL DEFAULT 'available',
                    cost_policy TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def list_tools(self) -> list[dict[str, Any]]:
        with self._db() as db:
            return [dict(row) for row in db.execute("SELECT * FROM harness_tool ORDER BY updated_at DESC, name").fetchall()]

    def list_models(self) -> list[dict[str, Any]]:
        with self._db() as db:
            return [dict(row) for row in db.execute("SELECT * FROM harness_model ORDER BY updated_at DESC, name").fetchall()]

    def create_tool(self, payload: dict[str, Any]) -> dict[str, Any]:
        tool_id = f"tool-{uuid4().hex[:12]}"
        with self._db() as db:
            db.execute("INSERT INTO harness_tool(tool_id,name,source,scope,risk,status,description) VALUES(?,?,?,?,?,?,?)", (tool_id, payload['name'], payload.get('source','mcp'), payload.get('scope','workspace'), payload.get('risk','low'), payload.get('status','configured'), payload.get('description','')))
            return dict(db.execute("SELECT * FROM harness_tool WHERE tool_id=?", (tool_id,)).fetchone())

    def create_model(self, payload: dict[str, Any]) -> dict[str, Any]:
        model_id = f"model-{uuid4().hex[:12]}"
        with self._db() as db:
            db.execute("INSERT INTO harness_model(model_id,name,provider,route,status,cost_policy) VALUES(?,?,?,?,?,?)", (model_id, payload['name'], payload.get('provider',''), payload.get('route','default'), payload.get('status','available'), payload.get('cost_policy','')))
            return dict(db.execute("SELECT * FROM harness_model WHERE model_id=?", (model_id,)).fetchone())

