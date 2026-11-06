from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...infrastructure.resource_store import ResourceStore


class AgentPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    version: str = Field(default="v1", max_length=40)
    model: str = Field(default="auto", max_length=120)
    policy: dict[str, Any] = Field(default_factory=dict)


class WorkspacePayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    repository: str = Field(default="", max_length=500)
    branch: str = Field(default="main", max_length=200)


def create_resource_router(store: ResourceStore) -> APIRouter:
    router = APIRouter()

    @router.get("/harness/agents")
    def list_agents():
        return {"items": store.list_agents()}

    @router.post("/harness/agents")
    def create_agent(payload: AgentPayload):
        return {"agent": store.create_agent({**payload.model_dump(), "policy": json.dumps(payload.policy, ensure_ascii=False)})}

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

    @router.get("/harness/workspaces/{workspace_id}")
    def get_workspace(workspace_id: str):
        item = store.get_workspace(workspace_id)
        if not item:
            raise HTTPException(status_code=404, detail="工作空间不存在")
        return {"workspace": item}

    return router

