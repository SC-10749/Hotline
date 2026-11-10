from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from ...config import settings
from ...infrastructure.registry_store import RegistryConflictError, RegistryStore
from ...llm import probe_model
from ...modules.execution.tools import find_builtin_tool
from ...modules.mcp import probe_stdio_server


class ToolPayload(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    source: str = Field(default='mcp', min_length=1, max_length=160)
    scope: str = Field(default='workspace', min_length=1, max_length=500)
    risk: Literal['low', 'medium', 'high'] = 'low'
    status: str = Field(default='configured', min_length=1, max_length=40)
    description: str = Field(default='', max_length=2000)
    input_schema: dict[str, Any] = Field(default_factory=lambda: {'type': 'object', 'properties': {}})
    approval_policy: Literal['risk-based', 'always'] = 'risk-based'

    @field_validator('name', 'source', 'scope', 'status')
    @classmethod
    def nonempty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('名称、来源、范围和状态不能为空')
        return value

    @field_validator('input_schema')
    @classmethod
    def object_schema(cls, value: dict[str, Any]) -> dict[str, Any]:
        if value.get('type') != 'object':
            raise ValueError('参数 Schema 的根 type 必须是 object')
        if not isinstance(value.get('properties', {}), dict):
            raise ValueError('properties 必须是对象')
        required = value.get('required', [])
        if not isinstance(required, list) or any(not isinstance(key, str) for key in required):
            raise ValueError('required 必须是字符串数组')
        if any(key not in value.get('properties', {}) for key in required):
            raise ValueError('required 中的字段必须在 properties 中声明')
        return value


class ToolUpdatePayload(ToolPayload):
    revision: int = Field(ge=1)


class ModelPayload(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    provider: str = Field(default='', max_length=160)
    route: str = Field(default='default', min_length=1, max_length=160)
    status: str = Field(default='available', min_length=1, max_length=40)
    cost_policy: str = Field(default='', max_length=2000)
    fallback_model_id: str | None = Field(default=None, min_length=1, max_length=160)

    @field_validator('name', 'route', 'status')
    @classmethod
    def nonempty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('模型名称、路由用途和状态不能为空')
        return value


class ModelUpdatePayload(ModelPayload):
    revision: int = Field(ge=1)


def create_registry_router(store: RegistryStore) -> APIRouter:
    router = APIRouter()

    @router.get('/harness/tools')
    def list_tools():
        return {'items': store.list_tools()}

    @router.post('/harness/tools')
    def create_tool(payload: ToolPayload):
        return {'tool': store.create_tool(payload.model_dump())}

    @router.get('/harness/tools/{tool_id}')
    def get_tool(tool_id: str):
        item = store.get_tool(tool_id)
        if not item:
            raise HTTPException(status_code=404, detail='工具不存在')
        return {'tool': item}

    @router.put('/harness/tools/{tool_id}')
    def update_tool(tool_id: str, payload: ToolUpdatePayload):
        try:
            item = store.update_tool(tool_id, payload.model_dump(), payload.revision)
        except RegistryConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if not item:
            raise HTTPException(status_code=404, detail='工具不存在')
        return {'tool': item}

    @router.post('/harness/tools/{tool_id}/test')
    def test_tool(tool_id: str):
        tool = store.get_tool(tool_id)
        if not tool:
            raise HTTPException(status_code=404, detail='工具不存在')
        source = (tool.get('source') or '').strip()
        if source.startswith('mcp:'):
            schema = tool.get('input_schema') or {}
            config = schema.get('mcp') if isinstance(schema, dict) else None
            return probe_stdio_server(config)
        if source in {'', 'builtin'}:
            if find_builtin_tool(tool.get('name') or ''):
                return {'ok': True, 'message': '连接正常', 'details': {'tool': tool.get('name'), 'kind': 'builtin'}}
            return {'ok': False, 'message': '未找到同名内置工具'}
        return {'ok': False, 'message': f'暂不支持的连接方式：{source}'}

    @router.get('/harness/models')
    def list_models():
        return {'items': store.list_models()}

    @router.post('/harness/models')
    def create_model(payload: ModelPayload):
        try:
            return {'model': store.create_model(payload.model_dump())}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get('/harness/models/{model_id}')
    def get_model(model_id: str):
        item = store.get_model(model_id)
        if not item:
            raise HTTPException(status_code=404, detail='模型路由不存在')
        return {'model': item}

    @router.post('/harness/models/{model_id}/test')
    def test_model(model_id: str):
        if not store.get_model(model_id):
            raise HTTPException(status_code=404, detail='模型路由不存在')
        return probe_model(settings)

    @router.get('/harness/models/{model_id}/fallback-chain')
    def fallback_chain(model_id: str):
        if not store.get_model(model_id):
            raise HTTPException(status_code=404, detail='模型路由不存在')
        try:
            chain = store.fallback_chain(model_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {'chain': chain, 'ids': [item['model_id'] for item in chain]}

    @router.put('/harness/models/{model_id}')
    def update_model(model_id: str, payload: ModelUpdatePayload):
        try:
            item = store.update_model(model_id, payload.model_dump(), payload.revision)
        except RegistryConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not item:
            raise HTTPException(status_code=404, detail='模型路由不存在')
        return {'model': item}

    return router

