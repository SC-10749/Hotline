from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4


class ResourceStore:
    """Durable registry for Harness Agent and workspace definitions."""

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
                CREATE TABLE IF NOT EXISTS harness_agent (
                    agent_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    version TEXT NOT NULL DEFAULT 'v1',
                    model TEXT NOT NULL DEFAULT 'auto',
                    policy TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS harness_workspace (
                    workspace_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    repository TEXT NOT NULL DEFAULT '',
                    branch TEXT NOT NULL DEFAULT 'main',
                    status TEXT NOT NULL DEFAULT 'ready',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def list_agents(self) -> list[dict[str, Any]]:
        with self._db() as db:
            return [dict(row) for row in db.execute("SELECT * FROM harness_agent ORDER BY updated_at DESC").fetchall()]

    def create_agent(self, payload: dict[str, Any]) -> dict[str, Any]:
        agent_id = f"agent-{uuid4().hex[:12]}"
        with self._db() as db:
            db.execute(
                "INSERT INTO harness_agent(agent_id,name,description,version,model,policy,status) VALUES(?,?,?,?,?,?,?)",
                (agent_id, payload["name"], payload.get("description", ""), payload.get("version", "v1"), payload.get("model", "auto"), payload.get("policy", "{}"), payload.get("status", "draft")),
            )
        return self.get_agent(agent_id) or {}

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM harness_agent WHERE agent_id=?", (agent_id,)).fetchone()
        return dict(row) if row else None

    def list_workspaces(self) -> list[dict[str, Any]]:
        with self._db() as db:
            return [dict(row) for row in db.execute("SELECT * FROM harness_workspace ORDER BY updated_at DESC").fetchall()]

    def create_workspace(self, payload: dict[str, Any]) -> dict[str, Any]:
        workspace_id = f"workspace-{uuid4().hex[:12]}"
        with self._db() as db:
            db.execute(
                "INSERT INTO harness_workspace(workspace_id,name,repository,branch,status) VALUES(?,?,?,?,?)",
                (workspace_id, payload["name"], payload.get("repository", ""), payload.get("branch", "main"), payload.get("status", "ready")),
            )
        return self.get_workspace(workspace_id) or {}

    def get_workspace(self, workspace_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM harness_workspace WHERE workspace_id=?", (workspace_id,)).fetchone()
        return dict(row) if row else None

