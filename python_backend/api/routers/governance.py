from __future__ import annotations

import csv
import io
import json
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ...infrastructure.governance_store import ApprovalStateError, GovernanceStore
from ...infrastructure.notification_store import NotificationStore


AUDIT_COLUMNS = ("request_id", "run_id", "tool", "risk", "status", "reason", "operator", "created_at", "decided_at")


class ApprovalCreatePayload(BaseModel):
    runId: str
    tool: str
    risk: str = 'high'
    detail: str = ''
    timeoutSeconds: int | None = Field(default=None, ge=1, le=86400)


class ApprovalDecisionPayload(BaseModel):
    decision: str
    reason: str = Field(default='', max_length=500)
    operator: str | None = None


class ApprovalBatchDecisionPayload(BaseModel):
    requestIds: list[str] = Field(default_factory=list)
    decision: str
    reason: str = Field(default='', max_length=500)
    operator: str | None = None


class DrainPayload(BaseModel):
    draining: bool = True


def post_webhook(url: str, payload: dict[str, Any], timeout: float = 5.0) -> tuple[bool, str]:
    """Best-effort webhook delivery; failures never break the approval decision."""
    import urllib.error
    import urllib.request

    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    request = urllib.request.Request(url, data=body, method='POST',
                                     headers={'Content-Type': 'application/json; charset=utf-8'})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 300, f'HTTP {response.status}'
    except urllib.error.HTTPError as exc:
        return False, f'HTTP {exc.code}'
    except Exception as exc:
        return False, type(exc).__name__


def create_governance_router(workers: Callable[[], list[dict[str, Any]]], store: GovernanceStore,
                            set_worker_state: Callable[[str, str], dict[str, Any] | None] | None = None,
                            harness_settings: Callable[[], dict[str, Any]] | None = None,
                            notifications: NotificationStore | None = None,
                            worker_errors: Callable[[str, int], list[dict[str, Any]]] | None = None) -> APIRouter:
    router = APIRouter()

    def approval_timeout() -> int:
        if harness_settings is None:
            return 3600
        return int(harness_settings().get('approvalTimeoutSeconds') or 3600)

    def notify_decision(approval: dict[str, Any], decision: str, operator: str) -> dict[str, Any] | None:
        """记录审批决定通知；外发失败不影响决定本身。"""
        if notifications is None or harness_settings is None:
            return None
        config = harness_settings()
        if not config.get('approvalNotifyEnabled', True):
            return None
        payload = {
            'event': 'approval_decided',
            'requestId': approval.get('request_id', ''),
            'runId': approval.get('run_id', ''),
            'tool': approval.get('tool', ''),
            'risk': approval.get('risk', ''),
            'decision': decision,
            'operator': operator,
            'reason': str(approval.get('reason') or '')[:200],
            'decidedAt': approval.get('decided_at') or '',
        }
        record = notifications.record(request_id=approval.get('request_id', ''), event='approval_decided',
                                     payload=payload, channel='local', status='recorded')
        webhook = str(config.get('notificationWebhookUrl') or '').strip()
        if webhook:
            ok, detail = post_webhook(webhook, payload)
            record = notifications.record(request_id=approval.get('request_id', ''), event='approval_decided',
                                         payload=payload, channel='webhook',
                                         status='delivered' if ok else 'failed', detail=detail)
        return record

    @router.get('/harness/machines')
    def list_machines():
        return {'items': workers()}

    @router.get('/harness/machines/{worker_id}/errors')
    def machine_errors(worker_id: str, limit: int = Query(20, ge=1, le=200)):
        """节点错误日志：只读返回该节点执行失败的运行与错误事件。"""
        if worker_errors is None:
            return {'items': []}
        return {'items': worker_errors(worker_id, limit)}

    @router.post('/harness/machines/{worker_id}/drain')
    def drain_machine(worker_id: str, payload: DrainPayload):
        if set_worker_state is None:
            raise HTTPException(status_code=503, detail='运行时状态未接入')
        state = 'draining' if payload.draining else 'online'
        worker = set_worker_state(worker_id, state)
        if not worker:
            raise HTTPException(status_code=404, detail='Worker 不存在')
        return {'worker': worker}

    @router.get('/harness/approvals')
    def list_approvals(status: str | None = Query(None)):
        store.expire_pending()
        return {'items': store.list(status)}

    @router.get('/harness/approvals/audit')
    def export_audit(status: str | None = Query(None)):
        store.expire_pending()
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator='\n')
        writer.writerow(AUDIT_COLUMNS)
        for item in store.list(status):
            writer.writerow([item.get(column) or '' for column in AUDIT_COLUMNS])
        return Response(
            content='\ufeff' + buffer.getvalue(),
            media_type='text/csv; charset=utf-8',
            headers={'Content-Disposition': 'attachment; filename="harness-approvals.csv"'},
        )

    @router.post('/harness/approvals/decide-batch')
    def decide_batch(payload: ApprovalBatchDecisionPayload):
        items = []
        failed = []
        for request_id in payload.requestIds:
            try:
                item = store.decide(request_id, payload.decision, payload.reason,
                                    payload.operator or 'harness-operator')
            except ApprovalStateError as exc:
                failed.append({'requestId': request_id, 'reason': str(exc)})
                continue
            except ValueError as exc:
                failed.append({'requestId': request_id, 'reason': str(exc)})
                continue
            if not item:
                failed.append({'requestId': request_id, 'reason': '审批请求不存在'})
                continue
            notify_decision(item, payload.decision, payload.operator or 'harness-operator')
            items.append(item)
        return {'items': items, 'failed': failed}

    @router.get('/harness/approvals/notifications')
    def list_notifications(requestId: str | None = Query(None), limit: int = Query(100, ge=1, le=500)):
        if notifications is None:
            return {'items': []}
        return {'items': notifications.list(requestId, limit)}

    @router.get('/harness/approvals/{request_id}')
    def get_approval(request_id: str):
        store.expire_pending()
        item = store.get(request_id)
        if not item:
            raise HTTPException(status_code=404, detail='审批请求不存在')
        return {'approval': item}

    @router.post('/harness/approvals')
    def create_approval(payload: ApprovalCreatePayload):
        return {'approval': store.create({
            'run_id': payload.runId,
            'tool': payload.tool,
            'risk': payload.risk,
            'detail': payload.detail,
            'timeout_seconds': payload.timeoutSeconds or approval_timeout(),
        })}

    @router.post('/harness/approvals/{request_id}/decision')
    def decide_approval(request_id: str, payload: ApprovalDecisionPayload):
        try:
            item = store.decide(request_id, payload.decision, payload.reason,
                                payload.operator or 'harness-operator')
        except ApprovalStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not item:
            raise HTTPException(status_code=404, detail='审批请求不存在')
        notify_decision(item, payload.decision, payload.operator or 'harness-operator')
        return {'approval': item}

    return router
