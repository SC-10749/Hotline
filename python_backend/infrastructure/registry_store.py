from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4


class RegistryConflictError(ValueError):
    pass


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
            db.execute('BEGIN IMMEDIATE')
            try:
                columns = {row['name'] for row in db.execute('PRAGMA table_info(harness_tool)')}
                additions = {
                    'input_schema': "TEXT NOT NULL DEFAULT '{\"type\":\"object\",\"properties\":{}}'",
                    'approval_policy': "TEXT NOT NULL DEFAULT 'risk-based'",
                    'revision': 'INTEGER NOT NULL DEFAULT 1',
                }
                for name, definition in additions.items():
                    if name not in columns:
                        db.execute(f'ALTER TABLE harness_tool ADD COLUMN {name} {definition}')
                model_columns = {row['name'] for row in db.execute('PRAGMA table_info(harness_model)')}
                for name, definition in {'revision': 'INTEGER NOT NULL DEFAULT 1', 'fallback_model_id': 'TEXT'}.items():
                    if name not in model_columns:
                        db.execute(f'ALTER TABLE harness_model ADD COLUMN {name} {definition}')
                db.commit()
            except Exception:
                db.rollback()
                raise

    @staticmethod
    def _tool_dict(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item['input_schema'] = json.loads(item['input_schema'])
        return item

    def list_tools(self) -> list[dict[str, Any]]:
        with self._db() as db:
            return [self._tool_dict(row) for row in db.execute("SELECT * FROM harness_tool ORDER BY updated_at DESC, name").fetchall()]

    def list_models(self) -> list[dict[str, Any]]:
        with self._db() as db:
            return [dict(row) for row in db.execute("SELECT * FROM harness_model ORDER BY updated_at DESC, name").fetchall()]

    def create_tool(self, payload: dict[str, Any]) -> dict[str, Any]:
        tool_id = f"tool-{uuid4().hex[:12]}"
        with self._db() as db:
            db.execute(
                '''INSERT INTO harness_tool(tool_id,name,source,scope,risk,status,description,input_schema,approval_policy)
                   VALUES(?,?,?,?,?,?,?,?,?)''',
                (tool_id, payload['name'], payload.get('source','mcp'), payload.get('scope','workspace'),
                 payload.get('risk','low'), payload.get('status','configured'), payload.get('description',''),
                 json.dumps(payload.get('input_schema', {'type': 'object', 'properties': {}}), ensure_ascii=False),
                 payload.get('approval_policy', 'risk-based')),
            )
            return self._tool_dict(db.execute('SELECT * FROM harness_tool WHERE tool_id=?', (tool_id,)).fetchone())

    def get_tool(self, tool_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute('SELECT * FROM harness_tool WHERE tool_id=?', (tool_id,)).fetchone()
        return self._tool_dict(row) if row else None

    def get_tool_by_name(self, name: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute('SELECT * FROM harness_tool WHERE name=? ORDER BY updated_at DESC LIMIT 1', (name,)).fetchone()
        return self._tool_dict(row) if row else None

    def list_mcp_servers(self) -> list[dict[str, Any]]:
        """登记了 MCP 连接配置的工具，即已知的 MCP 服务器。"""
        servers = []
        for tool in self.list_tools():
            schema = tool.get('input_schema') or {}
            if isinstance(schema, dict) and isinstance(schema.get('mcp'), dict):
                servers.append({'tool_id': tool['tool_id'], 'name': tool['name'],
                                'source': tool['source'], 'status': tool['status']})
        return servers

    def update_tool(self, tool_id: str, payload: dict[str, Any], revision: int) -> dict[str, Any] | None:
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                row = db.execute('SELECT revision FROM harness_tool WHERE tool_id=?', (tool_id,)).fetchone()
                if not row:
                    db.commit()
                    return None
                if row['revision'] != revision:
                    raise RegistryConflictError('工具已被修改，请重新打开详情后再保存')
                db.execute(
                    '''UPDATE harness_tool SET name=?,source=?,scope=?,risk=?,status=?,description=?,
                       input_schema=?,approval_policy=?,revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE tool_id=?''',
                    (payload['name'], payload['source'], payload['scope'], payload['risk'], payload['status'],
                     payload['description'], json.dumps(payload['input_schema'], ensure_ascii=False), payload['approval_policy'], tool_id),
                )
                result = self._tool_dict(db.execute('SELECT * FROM harness_tool WHERE tool_id=?', (tool_id,)).fetchone())
                db.commit()
                return result
            except Exception:
                db.rollback()
                raise

    def create_model(self, payload: dict[str, Any]) -> dict[str, Any]:
        model_id = f"model-{uuid4().hex[:12]}"
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                self._validate_fallback(db, model_id, payload.get('fallback_model_id'))
                db.execute(
                    '''INSERT INTO harness_model(model_id,name,provider,route,status,cost_policy,fallback_model_id)
                       VALUES(?,?,?,?,?,?,?)''',
                    (model_id, payload['name'], payload.get('provider',''), payload.get('route','default'),
                     payload.get('status','available'), payload.get('cost_policy',''), payload.get('fallback_model_id')),
                )
                result = dict(db.execute('SELECT * FROM harness_model WHERE model_id=?', (model_id,)).fetchone())
                db.commit()
                return result
            except Exception:
                db.rollback()
                raise

    @staticmethod
    def _validate_fallback(db: sqlite3.Connection, model_id: str, fallback_id: str | None) -> None:
        visited = {model_id}
        while fallback_id:
            if fallback_id in visited:
                raise ValueError('备用模型引用形成循环，请调整 fallback')
            visited.add(fallback_id)
            row = db.execute('SELECT fallback_model_id FROM harness_model WHERE model_id=?', (fallback_id,)).fetchone()
            if not row:
                raise ValueError('备用模型不存在，请刷新目录后重新选择')
            fallback_id = row['fallback_model_id']

    def get_model(self, model_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute('SELECT * FROM harness_model WHERE model_id=?', (model_id,)).fetchone()
        return dict(row) if row else None

    def fallback_chain(self, model_id: str) -> list[dict[str, Any]]:
        """主模型沿 fallback_model_id 展开的备用链，顺序即回退顺序。"""
        chain: list[dict[str, Any]] = []
        visited: set[str] = set()
        current: str | None = model_id
        while current:
            if current in visited:
                raise ValueError('备用模型引用形成循环，请调整 fallback')
            visited.add(current)
            row = self.get_model(current)
            if not row:
                break
            chain.append({'model_id': row['model_id'], 'name': row['name'],
                           'provider': row['provider'], 'route': row['route']})
            current = row.get('fallback_model_id')
        return chain

    def update_model(self, model_id: str, payload: dict[str, Any], revision: int) -> dict[str, Any] | None:
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                row = db.execute('SELECT revision FROM harness_model WHERE model_id=?', (model_id,)).fetchone()
                if not row:
                    db.commit()
                    return None
                if row['revision'] != revision:
                    raise RegistryConflictError('模型路由已被修改，请重新打开详情后再保存')
                self._validate_fallback(db, model_id, payload.get('fallback_model_id'))
                db.execute(
                    '''UPDATE harness_model SET name=?,provider=?,route=?,status=?,cost_policy=?,fallback_model_id=?,
                       revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE model_id=?''',
                    (payload['name'], payload['provider'], payload['route'], payload['status'],
                     payload['cost_policy'], payload.get('fallback_model_id'), model_id),
                )
                result = dict(db.execute('SELECT * FROM harness_model WHERE model_id=?', (model_id,)).fetchone())
                db.commit()
                return result
            except Exception:
                db.rollback()
                raise

