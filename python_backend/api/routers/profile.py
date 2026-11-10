"""个人偏好与模型凭证路由。

凭证只存在本机 data 目录，接口只回显掩码；回答风格会真正进入模型提示词。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...infrastructure.credential_store import CredentialStore
from ...infrastructure.profile_store import ProfileStore


class ProfilePayload(BaseModel):
    nickname: str | None = Field(default=None, max_length=60)
    bio: str | None = Field(default=None, max_length=500)
    answerStyle: str | None = Field(default=None, max_length=40)
    theme: str | None = Field(default=None, max_length=20)


class CredentialPayload(BaseModel):
    provider: str | None = Field(default=None, max_length=120)
    baseUrl: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, max_length=160)
    apiKey: str | None = Field(default=None, max_length=1000)


ANSWER_STYLES = {'default', 'concise', 'detailed', 'friendly'}
THEMES = {'system', 'light', 'dark'}


def create_profile_router(profile_store: ProfileStore, credential_store: CredentialStore,
                          model_probe: Any = None) -> APIRouter:
    router = APIRouter()

    @router.get('/harness/profile')
    def get_profile():
        return {'profile': profile_store.get()}

    @router.put('/harness/profile')
    def save_profile(payload: ProfilePayload):
        values = payload.model_dump(exclude_none=True)
        if 'answerStyle' in values and values['answerStyle'] not in ANSWER_STYLES:
            raise HTTPException(status_code=400, detail='不支持的回答风格')
        if 'theme' in values and values['theme'] not in THEMES:
            raise HTTPException(status_code=400, detail='不支持的界面主题')
        return {'profile': profile_store.save(values)}

    @router.get('/harness/profile/credentials')
    def get_credentials():
        return {'credential': credential_store.public()}

    @router.put('/harness/profile/credentials')
    def save_credentials(payload: CredentialPayload):
        values = payload.model_dump(exclude_none=True)
        values['base_url'] = values.pop('baseUrl', '')
        values['api_key'] = values.pop('apiKey', '')
        return {'credential': credential_store.save(values)}

    @router.delete('/harness/profile/credentials')
    def delete_credentials():
        if not credential_store.delete():
            raise HTTPException(status_code=404, detail='尚未保存模型凭证')
        return {'deleted': True}

    @router.post('/harness/profile/credentials/test')
    def test_credentials(payload: CredentialPayload):
        """用当前保存的（或这次提交的）凭证真实发一次请求。"""
        if model_probe is None:
            raise HTTPException(status_code=501, detail='模型连通性测试未接入')
        values = payload.model_dump(exclude_none=True)
        credential = {
            'api_key': values.get('apiKey') or (credential_store.get() or {}).get('api_key', ''),
            'base_url': values.get('baseUrl') or (credential_store.get() or {}).get('base_url', ''),
            'model': values.get('model') or (credential_store.get() or {}).get('model', ''),
        }
        return model_probe(credential)

    return router
