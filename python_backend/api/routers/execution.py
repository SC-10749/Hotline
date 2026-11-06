from __future__ import annotations

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


def create_execution_router(
    service: ExecutionApplicationService,
    file_exists: Callable[[str], bool],
) -> APIRouter:
    router = APIRouter()

    def event_stream(run_id: str, last_event_id: int = 0):
        cursor = last_event_id
        heartbeat_at = time.monotonic()
        while True:
            for item in service.queue.events_after(run_id, cursor):
                cursor = item["event_id"]
                yield f"id: {cursor}\ndata: {json.dumps(item['event'], ensure_ascii=False)}\n\n"
                heartbeat_at = time.monotonic()

            status = service.queue.get_status(run_id)
            if status in {"completed", "failed", "cancelled", None}:
                yield "data: [DONE]\n\n"
                return
            if time.monotonic() - heartbeat_at >= 15:
                yield ": keep-alive\n\n"
                heartbeat_at = time.monotonic()
            time.sleep(0.25)

    def submit(agent: str, query: str, conversation_id: str, file_id: str | None,
               last_event_id: str | None):
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
            run = service.submit_or_resume(request, cursor)
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
            return {"run": service.create(request)}
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
    def chat_stream(query: str, conversationId: str, request: Request):
        return submit("chat", query, conversationId, None, request.headers.get("last-event-id"))

    @router.get("/agent/file/stream")
    def file_stream(query: str, conversationId: str, fileId: str, request: Request):
        return submit("file", query, conversationId, fileId, request.headers.get("last-event-id"))

    @router.get("/agent/pptx/stream")
    def pptx_stream(query: str, conversationId: str, request: Request):
        return submit("ppt", query, conversationId, None, request.headers.get("last-event-id"))

    @router.get("/agent/deep/stream")
    def deep_stream(query: str, conversationId: str, request: Request):
        return submit("deep", query, conversationId, None, request.headers.get("last-event-id"))

    @router.get("/agent/skills/stream")
    def skills_stream(query: str, conversationId: str, request: Request, fileId: str | None = None):
        return submit("skills", query, conversationId, fileId, request.headers.get("last-event-id"))

    return router
