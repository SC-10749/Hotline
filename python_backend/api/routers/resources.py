from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from ...config import settings
from ...infrastructure.resource_store import (
    CHANGE_TYPES,
    GIT_URL_PATTERN,
    CheckoutError,
    ResourceConflictError,
    ResourceStore,
)
from python_backend.modules.skills.catalog import Catalog

DIFF_FIELDS = ('name', 'description', 'version', 'model', 'policy', 'tools', 'skills', 'enabled')


class AgentPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    version: str = Field(default="v1", max_length=40)
    model: str = Field(default="auto", max_length=120)
    policy: dict[str, Any] = Field(default_factory=dict)
    tools: list[str] | None = None

    @field_validator('name', 'version', 'model')
    @classmethod
    def nonempty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('名称、版本和模型路由不能为空')
        return value


class AgentUpdatePayload(AgentPayload):
    revision: int = Field(ge=1)


class AgentStatusPayload(BaseModel):
    enabled: bool


class SkillBindingPayload(BaseModel):
    skillIds: list[str] = Field(default_factory=list)


class WorkspacePayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    repository: str = Field(default="", max_length=500)
    branch: str = Field(default="main", max_length=200)

    @field_validator('name', 'branch')
    @classmethod
    def nonempty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('名称和分支不能为空')
        return value


class WorkspaceUpdatePayload(WorkspacePayload):
    revision: int = Field(ge=1)


class CatalogBindPayload(BaseModel):
    project: str | None = Field(default=None, max_length=200)
    name: str = Field(default='', max_length=200)
    version: str = Field(default='', max_length=100)
    percentage: int | None = Field(default=None, ge=0, le=100)

    @field_validator('name', 'version')
    @classmethod
    def trimmed(cls, value: str) -> str:
        return value.strip()


class CatalogUnbindPayload(BaseModel):
    project: str | None = Field(default=None, max_length=200)
    name: str = Field(default='', max_length=200)

    @field_validator('name')
    @classmethod
    def trimmed(cls, value: str) -> str:
        return value.strip()


class WorkspaceChangePayload(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    changeType: str = Field(default='tracked', max_length=20)
    snapshotId: str | None = None

    @field_validator('path')
    @classmethod
    def nonempty_path(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('文件路径不能为空')
        return value


def _normalize(field: str, value: Any) -> Any:
    """Normalize a snapshot field so key order never shows up as a difference."""
    if field == 'policy':
        try:
            parsed = json.loads(value or '{}')
        except (TypeError, ValueError):
            return value
        return parsed if isinstance(parsed, dict) else {'value': parsed}
    if field in ('tools', 'skills'):
        try:
            parsed = json.loads(value or '[]')
        except (TypeError, ValueError):
            parsed = []
        return sorted(parsed) if isinstance(parsed, list) else []
    if field == 'enabled':
        return bool(value)
    return value


def diff_versions(base: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    changed: list[dict[str, Any]] = []
    added: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    for field in DIFF_FIELDS:
        base_value = _normalize(field, base.get(field))
        target_value = _normalize(field, target.get(field))
        if base_value == target_value:
            continue
        changed.append({'field': field, 'base': base_value, 'target': target_value})
        if isinstance(base_value, list) and isinstance(target_value, list):
            added.extend({'field': field, 'value': value} for value in target_value if value not in base_value)
            removed.extend({'field': field, 'value': value} for value in base_value if value not in target_value)
    return {'changed': changed, 'added': added, 'removed': removed}


def _catalog_call(action: str, args: dict[str, Any]) -> dict[str, Any]:
    """按次打开技能目录，避免长时间持有连接。"""
    catalog = Catalog(settings.skill_catalog_db)
    try:
        return catalog.call(action, args)
    finally:
        catalog.db.close()


def _execution_runs(column: str, value: str, limit: int) -> list[dict[str, Any]]:
    """Read-only view over the execution database; a missing database is simply empty."""
    path = Path(settings.execution_db_path)
    if not path.exists():
        return []
    absolute = path.resolve().as_posix()
    if not absolute.startswith('/'):
        absolute = '/' + absolute
    uri = 'file://' + quote(absolute, safe='/:') + '?mode=ro'
    try:
        db = sqlite3.connect(uri, uri=True, timeout=10)
    except sqlite3.Error:
        return []
    try:
        db.row_factory = sqlite3.Row
        available = {row['name'] for row in db.execute('PRAGMA table_info(execution_run)')}
        if column not in available:
            return []
        columns = [name for name in ('run_id', 'conversation_id', 'agent', 'query', 'status', 'created_at',
                                     'started_at', 'finished_at', 'error', 'agent_id', 'workspace_id')
                   if name in available]
        rows = db.execute(
            f"SELECT {','.join(columns)} FROM execution_run WHERE {column}=?"
            " ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (value, limit)).fetchall()
    except sqlite3.Error:
        return []
    finally:
        db.close()
    return [dict(row) for row in rows]


def create_resource_router(store: ResourceStore) -> APIRouter:
    router = APIRouter()

    @router.get("/harness/agents")
    def list_agents():
        return {"items": store.list_agents()}

    @router.post("/harness/agents")
    def create_agent(payload: AgentPayload):
        values = {**payload.model_dump(), "policy": json.dumps(payload.policy, ensure_ascii=False)}
        return {"agent": store.create_agent(values)}

    @router.get("/harness/workspaces")
    def list_workspaces():
        return {"items": store.list_workspaces()}

    @router.post("/harness/workspaces")
    def create_workspace(payload: WorkspacePayload):
        return {"workspace": store.create_workspace(payload.model_dump())}

    @router.get("/harness/agents/{agent_id}")
    def get_agent(agent_id: str):
        item = store.get_agent(agent_id)
        if not item:
            raise HTTPException(status_code=404, detail="Agent 不存在")
        return {"agent": item}

    @router.put('/harness/agents/{agent_id}')
    def update_agent(agent_id: str, payload: AgentUpdatePayload):
        values = {**payload.model_dump(), 'policy': json.dumps(payload.policy, ensure_ascii=False)}
        try:
            item = store.update_agent(agent_id, values, payload.revision)
        except ResourceConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if not item:
            raise HTTPException(status_code=404, detail='Agent 不存在')
        return {'agent': item}

    @router.put('/harness/agents/{agent_id}/status')
    def set_agent_status(agent_id: str, payload: AgentStatusPayload):
        item = store.set_agent_status(agent_id, payload.enabled)
        if not item:
            raise HTTPException(status_code=404, detail='Agent 不存在')
        return {'agent': item}

    @router.get('/harness/agents/{agent_id}/versions')
    def list_agent_versions(agent_id: str):
        if not store.get_agent(agent_id):
            raise HTTPException(status_code=404, detail='Agent 不存在')
        return {'items': store.list_agent_versions(agent_id)}

    @router.get('/harness/agents/{agent_id}/diff')
    def diff_agent(agent_id: str, base: str = Query(...), target: str = Query(...)):
        if not store.get_agent(agent_id):
            raise HTTPException(status_code=404, detail='Agent 不存在')
        base_row = store.get_agent_version(agent_id, base)
        target_row = store.get_agent_version(agent_id, target)
        if not base_row or not target_row:
            raise HTTPException(status_code=404, detail='版本快照不存在')
        return diff_versions(base_row, target_row)

    @router.post('/harness/agents/{agent_id}/skills')
    def bind_agent_skills(agent_id: str, payload: SkillBindingPayload):
        item = store.set_agent_skills(agent_id, [value.strip() for value in payload.skillIds if value.strip()])
        if not item:
            raise HTTPException(status_code=404, detail='Agent 不存在')
        return {'agent': item}

    @router.delete('/harness/agents/{agent_id}/skills/{skill_id}')
    def unbind_agent_skill(agent_id: str, skill_id: str):
        current = store.get_agent(agent_id)
        if not current:
            raise HTTPException(status_code=404, detail='Agent 不存在')
        remaining = [value for value in current['skills'] if value != skill_id]
        item = store.set_agent_skills(agent_id, remaining)
        return {'agent': item or current}

    @router.get('/harness/agents/{agent_id}/runs')
    def list_agent_runs(agent_id: str, limit: int = Query(50, ge=1, le=200)):
        if not store.get_agent(agent_id):
            raise HTTPException(status_code=404, detail='Agent 不存在')
        return {'items': _execution_runs('agent_id', agent_id, limit), 'limit': limit}

    @router.get("/harness/workspaces/{workspace_id}")
    def get_workspace(workspace_id: str):
        item = store.get_workspace(workspace_id)
        if not item:
            raise HTTPException(status_code=404, detail="工作空间不存在")
        return {"workspace": item}

    @router.put('/harness/workspaces/{workspace_id}')
    def update_workspace(workspace_id: str, payload: WorkspaceUpdatePayload):
        try:
            item = store.update_workspace(workspace_id, payload.model_dump(), payload.revision)
        except ResourceConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if not item:
            raise HTTPException(status_code=404, detail='工作空间不存在')
        return {'workspace': item}

    @router.post('/harness/workspaces/{workspace_id}/checkout')
    def checkout_workspace(workspace_id: str):
        workspace = store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail='工作空间不存在')
        repository = (workspace.get('repository') or '').strip()
        if not repository:
            raise HTTPException(status_code=400, detail='工作空间没有配置仓库地址')
        if not GIT_URL_PATTERN.match(repository):
            local = store.resolve_local_repository(repository)
            if local is not None:
                return JSONResponse(status_code=400, content={
                    'detail': '本地目录无需检出',
                    'directory': local.as_posix(),
                    'files': len(list(local.iterdir())),
                })
            raise HTTPException(status_code=400, detail='仓库地址无法识别，请填写本地目录或 git 地址')
        try:
            result = store.checkout_workspace(workspace_id, repository, workspace.get('branch') or 'main')
        except CheckoutError as exc:
            store.save_workspace_checkout(workspace_id, repository, workspace.get('branch') or '',
                                         '', '', 'error', str(exc))
            return JSONResponse(status_code=400, content={'detail': str(exc), 'reason': exc.reason, **exc.detail})
        return result

    @router.get('/harness/workspaces/{workspace_id}/checkout')
    def get_workspace_checkout(workspace_id: str):
        if not store.get_workspace(workspace_id):
            raise HTTPException(status_code=404, detail='工作空间不存在')
        checkout = store.get_workspace_checkout(workspace_id)
        if not checkout:
            return {'checkedOut': False, 'branch': '', 'commit': '', 'checkoutDir': '',
                    'checkedAt': '', 'message': ''}
        return {
            'checkedOut': checkout['status'] == 'checked_out',
            'branch': checkout['branch'],
            'commit': checkout['commit'],
            'checkoutDir': checkout['checkout_dir'],
            'checkedAt': checkout['checked_at'],
            'message': checkout['message'],
        }

    @router.post('/harness/skills/catalog/bind')
    def bind_catalog_skill(payload: CatalogBindPayload):
        project = payload.project or settings.skill_project
        if not payload.name:
            raise HTTPException(status_code=400, detail='技能名称不能为空')
        if not payload.version:
            raise HTTPException(status_code=400, detail='技能版本不能为空')
        args = {'project': project, 'name': payload.name, 'version': payload.version}
        if payload.percentage is not None:
            args['percentage'] = payload.percentage
        try:
            result = _catalog_call('bind', args)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        summary = _catalog_call('catalog_summary', {'project': project})
        return {'binding': result, 'bindings': summary.get('bindings', [])}

    @router.delete('/harness/skills/catalog/bind')
    def unbind_catalog_skill(payload: CatalogUnbindPayload):
        project = payload.project or settings.skill_project
        if not payload.name:
            raise HTTPException(status_code=400, detail='技能名称不能为空')
        try:
            result = _catalog_call('unbind', {'project': project, 'name': payload.name})
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        summary = _catalog_call('catalog_summary', {'project': project})
        return {'binding': result, 'bindings': summary.get('bindings', [])}

    @router.post('/harness/workspaces/{workspace_id}/snapshots')
    def create_workspace_snapshot(workspace_id: str):
        workspace = store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail='工作空间不存在')
        try:
            snapshot = store.create_workspace_snapshot(workspace_id, workspace['repository'], workspace['branch'])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {'snapshot': snapshot}

    @router.get('/harness/workspaces/{workspace_id}/snapshots')
    def list_workspace_snapshots(workspace_id: str):
        if not store.get_workspace(workspace_id):
            raise HTTPException(status_code=404, detail='工作空间不存在')
        return {'items': store.list_workspace_snapshots(workspace_id)}

    @router.get('/harness/workspaces/{workspace_id}/snapshots/{snapshot_id}/changes')
    def list_workspace_snapshot_changes(workspace_id: str, snapshot_id: str):
        snapshot = store.get_workspace_snapshot(snapshot_id)
        if not snapshot or snapshot['workspace_id'] != workspace_id:
            raise HTTPException(status_code=404, detail='快照不存在')
        return {'items': store.list_workspace_changes(workspace_id, snapshot_id)}

    @router.post('/harness/workspaces/{workspace_id}/changes')
    def create_workspace_change(workspace_id: str, payload: WorkspaceChangePayload):
        if not store.get_workspace(workspace_id):
            raise HTTPException(status_code=404, detail='工作空间不存在')
        if payload.changeType not in CHANGE_TYPES:
            raise HTTPException(status_code=400, detail='变更类型不合法')
        if payload.snapshotId and not store.get_workspace_snapshot(payload.snapshotId):
            raise HTTPException(status_code=404, detail='快照不存在')
        change = store.create_workspace_change(workspace_id, payload.path, payload.changeType, payload.snapshotId)
        return {'change': change}

    @router.get('/harness/workspaces/{workspace_id}/runs')
    def list_workspace_runs(workspace_id: str, limit: int = Query(50, ge=1, le=200)):
        if not store.get_workspace(workspace_id):
            raise HTTPException(status_code=404, detail='工作空间不存在')
        return {'items': _execution_runs('workspace_id', workspace_id, limit), 'limit': limit}

    return router
