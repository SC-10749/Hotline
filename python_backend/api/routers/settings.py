from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ...infrastructure.settings_store import SettingsStore


class HarnessSettingsPayload(BaseModel):
    isolation: str = Field(default='container', max_length=40)
    auditRetentionDays: int = Field(default=30, ge=1, le=3650)
    approvalPolicy: str = Field(default='risk-based', max_length=60)
    defaultBudgetUsd: float = Field(default=0.2, ge=0, le=100000)
    defaultTimeoutSeconds: int = Field(default=900, ge=1, le=86400)
    defaultRetryCount: int = Field(default=1, ge=0, le=10)
    approvalTimeoutSeconds: int = Field(default=3600, ge=60, le=86400)
    artifactRetentionDays: int = Field(default=30, ge=1, le=3650)
    defaultTokenBudget: int = Field(default=0, ge=0, le=100000000)
    approvalNotifyEnabled: bool = True
    notificationWebhookUrl: str = Field(default='', max_length=500)
    artifactOwnerHeader: str = Field(default='X-Harness-Owner', max_length=80)


def create_settings_router(store: SettingsStore) -> APIRouter:
    router = APIRouter()

    @router.get('/harness/settings')
    def get_settings():
        return {'settings': store.get()}

    @router.put('/harness/settings')
    def save_settings(payload: HarnessSettingsPayload):
        return {'settings': store.save(payload.model_dump())}

    return router

