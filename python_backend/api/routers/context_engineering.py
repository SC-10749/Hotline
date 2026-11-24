from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ...modules.context_engineering.privacy import sanitize_text, sanitize_value
from ...modules.context_engineering.service import ContextService
from ...modules.memory.store import MemoryConflict


class TaskFact(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    quote: str = Field(min_length=1, max_length=2000)
    sourceId: str = Field(min_length=1, max_length=255)
    status: Literal['active', 'completed', 'cancelled'] = 'active'


class TaskUpdate(BaseModel):
    revision: int = Field(ge=0)
    goal: str = Field(min_length=1, max_length=4000)
    constraints: list[TaskFact] = Field(default_factory=list, max_length=64)
    decisions: list[TaskFact] = Field(default_factory=list, max_length=64)
    pending: list[TaskFact] = Field(default_factory=list, max_length=64)


class ForgetMemory(BaseModel):
    uri: str = Field(min_length=1, max_length=2048)


def create_context_router(service: ContextService, delete_session=None) -> APIRouter:
    router = APIRouter(prefix='/harness/context', tags=['context-engineering'])

    def require(conversation_id):
        scope = service.store.conversation(conversation_id)
        if not scope:
            raise HTTPException(404, '会话上下文不存在')
        return scope

    @router.get('/{conversation_id}')
    def context_status(conversation_id: str):
        status = service.status(conversation_id)
        if status['task'] is None and not status['deliveries']:
            raise HTTPException(404, '会话上下文不存在')
        return sanitize_value(status)

    @router.put('/{conversation_id}/task')
    def update_task(conversation_id: str, payload: TaskUpdate):
        scope = require(conversation_id)
        for fact in payload.constraints + payload.decisions + payload.pending:
            source = service.store.source(conversation_id, fact.sourceId)
            if not source or (fact.quote not in source['question'] and fact.quote not in sanitize_text(source['question'])):
                raise HTTPException(400, '任务事实必须引用本会话的用户原话')
        state = {**scope['state'], **payload.model_dump(exclude={'revision'})}
        try:
            return {'task': sanitize_value(service.store.put_state(conversation_id, state, payload.revision))}
        except MemoryConflict as exc:
            raise HTTPException(409, str(exc)) from None

    @router.get('/{conversation_id}/history')
    def search_history(conversation_id: str, q: str = Query(min_length=1, max_length=2000)):
        require(conversation_id)
        return {'sources': sanitize_value(service.store.search_history(conversation_id, q))}

    @router.get('/{conversation_id}/sources/{source_id:path}')
    def source(conversation_id: str, source_id: str, offset: int = Query(0, ge=0),
               limit: int = Query(6000, ge=1, le=12000)):
        require(conversation_id)
        row = service.store.source(conversation_id, source_id)
        if not row:
            raise HTTPException(404, '原始记录不存在')
        safe = sanitize_value(row)
        content = safe['question'] + '\n' + safe['answer']
        return {'sourceId': source_id, 'content': content[offset:offset + limit], 'totalChars': len(content),
                'nextOffset': offset + limit if offset + limit < len(content) else None}

    @router.delete('/{conversation_id}/memories')
    def forget_memory(conversation_id: str, payload: ForgetMemory):
        require(conversation_id)
        try:
            service.forget_uri(conversation_id, payload.uri)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        return {'forgotten': True, 'remoteDeletion': 'queued' if service.client else 'unconfigured'}

    @router.delete('/{conversation_id}')
    def forget_context(conversation_id: str):
        require(conversation_id)
        service.forget(conversation_id)
        if delete_session:
            delete_session(conversation_id)
        return {'forgotten': True, 'sharedScopeInvalidated': True,
                'remoteDeletion': 'queued' if service.client else 'unconfigured'}

    return router
