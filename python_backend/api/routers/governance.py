from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ...infrastructure.governance_store import GovernanceStore


class ApprovalCreatePayload(BaseModel):
    runId: str
    tool: str
    risk: str = 'high'
    detail: str = ''


class ApprovalDecisionPayload(BaseModel):
    decision: str
    reason: str = Field(default='', max_length=500)


def create_governance_router(workers: Callable[[], list[dict[str, Any]]], store: GovernanceStore) -> APIRouter:
    router = APIRouter()

    @router.get('/harness/machines')
    def list_machines():
        return {'items': workers()}

    @router.get('/harness/approvals')
    def list_approvals(status: str | None = Query(None)):
        return {'items': store.list(status)}

    @router.get('/harness/approvals/{request_id}')
    def get_approval(request_id: str):
        item = store.get(request_id)
        if not item:
            raise HTTPException(status_code=404, detail='审批请求不存在')
        return {'approval': item}

    @router.post('/harness/approvals')
    def create_approval(payload: ApprovalCreatePayload):
        return {'approval': store.create({'run_id': payload.runId, 'tool': payload.tool, 'risk': payload.risk, 'detail': payload.detail})}

    @router.post('/harness/approvals/{request_id}/decision')
    def decide_approval(request_id: str, payload: ApprovalDecisionPayload):
        item = store.decide(request_id, payload.decision, payload.reason)
        if not item:
            raise HTTPException(status_code=404, detail='审批请求不存在')
        return {'approval': item}

    return router

