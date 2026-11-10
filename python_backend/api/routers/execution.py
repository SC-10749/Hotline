from __future__ import annotations

import asyncio
import json
import time
from typing import Callable

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from ...application.execution_service import ExecutionApplicationService, WorkerUnavailableError
from ...domain.execution import ExecutionRequest
from ...modules.execution import ActiveExecutionError


class ExecutionCreatePayload(BaseModel):
    conversationId: str
    agent: str = "chat"
    query: str
    fileId: str | None = None
    agentId: str | None = None
    workspaceId: str | None = None


def create_execution_router(
    service: ExecutionApplicationService,
    file_exists: Callable[[str], bool],
    pending_approvals: Callable[[], int] | None = None,
    workspace_exists: Callable[[str], bool] | None = None,
) -> APIRouter:
    router = APIRouter()

    @router.get('/harness/overview')
    def harness_overview():
        """总览聚合：今日运行、模型用量与待审批数量，全部来自真实记录。"""
        stats = service.daily_stats()
        stats['pendingApprovals'] = pending_approvals() if pending_approvals else 0
        return stats

    async def event_stream(run_id: str, last_event_id: int = 0, envelope: bool = False):
        cursor = last_event_id
        heartbeat_at = time.monotonic()
        while True:
            # Read terminal state before draining so the final event cannot be skipped.
            run = service.get_run(run_id)
            status = run["status"] if run else None
            for item in service.get_events(run_id, cursor):
                cursor = item["event_id"]
                payload = item if envelope else item["event"]
                yield f"id: {cursor}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                heartbeat_at = time.monotonic()

            if status in {"completed", "failed", "cancelled", None}:
                yield (f"event: done\ndata: {json.dumps({'status': status})}\n\n"
                       if envelope else "data: [DONE]\n\n")
                return
            if time.monotonic() - heartbeat_at >= 15:
                yield ": keep-alive\n\n"
                heartbeat_at = time.monotonic()
            await asyncio.sleep(0.08)

    def submit(agent: str, query: str, conversation_id: str, file_id: str | None,
               last_event_id: str | None, workspace_id: str = ''):
        workspace_id = workspace_id.strip()
        if workspace_id and (len(workspace_id) > 255 or (workspace_exists and not workspace_exists(workspace_id))):
            raise HTTPException(404, '工作区不存在')
        try:
            request = ExecutionRequest(
                conversation_id=(conversation_id or "").strip(),
                agent=agent,
                query=(query or "").strip(),
                file_id=(file_id or "").strip() or None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if agent == "file" and not file_exists(request.file_id or ""):
            raise HTTPException(status_code=404, detail="文件或文档不存在")
        try:
            cursor = max(0, int(last_event_id or "0"))
        except ValueError:
            cursor = 0
        try:
            run = service.submit_or_resume(request, cursor, workspace_id.strip())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        except WorkerUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ActiveExecutionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return StreamingResponse(
            event_stream(run["run_id"], cursor),
            media_type="text/event-stream; charset=utf-8",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                     "X-Execution-Run-Id": run["run_id"]},
        )

    @router.get("/agent/stop")
    def agent_stop(conversationId: str = Query(...)):
        stopped = service.cancel(conversationId)
        return {"success": stopped, "message": "已停止执行" if stopped else "没有找到正在执行的任务"}

    @router.post("/execution/runs")
    def create_run(payload: ExecutionCreatePayload):
        if payload.workspaceId and (len(payload.workspaceId) > 255 or (workspace_exists and not workspace_exists(payload.workspaceId.strip()))):
            raise HTTPException(404, '工作区不存在')
        try:
            request = ExecutionRequest(
                conversation_id=payload.conversationId.strip(),
                agent=payload.agent.strip(),
                query=payload.query.strip(),
                file_id=(payload.fileId or "").strip() or None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if request.file_id and not file_exists(request.file_id):
            raise HTTPException(status_code=404, detail="文件或文档不存在")
        try:
            return {"run": service.create(request, (payload.agentId or "").strip(), (payload.workspaceId or "").strip())}
        except WorkerUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ActiveExecutionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get("/execution/runs")
    def list_runs(
        status: str | None = None,
        search: str | None = None,
        limit: int = Query(100, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        items, total = service.list_runs(status=status, search=search, limit=limit, offset=offset)
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    @router.get("/execution/runs/{run_id}")
    def get_run(run_id: str):
        run = service.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="运行不存在")
        return {"run": run}

    @router.get("/execution/runs/{run_id}/events")
    def get_run_events(run_id: str, after: int = Query(0, ge=0)):
        if not service.get_run(run_id):
            raise HTTPException(status_code=404, detail="运行不存在")
        return {"items": service.get_events(run_id, after)}

    @router.get('/execution/runs/{run_id}/context')
    def get_run_context(run_id: str):
        if not service.get_run(run_id):
            raise HTTPException(status_code=404, detail='运行不存在')
        return {'items': service.get_context_snapshots(run_id)}

    @router.get("/execution/runs/{run_id}/stream")
    def stream_run_events(run_id: str, request: Request, after: int = Query(0, ge=0)):
        if not service.get_run(run_id):
            raise HTTPException(status_code=404, detail="运行不存在")
        try:
            cursor = max(after, int(request.headers.get("last-event-id", "0")))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="事件游标无效") from exc
        return StreamingResponse(
            event_stream(run_id, cursor, envelope=True),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.post("/execution/runs/{run_id}/cancel")
    def cancel_run(run_id: str):
        if not service.get_run(run_id):
            raise HTTPException(status_code=404, detail="运行不存在")
        cancelled = service.cancel_run(run_id)
        return {"success": cancelled, "message": "已请求停止" if cancelled else "运行已结束"}

    @router.post("/execution/runs/{run_id}/retry")
    def retry_run(run_id: str):
        if not service.get_run(run_id):
            raise HTTPException(status_code=404, detail="运行不存在")
        try:
            run = service.retry_run(run_id)
        except WorkerUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ActiveExecutionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if not run:
            raise HTTPException(status_code=409, detail="只有已结束的运行可以重试")
        return {"run": run}

    @router.get("/agent/chat/stream")
    def chat_stream(query: str, conversationId: str, request: Request, workspaceId: str = ''):
        return submit("chat", query, conversationId, None, request.headers.get("last-event-id"), workspaceId)

    @router.get("/agent/file/stream")
    def file_stream(query: str, conversationId: str, fileId: str, request: Request, workspaceId: str = ''):
        return submit("file", query, conversationId, fileId, request.headers.get("last-event-id"), workspaceId)

    @router.get("/agent/pptx/stream")
    def pptx_stream(query: str, conversationId: str, request: Request, workspaceId: str = ''):
        return submit("ppt", query, conversationId, None, request.headers.get("last-event-id"), workspaceId)

    @router.get("/agent/deep/stream")
    def deep_stream(query: str, conversationId: str, request: Request, workspaceId: str = ''):
        return submit("deep", query, conversationId, None, request.headers.get("last-event-id"), workspaceId)

    @router.get("/agent/skills/stream")
    def skills_stream(query: str, conversationId: str, request: Request, fileId: str | None = None,
                      workspaceId: str = ''):
        return submit("skills", query, conversationId, fileId, request.headers.get("last-event-id"), workspaceId)

    return router
