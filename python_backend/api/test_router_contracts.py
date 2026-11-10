"""前端调用路径与后端路由的契约测试。

frontend/src/api.js 里每条 Harness 请求都必须在后端真实注册，否则页面只会拿到
404。这里只装配路由工厂（不连 MySQL），核对路径与方法，并检查动态段是否把静态
路径抢占（例如 /evaluation/runs/compare 被 /evaluation/runs/{id} 吃掉）。
"""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ..application.execution_service import ExecutionApplicationService
from ..infrastructure.evaluation_store import EvaluationStore
from ..infrastructure.governance_store import GovernanceStore
from ..infrastructure.notification_store import NotificationStore
from ..infrastructure.registry_store import RegistryStore
from ..infrastructure.resource_store import ResourceStore
from ..infrastructure.settings_store import SettingsStore
from ..infrastructure.bot_store import BotStore
from ..infrastructure.credential_store import CredentialStore
from ..infrastructure.profile_store import ProfileStore
from ..infrastructure.queue import SqliteExecutionQueue
from ..modules.artifacts.store import ArtifactStore
from .routers.artifacts import create_artifact_router
from .routers.evaluation import create_evaluation_router
from .routers.execution import create_execution_router
from .routers.governance import create_governance_router
from .routers.mcp import create_mcp_router
from .routers.observability import create_observability_router
from .routers.registry import create_registry_router
from .routers.release import create_release_router, stop_release_observation
from .routers.resources import create_resource_router
from .routers.settings import create_settings_router
from .routers.bots import create_bots_router
from .routers.profile import create_profile_router

# 与 frontend/src/api.js 中 Harness 相关调用一一对应。
FRONTEND_CONTRACTS = [
    ('GET', '/harness/approvals/notifications'),
    ('GET', '/evaluation/runs/compare'),
    ('GET', '/evaluation/runs/{eval_run_id}/export'),
    ('POST', '/release/rollouts/observe'),
    ('GET', '/release/observations'),
    ('GET', '/harness/observability/exports'),
    ('GET', '/harness/observability/trends'),
    ('POST', '/harness/workspaces/{workspace_id}/checkout'),
    ('GET', '/harness/workspaces/{workspace_id}/checkout'),
    ('POST', '/harness/skills/catalog/bind'),
    ('DELETE', '/harness/skills/catalog/bind'),
    ('GET', '/harness/mcp/servers'),
    ('GET', '/harness/models/{model_id}/fallback-chain'),
    ('POST', '/harness/mcp/servers/{tool_id}/tools/{tool_name}/call'),
    ('GET', '/harness/overview'),
    ('GET', '/harness/machines/{worker_id}/errors'),
    ('GET', '/harness/artifacts'),
    ('GET', '/harness/artifacts/{artifact_id}/download'),
    ('GET', '/harness/artifacts/{artifact_id}/preview'),
    ('GET', '/harness/bots'),
    ('POST', '/harness/bots'),
    ('GET', '/harness/bots/{bot_id}'),
    ('PUT', '/harness/bots/{bot_id}'),
    ('DELETE', '/harness/bots/{bot_id}'),
    ('POST', '/harness/bots/{bot_id}/sessions'),
    ('GET', '/harness/profile'),
    ('PUT', '/harness/profile'),
    ('GET', '/harness/profile/credentials'),
    ('PUT', '/harness/profile/credentials'),
    ('DELETE', '/harness/profile/credentials'),
    ('POST', '/harness/profile/credentials/test'),
]


class _FakeStorage:
    """只提供产物路由需要的最小接口，不连接对象存储。"""

    backend = 'local'

    def __init__(self, root: Path):
        self.settings = type('StorageSettings', (), {'generated_dir': root, 'data_dir': root})()


def _split_template(path: str) -> list[str]:
    """把 /a/{id}/b 拆成 ['/a/', '{id}', '/b']。"""
    parts: list[str] = []
    remainder = path
    while True:
        start = remainder.find('{')
        end = remainder.find('}', start) if start >= 0 else -1
        if end < 0:
            parts.append(remainder)
            return parts
        parts.append(remainder[:start])
        parts.append(remainder[start:end + 1])
        remainder = remainder[end + 1:]


def _template_regex(path: str) -> re.Pattern:
    """把 /a/{id}/b 变成能匹配具体路径的正则。"""
    pattern = ''.join('([^/]+)' if part.startswith('{') else re.escape(part)
                     for part in _split_template(path))
    return re.compile('^' + pattern + '$')


def _literal(path: str) -> str:
    """把模板路径变成一个具体请求路径，用于检查路由匹配顺序。"""
    return ''.join('sample' if part.startswith('{') else part
                   for part in _split_template(path))


class RouterContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.app = FastAPI()
        evaluation_store = EvaluationStore(root / 'evaluation.db')
        governance_store = GovernanceStore(root / 'governance.db')
        registry_store = RegistryStore(root / 'registry.db')
        resource_store = ResourceStore(root / 'resources.db')
        settings_store = SettingsStore(root / 'settings.db')
        artifact_store = ArtifactStore(root / 'artifacts.db')
        routers = [
            create_execution_router(ExecutionApplicationService(SqliteExecutionQueue(root / 'execution.db')), lambda _: True),
            create_evaluation_router(evaluation_store),
            create_resource_router(resource_store),
            create_registry_router(registry_store),
            create_mcp_router(registry_store),
            create_governance_router(
                lambda: [], governance_store, None, settings_store.get, NotificationStore(root / 'notifications.db'),
            ),
            create_observability_router(
                lambda **kwargs: ([], 0), lambda run_id: None, lambda run_id, *args, **kwargs: [],
                execution_db_path=root / 'execution.db',
            ),
            create_artifact_router(artifact_store, _FakeStorage(root), settings_store.get),
            create_settings_router(settings_store),
            create_release_router(
                lambda action, args: {}, 'hotline-agent', evaluation_store.get_run, governance_store,
            ),
            create_bots_router(BotStore(root / 'bots.db')),
            create_profile_router(ProfileStore(root / 'profile.db'), CredentialStore(root / 'credentials.db')),
        ]
        for router in routers:
            self.app.include_router(router)
        self.client = TestClient(self.app)
        # FastAPI 新版本把 include 后的路由包成 _IncludedRouter，这里直接读各 router 自己的路由表。
        self.routes = [
            (route.path, method)
            for router in routers
            for route in router.routes
            for method in getattr(route, 'methods', set())
            if method not in {'HEAD', 'OPTIONS'}
        ]

    def tearDown(self):
        stop_release_observation()
        self.temp.cleanup()

    def test_frontend_paths_are_registered(self):
        registered = {(method, path) for path, method in self.routes}
        missing = [item for item in FRONTEND_CONTRACTS if item not in registered]
        self.assertEqual(missing, [], '前端调用的路径没有注册：' + str(missing))

    def test_static_paths_are_not_shadowed_by_dynamic_routes(self):
        for method, template in FRONTEND_CONTRACTS:
            literal = _literal(template)
            candidates = [route_path for route_path, route_method in self.routes
                          if route_method == method and _template_regex(route_path).match(literal)]
            self.assertTrue(candidates, method + ' ' + literal + ' 没有匹配路由')
            self.assertEqual(candidates[0], template,
                             method + ' ' + literal + ' 被更早注册的 ' + candidates[0] + ' 抢占')

    def test_empty_data_endpoints_answer(self):
        self.assertEqual(self.client.get('/harness/approvals/notifications').status_code, 200)
        self.assertEqual(self.client.get('/release/observations').status_code, 200)
        self.assertEqual(self.client.get('/harness/observability/exports?format=json').status_code, 200)
        self.assertEqual(self.client.get('/harness/observability/trends?bucket=hour').status_code, 200)
        self.assertEqual(self.client.get('/harness/mcp/servers').status_code, 200)
        self.assertEqual(self.client.get('/harness/artifacts').status_code, 200)

    def test_compare_missing_runs_returns_404(self):
        response = self.client.get('/evaluation/runs/compare?base=missing-a&target=missing-b')
        self.assertEqual(response.status_code, 404)


if __name__ == '__main__':
    unittest.main()
