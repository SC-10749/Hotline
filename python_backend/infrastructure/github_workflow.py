"""GitHub Actions 工作流开关：查询与启停仓库里的 CI 工作流。

凭据只从本机环境变量读（Settings.github_token），不进数据库、不写日志、不出网到第三方。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

GITHUB_API = 'https://api.github.com'


class WorkflowError(RuntimeError):
    """GitHub 接口不可用或拒绝请求；消息里只带状态码，不带凭据。"""


class GitHubWorkflowClient:
    """仓库级工作流开关；只操作一个仓库的一个工作流。"""

    def __init__(self, token: str, repository: str, workflow: str = 'ci.yml', timeout: float = 15.0):
        self.token = token
        self.repository = repository
        self.workflow = workflow
        self.timeout = timeout

    def _request(self, method: str, path: str) -> dict:
        request = urllib.request.Request(
            f'{GITHUB_API}{path}', method=method,
            headers={'Authorization': f'Bearer {self.token}',
                     'Accept': 'application/vnd.github+json',
                     'X-GitHub-Api-Version': '2022-11-28'})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode('utf-8')
        except urllib.error.HTTPError as exc:
            raise WorkflowError(f'GitHub 接口返回 {exc.code}') from exc
        except Exception as exc:
            raise WorkflowError('GitHub 接口不可用') from exc
        try:
            return json.loads(body) if body.strip() else {}
        except json.JSONDecodeError as exc:
            raise WorkflowError('GitHub 接口返回了无法解析的内容') from exc

    def workflow_state(self) -> dict:
        data = self._request('GET', f'/repos/{self.repository}/actions/workflows/{self.workflow}')
        state = str(data.get('state') or 'unknown')
        return {'state': state, 'enabled': state == 'active',
                'name': str(data.get('name') or ''), 'path': str(data.get('path') or '')}

    def set_enabled(self, enabled: bool) -> dict:
        action = 'enable' if enabled else 'disable'
        self._request('PUT', f'/repos/{self.repository}/actions/workflows/{self.workflow}/{action}')
        return self.workflow_state()
