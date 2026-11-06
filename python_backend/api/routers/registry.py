from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ...infrastructure.registry_store import RegistryStore


class ToolPayload(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    source: str = 'mcp'
    scope: str = 'workspace'
    risk: str = 'low'
    status: str = 'configured'
    description: str = ''


class ModelPayload(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    provider: str = ''
    route: str = 'default'
    status: str = 'available'
    cost_policy: str = ''


def create_registry_router(store: RegistryStore) -> APIRouter:
    router = APIRouter()

    @router.get('/harness/tools')
    def list_tools():
        return {'items': store.list_tools()}

    @router.post('/harness/tools')
    def create_tool(payload: ToolPayload):
        return {'tool': store.create_tool(payload.model_dump())}

    @router.get('/harness/models')
    def list_models():
        return {'items': store.list_models()}

    @router.post('/harness/models')
    def create_model(payload: ModelPayload):
        return {'model': store.create_model(payload.model_dump())}

    return router

