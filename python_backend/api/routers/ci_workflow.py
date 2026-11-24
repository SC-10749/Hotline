"""CI 工作流开关路由：查看与启停仓库里的 GitHub Actions 工作流。

未配置凭据时接口如实说明"未配置"，不做猜测；启停结果以 GitHub 返回的状态为准。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...infrastructure.github_workflow import GitHubWorkflowClient, WorkflowError


class CiWorkflowPayload(BaseModel):
    enabled: bool


def create_ci_workflow_router(settings) -> APIRouter:
    router = APIRouter()

    def client() -> GitHubWorkflowClient | None:
        if not settings.github_token or not settings.github_repository:
            return None
        return GitHubWorkflowClient(settings.github_token, settings.github_repository,
                                   settings.github_ci_workflow)

    def describe(extra: dict | None = None) -> dict:
        payload = {'configured': True, 'enabled': None, 'state': '',
                   'workflow': settings.github_ci_workflow,
                   'repository': settings.github_repository}
        payload.update(extra or {})
        return payload

    @router.get('/harness/ci-workflow')
    def read_ci_workflow():
        api = client()
        if api is None:
            return {'configured': False, 'enabled': None, 'state': '',
                    'workflow': settings.github_ci_workflow,
                    'repository': settings.github_repository,
                    'message': '未配置 GitHub Token 与仓库地址，无法读取工作流状态'}
        try:
            state = api.workflow_state()
        except WorkflowError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return describe(state)

    @router.post('/harness/ci-workflow')
    def set_ci_workflow(payload: CiWorkflowPayload):
        api = client()
        if api is None:
            raise HTTPException(status_code=409, detail='未配置 GitHub Token 与仓库地址，无法启停工作流')
        try:
            state = api.set_enabled(payload.enabled)
        except WorkflowError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return describe(state)

    return router
