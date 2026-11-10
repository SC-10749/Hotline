"""轻量机器人路由：机器人配置与会话绑定。

机器人页写入 BotStore；会话绑定决定这次对话用哪个人设。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from ...infrastructure.bot_store import BotStore


class BotPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    instruction: str = Field(default='', max_length=4000)
    skills: list[str] | None = None
    enabled: bool = True

    @field_validator('name')
    @classmethod
    def nonempty_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('机器人名称不能为空')
        return value


class BotUpdatePayload(BotPayload):
    pass


class BotSessionPayload(BaseModel):
    conversationId: str = Field(min_length=1, max_length=200)


def create_bots_router(store: BotStore) -> APIRouter:
    router = APIRouter()

    @router.get('/harness/bots')
    def list_bots():
        return {'items': store.list()}

    @router.post('/harness/bots')
    def create_bot(payload: BotPayload):
        bot = store.create({'name': payload.name, 'instruction': payload.instruction.strip(),
                            'skills': payload.skills or [], 'enabled': payload.enabled})
        return {'bot': bot}

    @router.get('/harness/bots/{bot_id}')
    def get_bot(bot_id: str):
        bot = store.get(bot_id)
        if not bot:
            raise HTTPException(status_code=404, detail='机器人不存在')
        return {'bot': bot}

    @router.put('/harness/bots/{bot_id}')
    def update_bot(bot_id: str, payload: BotUpdatePayload):
        if not store.get(bot_id):
            raise HTTPException(status_code=404, detail='机器人不存在')
        bot = store.update(bot_id, {'name': payload.name, 'instruction': payload.instruction.strip(),
                                    'skills': payload.skills or [], 'enabled': payload.enabled})
        return {'bot': bot}

    @router.delete('/harness/bots/{bot_id}')
    def delete_bot(bot_id: str):
        if not store.delete(bot_id):
            raise HTTPException(status_code=404, detail='机器人不存在')
        return {'deleted': bot_id}

    @router.post('/harness/bots/{bot_id}/sessions')
    def bind_session(bot_id: str, payload: BotSessionPayload):
        """把一个会话绑定到机器人；之后该会话的提问都会带上这条人设。"""
        if not store.get(bot_id):
            raise HTTPException(status_code=404, detail='机器人不存在')
        store.bind_session(payload.conversationId.strip(), bot_id)
        return {'bot': store.get(bot_id), 'conversationId': payload.conversationId.strip()}

    return router
