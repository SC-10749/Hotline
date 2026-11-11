"""轻量机器人、个人偏好与模型凭证的存储和接口测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from python_backend.modules.execution.engine import AgentEngine
from ..llm import model_config, model_ready
from ..infrastructure.bot_store import BotStore
from ..infrastructure.credential_store import CredentialStore
from ..infrastructure.persona import load_persona
from ..infrastructure.profile_store import ProfileStore
from .routers.bots import create_bots_router
from .routers.profile import create_profile_router


class BotProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bot_store = BotStore(self.root / 'harness-bots.db')
        self.profile_store = ProfileStore(self.root / 'harness-profile.db')
        self.credential_store = CredentialStore(self.root / 'harness-credentials.db')
        app = FastAPI()
        app.include_router(create_bots_router(self.bot_store))
        app.include_router(create_profile_router(
            self.profile_store, self.credential_store,
            model_probe=lambda credential: {'ok': False, 'message': '模型连接失败：ConnectionError'},
        ))
        self.client = TestClient(app)

    def tearDown(self):
        self.temp.cleanup()

    def test_bot_crud_round_trip(self):
        created = self.client.post('/harness/bots', json={
            'name': '运维助手', 'instruction': '你是运维助手', 'skills': ['skill-a'], 'enabled': True,
        })
        self.assertEqual(created.status_code, 200)
        bot = created.json()['bot']
        self.assertEqual(bot['name'], '运维助手')
        self.assertEqual(bot['skills'], ['skill-a'])

        listed = self.client.get('/harness/bots').json()['items']
        self.assertEqual([item['bot_id'] for item in listed], [bot['bot_id']])

        updated = self.client.put(f"/harness/bots/{bot['bot_id']}", json={
            'name': '运维助手2', 'instruction': '你是运维助手', 'skills': [], 'enabled': False,
        })
        self.assertEqual(updated.status_code, 200)
        self.assertFalse(updated.json()['bot']['enabled'])

        self.assertEqual(self.client.delete(f"/harness/bots/{bot['bot_id']}").status_code, 200)
        self.assertEqual(self.client.get('/harness/bots').json()['items'], [])

    def test_missing_bot_returns_404(self):
        self.assertEqual(self.client.get('/harness/bots/bot-nope').status_code, 404)
        self.assertEqual(self.client.delete('/harness/bots/bot-nope').status_code, 404)

    def test_blank_name_is_rejected(self):
        response = self.client.post('/harness/bots', json={'name': '   '})
        self.assertEqual(response.status_code, 422)

    def test_session_binding_drives_persona(self):
        bot = self.client.post('/harness/bots', json={
            'name': '客服机器人', 'instruction': '你是客服机器人', 'skills': ['skill-a'],
        }).json()['bot']
        self.client.put('/harness/profile', json={'answerStyle': 'concise'})
        bound = self.client.post(f"/harness/bots/{bot['bot_id']}/sessions", json={'conversationId': 'conv-1'})
        self.assertEqual(bound.status_code, 200)

        persona = load_persona(self.root, 'conv-1')
        self.assertEqual(persona['instruction'], '你是客服机器人')
        self.assertEqual(persona['skills'], ['skill-a'])
        self.assertIn('简洁', persona['style'])

        # 未绑定会话拿不到人设
        self.assertEqual(load_persona(self.root, 'conv-none')['instruction'], '')

    def test_disabled_bot_keeps_only_personal_style(self):
        bot = self.client.post('/harness/bots', json={
            'name': '停用机器人', 'instruction': '你是停用机器人', 'enabled': False,
        }).json()['bot']
        self.client.post(f"/harness/bots/{bot['bot_id']}/sessions", json={'conversationId': 'conv-2'})
        persona = load_persona(self.root, 'conv-2')
        self.assertEqual(persona['instruction'], '')

    def test_profile_partial_update_keeps_other_fields(self):
        self.client.put('/harness/profile', json={'nickname': '小热', 'bio': '值班工程师'})
        updated = self.client.put('/harness/profile', json={'theme': 'dark'}).json()['profile']
        self.assertEqual(updated['nickname'], '小热')
        self.assertEqual(updated['bio'], '值班工程师')
        self.assertEqual(updated['theme'], 'dark')

    def test_profile_rejects_unknown_style_and_theme(self):
        self.assertEqual(self.client.put('/harness/profile', json={'answerStyle': 'shout'}).status_code, 400)
        self.assertEqual(self.client.put('/harness/profile', json={'theme': 'neon'}).status_code, 400)

    def test_credential_is_masked_and_keeps_existing_key(self):
        saved = self.client.put('/harness/profile/credentials', json={
            'provider': 'openai', 'baseUrl': 'https://api.example.com/v1', 'model': 'gpt-test', 'apiKey': 'sk-secret-value-1234',
        })
        self.assertEqual(saved.status_code, 200)
        credential = saved.json()['credential']
        self.assertNotIn('sk-secret-value-1234', str(credential))
        self.assertTrue(credential['apiKey'].endswith('1234'))

        # 不填 apiKey 时保留原有密钥
        again = self.client.put('/harness/profile/credentials', json={'model': 'gpt-other'}).json()['credential']
        self.assertEqual(again['model'], 'gpt-other')
        self.assertEqual(self.credential_store.get()['api_key'], 'sk-secret-value-1234')

        self.assertEqual(self.client.delete('/harness/profile/credentials').status_code, 200)
        self.assertEqual(self.client.delete('/harness/profile/credentials').status_code, 404)

    def test_credential_test_endpoint_reports_failure(self):
        response = self.client.post('/harness/profile/credentials/test', json={
            'apiKey': 'sk-bad', 'baseUrl': 'http://127.0.0.1:9/v1', 'model': 'x',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['ok'])


class PersonaPromptTests(unittest.TestCase):
    """人设注入只追加到系统提示词，不覆盖既有规则。"""

    def _engine(self):
        engine = AgentEngine.__new__(AgentEngine)
        engine.skills = None
        return engine

    def test_persona_block_appends_role_and_style(self):
        system = self._engine()._persona_block(
            {'instruction': '你是客服机器人', 'style': '回答保持简洁', 'skills': []}, '基础提示')
        self.assertTrue(system.startswith('基础提示'))
        self.assertIn('你是客服机器人', system)
        self.assertIn('回答保持简洁', system)

    def test_persona_block_keeps_system_without_persona(self):
        self.assertEqual(self._engine()._persona_block({}, '基础提示'), '基础提示')


class ModelConfigTests(unittest.TestCase):
    """本机保存的凭证必须优先于环境变量。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_local_credential_overrides_environment(self):
        CredentialStore(self.root / 'harness-credentials.db').save({
            'api_key': 'sk-local-key-9999', 'base_url': 'https://local.example/v1', 'model': 'local-model',
        })
        settings = SimpleNamespace(model_api_key='env-key', model_base_url='https://env.example/v1',
                                   model_name='env-model', data_dir=self.root)
        config = model_config(settings)
        self.assertEqual(config['api_key'], 'sk-local-key-9999')
        self.assertEqual(config['base_url'], 'https://local.example/v1')
        self.assertEqual(config['model'], 'local-model')

    def test_environment_is_used_without_local_credential(self):
        settings = SimpleNamespace(model_api_key='env-key', model_base_url='https://env.example/v1',
                                   model_name='env-model', data_dir=self.root)
        config = model_config(settings)
        self.assertEqual(config['api_key'], 'env-key')
        self.assertTrue(model_ready(settings))


if __name__ == '__main__':
    unittest.main()
