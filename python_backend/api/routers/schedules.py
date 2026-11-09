"""定时任务（安排任务）路由与调度回调。

页面写入 ScheduledStore，调度线程只读同一张表；到点后复用执行队列提交运行。
"""

from __future__ import annotations

import calendar
import time
from typing import Any, Callable

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...application.execution_service import ExecutionApplicationService
from ...domain.execution import ExecutionRequest
from ...infrastructure.scheduled_store import ScheduledStore


class SchedulePayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=8000)
    agent: str = Field(default='chat', max_length=40)
    intervalMinutes: int = Field(default=60, ge=1, le=60 * 24 * 30)
    enabled: bool = True


class ScheduleUpdatePayload(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    prompt: str | None = Field(default=None, min_length=1, max_length=8000)
    agent: str | None = Field(default=None, max_length=40)
    intervalMinutes: int | None = Field(default=None, ge=1, le=60 * 24 * 30)
    enabled: bool | None = None


def _epoch(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return calendar.timegm(time.strptime(value, "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        return None


def submit_task_run(store: ScheduledStore, service: ExecutionApplicationService,
                   task: dict[str, Any]) -> dict[str, Any]:
    """提交一次定时任务运行；没有可用 Worker 时如实返回失败原因。"""
    conversation_id = f"schedule-{task['task_id']}-{int(time.time())}"
    try:
        run = service.create(ExecutionRequest(conversation_id=conversation_id,
                                             agent=task.get('agent') or 'chat',
                                             query=task['prompt']))
    except Exception as exc:
        return {'ok': False, 'message': str(exc)}
    store.mark_run(task['task_id'], str(run.get('run_id') or ''))
    return {'ok': True, 'run': run}


def create_schedule_runner(store: ScheduledStore, service: ExecutionApplicationService) -> Callable[[], None]:
    """到点任务各跑一次；单个任务失败不影响其它任务。"""

    def run_due_tasks() -> None:
        now = time.time()
        for task in store.list(enabled_only=True):
            last = _epoch(task.get('last_run_at'))
            if last is not None and now - last < int(task.get('interval_minutes') or 60) * 60:
                continue
            submit_task_run(store, service, task)

    return run_due_tasks


def create_schedules_router(store: ScheduledStore, service: ExecutionApplicationService) -> APIRouter:
    router = APIRouter()

    @router.get('/harness/schedules')
    def list_schedules():
        return {'items': store.list()}

    @router.post('/harness/schedules')
    def create_schedule(payload: SchedulePayload):
        task = store.create({'name': payload.name.strip(), 'prompt': payload.prompt.strip(),
                            'agent': payload.agent, 'interval_minutes': payload.intervalMinutes,
                            'enabled': payload.enabled})
        return {'task': task}

    @router.put('/harness/schedules/{task_id}')
    def update_schedule(task_id: str, payload: ScheduleUpdatePayload):
        if not store.get(task_id):
            raise HTTPException(status_code=404, detail='定时任务不存在')
        data = payload.model_dump(exclude_none=True)
        if 'intervalMinutes' in data:
            data['interval_minutes'] = data.pop('intervalMinutes')
        task = store.update(task_id, data)
        return {'task': task}

    @router.delete('/harness/schedules/{task_id}')
    def delete_schedule(task_id: str):
        if not store.delete(task_id):
            raise HTTPException(status_code=404, detail='定时任务不存在')
        return {'deleted': task_id}

    @router.post('/harness/schedules/{task_id}/run')
    def run_schedule_now(task_id: str):
        task = store.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail='定时任务不存在')
        result = submit_task_run(store, service, task)
        if not result['ok']:
            raise HTTPException(status_code=503, detail=result['message'])
        return {'task': store.get(task_id), 'run': result['run']}

    return router
