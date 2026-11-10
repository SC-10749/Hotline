from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI

from ...api.routers.mcp import create_mcp_router
from ...api.routers.registry import create_registry_router
from ...config import Settings
from ...infrastructure.governance_store import GovernanceStore
from ...infrastructure.registry_store import RegistryStore
from ...llm import FallbackChatModel, build_chat_model, probe_model
from ...modules.execution.tools import (
    enforce_approval,
    prepare_tool_call,
    set_current_run_id,
    validate_tool_arguments,
)
from . import call_stdio_tool, list_stdio_tools, probe_stdio_server

FAKE_MCP_SERVER = """
import json
import sys

line = sys.stdin.readline()
try:
    request = json.loads(line)
except Exception:
    request = {}
response = {
    'jsonrpc': '2.0',
    'id': request.get('id'),
    'result': {'protocolVersion': '2024-11-05', 'serverInfo': {'name': 'fake-mcp', 'version': '1.0'}},
}
print(json.dumps(response))
sys.stdout.flush()
"""

FAKE_TOOL_SERVER = """
import json
import os
import sys

pid_file = sys.argv[1]
with open(pid_file, 'w', encoding='utf-8') as handle:
    handle.write(str(os.getpid()))

TOOLS = [{'name': 'echo', 'description': '回显文本',
          'inputSchema': {'type': 'object', 'properties': {'text': {'type': 'string'}},
                          'required': ['text']}}]

while True:
    line = sys.stdin.readline()
    if not line:
        break
    try:
        request = json.loads(line)
    except Exception:
        continue
    method = request.get('method')
    if method == 'initialize':
        result = {'protocolVersion': '2024-11-05', 'serverInfo': {'name': 'fake-mcp', 'version': '1.0'}}
    elif method == 'tools/list':
        result = {'tools': TOOLS}
    elif method == 'tools/call':
        arguments = (request.get('params') or {}).get('arguments') or {}
        result = {'content': [{'type': 'text', 'text': 'echo:' + str(arguments.get('text', ''))}],
                  'isError': False}
    else:
        result = {}
    sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': request.get('id'), 'result': result}) + chr(10))
    sys.stdout.flush()
"""

SLOW_TOOL_SERVER = """
import json
import sys
import time

sys.stdin.readline()
time.sleep(30)
"""

SILENT_MCP_SERVER = """
import sys
import time

sys.stdin.readline()
time.sleep(30)
"""

GARBAGE_MCP_SERVER = """
import sys

sys.stdin.readline()
print('not json at all')
sys.stdout.flush()
"""


def _write_script(root: Path, name: str, body: str) -> str:
    path = root / name
    path.write_text(body, encoding='utf-8')
    return str(path)


class McpProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_initialize_probe_succeeds(self):
        script = _write_script(self.root, 'fake_server.py', FAKE_MCP_SERVER)
        result = probe_stdio_server({'command': sys.executable, 'args': [script]}, timeout=15)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['message'], '连接正常')
        self.assertEqual(result['details']['protocolVersion'], '2024-11-05')
        self.assertEqual(result['details']['serverName'], 'fake-mcp')

    def test_missing_command_is_rejected(self):
        result = probe_stdio_server({'args': []})
        self.assertFalse(result['ok'])
        self.assertEqual(result['message'], 'MCP 配置缺少 command')

    def test_unknown_command_fails_without_leaking_path(self):
        secret_path = str(self.root / 'secret' / 'server.py')
        result = probe_stdio_server({'command': secret_path}, timeout=5)
        self.assertFalse(result['ok'])
        self.assertNotIn(secret_path, result['message'])
        self.assertNotIn('secret', result['message'])

    def test_silent_server_times_out(self):
        script = _write_script(self.root, 'silent_server.py', SILENT_MCP_SERVER)
        result = probe_stdio_server({'command': sys.executable, 'args': [script]}, timeout=1)
        self.assertFalse(result['ok'])
        self.assertIn('没有响应', result['message'])

    def test_garbage_output_is_rejected(self):
        script = _write_script(self.root, 'garbage_server.py', GARBAGE_MCP_SERVER)
        result = probe_stdio_server({'command': sys.executable, 'args': [script]}, timeout=15)
        self.assertFalse(result['ok'])
        self.assertIn('JSON-RPC', result['message'])


class RegistryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = RegistryStore(self.root / 'registry.db')

    def tearDown(self):
        self.temp.cleanup()

    def test_lookup_tool_by_name(self):
        self.store.create_tool({'name': 'read_skill', 'source': 'builtin'})
        found = self.store.get_tool_by_name('read_skill')
        self.assertIsNotNone(found)
        self.assertEqual(found['name'], 'read_skill')
        self.assertIsNone(self.store.get_tool_by_name('missing'))

    def test_list_mcp_servers_only_returns_configured_tools(self):
        self.store.create_tool({'name': 'read_skill', 'source': 'builtin'})
        self.store.create_tool({
            'name': 'files',
            'source': 'mcp:local',
            'input_schema': {'type': 'object', 'properties': {}, 'mcp': {'command': 'python', 'args': []}},
        })
        servers = self.store.list_mcp_servers()
        self.assertEqual([item['name'] for item in servers], ['files'])
        self.assertEqual(set(servers[0]), {'tool_id', 'name', 'source', 'status'})

    def test_fallback_chain_order(self):
        primary = self.store.create_model({'name': '主模型'})
        backup = self.store.create_model({'name': '备用模型', 'fallback_model_id': primary['model_id']})
        chain = self.store.fallback_chain(backup['model_id'])
        self.assertEqual([item['model_id'] for item in chain], [backup['model_id'], primary['model_id']])

    def test_fallback_chain_detects_cycle(self):
        first = self.store.create_model({'name': 'A'})
        second = self.store.create_model({'name': 'B', 'fallback_model_id': first['model_id']})
        with closing(sqlite3.connect(self.store.path)) as db:
            db.execute('UPDATE harness_model SET fallback_model_id=? WHERE model_id=?', (second['model_id'], first['model_id']))
            db.commit()
        with self.assertRaises(ValueError):
            self.store.fallback_chain(first['model_id'])


class ToolValidationTests(unittest.TestCase):
    def test_missing_required_argument_is_rejected(self):
        schema = {'type': 'object', 'properties': {'skill_id': {'type': 'string'}}, 'required': ['skill_id']}
        with self.assertRaises(ValueError) as ctx:
            validate_tool_arguments(schema, {})
        self.assertIn('缺少必填参数', str(ctx.exception))

    def test_wrong_type_is_rejected(self):
        schema = {'type': 'object', 'properties': {'limit': {'type': 'number'}}}
        with self.assertRaises(ValueError) as ctx:
            validate_tool_arguments(schema, {'limit': 'many'})
        self.assertIn('应为 number 类型', str(ctx.exception))

    def test_non_object_arguments_are_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            validate_tool_arguments({'type': 'object', 'properties': {}}, ['a'])
        self.assertIn('必须是 JSON 对象', str(ctx.exception))

    def test_valid_arguments_pass(self):
        schema = {'type': 'object', 'properties': {'skill_id': {'type': 'string'}, 'limit': {'type': 'integer'}}}
        validate_tool_arguments(schema, {'skill_id': 's1', 'limit': 10})

    def test_unregistered_tool_keeps_current_behaviour(self):
        temp = tempfile.TemporaryDirectory()
        try:
            prepare_tool_call('read_skill', {'skill_id': 's1'},
                              registry_db=Path(temp.name) / 'missing.db')
        finally:
            temp.cleanup()


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.governance_db = self.root / 'governance.db'
        self.store = GovernanceStore(self.governance_db)
        self.record = {'approval_policy': 'always', 'risk': 'high'}
        set_current_run_id(None)

    def tearDown(self):
        set_current_run_id(None)
        self.temp.cleanup()

    def _wait_for_request(self):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            pending = self.store.list('pending')
            if pending:
                return pending[0]
            time.sleep(0.05)
        self.fail('审批请求没有写入')

    def _run_approval(self, decision, run_id='run-1'):
        errors = []

        def _worker():
            try:
                enforce_approval('read_skill', {'skill_id': 's1'}, self.record,
                                  run_id=run_id, governance_db=self.governance_db, wait_seconds=10)
            except Exception as exc:
                errors.append(exc)

        thread = threading.Thread(target=_worker)
        thread.start()
        request = self._wait_for_request()
        self.store.decide(request['request_id'], decision)
        thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        return errors

    def test_approved_request_allows_execution(self):
        errors = self._run_approval('approved')
        self.assertEqual(errors, [])
        self.assertEqual(self.store.list('approved')[0]['tool'], 'read_skill')

    def test_rejected_request_blocks_execution(self):
        errors = self._run_approval('rejected')
        self.assertEqual(len(errors), 1)
        self.assertIn('审批被拒绝', str(errors[0]))

    def test_approval_detail_has_no_argument_values(self):
        errors = self._run_approval('approved')
        self.assertEqual(errors, [])
        detail = self.store.list('approved')[0]['detail']
        self.assertNotIn('s1', detail)
        self.assertIn('skill_id', detail)

    def test_without_run_id_approval_is_skipped(self):
        enforce_approval('read_skill', {'skill_id': 's1'}, self.record,
                          run_id=None, governance_db=self.governance_db, wait_seconds=1)
        self.assertEqual(self.store.list(), [])

    def test_env_switch_disables_approval(self):
        with patch.dict(os.environ, {'HARNESS_APPROVAL_ENFORCE': '0'}):
            enforce_approval('read_skill', {'skill_id': 's1'}, self.record,
                              run_id='run-1', governance_db=self.governance_db, wait_seconds=1)
        self.assertEqual(self.store.list(), [])

    def test_prepare_tool_call_validates_and_approves(self):
        registry_db = self.root / 'registry.db'
        store = RegistryStore(registry_db)
        store.create_tool({
            'name': 'read_skill',
            'source': 'builtin',
            'risk': 'high',
            'approval_policy': 'always',
            'input_schema': {'type': 'object', 'properties': {'skill_id': {'type': 'string'}},
                              'required': ['skill_id']},
        })
        with self.assertRaises(ValueError) as ctx:
            prepare_tool_call('read_skill', {'path': 'SKILL.md'},
                              run_id='run-1', registry_db=registry_db,
                              governance_db=self.governance_db, wait_seconds=1)
        self.assertIn('工具参数校验失败', str(ctx.exception))
        self.assertEqual(self.store.list(), [])


class RegistryRouterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = RegistryStore(self.root / 'registry.db')
        app = FastAPI()
        app.include_router(create_registry_router(self.store))
        self.client = TestClient(app)
        self.script = _write_script(self.root, 'fake_server.py', FAKE_MCP_SERVER)

    def tearDown(self):
        self.temp.cleanup()

    def _create_tool(self, **payload):
        body = {'name': 'read_skill', 'source': 'builtin', 'scope': 'workspace', 'risk': 'low',
                'status': 'configured', 'description': '', 'input_schema': {'type': 'object', 'properties': {}},
                'approval_policy': 'risk-based'}
        body.update(payload)
        response = self.client.post('/harness/tools', json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['tool']

    def test_builtin_tool_test_passes(self):
        tool = self._create_tool(name='read_skill', source='builtin')
        response = self.client.post(f"/harness/tools/{tool['tool_id']}/test")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['ok'], True)

    def test_unknown_builtin_tool_fails(self):
        tool = self._create_tool(name='not_a_builtin_tool', source='builtin')
        response = self.client.post(f"/harness/tools/{tool['tool_id']}/test")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'ok': False, 'message': '未找到同名内置工具'})

    def test_unsupported_source_is_reported(self):
        tool = self._create_tool(name='files', source='ftp')
        response = self.client.post(f"/harness/tools/{tool['tool_id']}/test")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['message'], '暂不支持的连接方式：ftp')

    def test_mcp_tool_test_probes_server(self):
        tool = self._create_tool(name='files', source='mcp:local', input_schema={
            'type': 'object', 'properties': {},
            'mcp': {'command': sys.executable, 'args': [self.script]},
        })
        response = self.client.post(f"/harness/tools/{tool['tool_id']}/test")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['ok'], True)

    def test_mcp_servers_list_is_owned_by_the_mcp_router(self):
        # MCP 服务器列表由 api/routers/mcp.py 单独提供（含工具发现），
        # registry 路由不再重复提供，避免同一路径两套语义。
        self.assertEqual(self.client.get('/harness/mcp/servers').status_code, 404)

    def test_model_test_uses_probe(self):
        model = self.store.create_model({'name': '主模型'})
        with patch('python_backend.api.routers.registry.probe_model',
                   return_value={'ok': True, 'message': '连接正常'}) as probe:
            response = self.client.post(f"/harness/models/{model['model_id']}/test")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['ok'], True)
        probe.assert_called_once()

    def test_model_test_404_for_unknown_model(self):
        response = self.client.post('/harness/models/model-missing/test')
        self.assertEqual(response.status_code, 404)

    def test_fallback_chain_endpoint(self):
        primary = self.store.create_model({'name': '主模型'})
        backup = self.store.create_model({'name': '备用', 'fallback_model_id': primary['model_id']})
        response = self.client.get(f"/harness/models/{backup['model_id']}/fallback-chain")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['ids'], [backup['model_id'], primary['model_id']])

    def test_fallback_chain_cycle_returns_400(self):
        first = self.store.create_model({'name': 'A'})
        second = self.store.create_model({'name': 'B', 'fallback_model_id': first['model_id']})
        with closing(sqlite3.connect(self.store.path)) as db:
            db.execute('UPDATE harness_model SET fallback_model_id=? WHERE model_id=?',
                       (second['model_id'], first['model_id']))
            db.commit()
        response = self.client.get(f"/harness/models/{first['model_id']}/fallback-chain")
        self.assertEqual(response.status_code, 400)


class _ScriptedChatModel(ChatOpenAI):
    """替身：总是返回固定回答，用来验证回退链路。"""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content='fallback-ok'))])


class FallbackModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = Settings(model_api_key='placeholder-test-key', model_name='primary-model',
                                 model_base_url='http://127.0.0.1:1/v1', data_dir=self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_default_build_has_no_fallback(self):
        model = build_chat_model(self.settings)
        self.assertNotIsInstance(model, FallbackChatModel)

    def test_fallback_models_are_resolved_from_registry(self):
        store = RegistryStore(self.root / 'harness-registry.db')
        backup = store.create_model({'name': 'backup-model'})
        model = build_chat_model(self.settings, fallback_model_ids=[backup['model_id']])
        self.assertIsInstance(model, FallbackChatModel)
        self.assertEqual(len(model.fallback_models), 1)
        self.assertEqual(model.fallback_models[0].model_name, 'backup-model')

    def test_fallback_is_used_and_recorded(self):
        events = []
        scripted = _ScriptedChatModel(model='backup-model', api_key='placeholder-test-key',
                                      base_url='http://127.0.0.1:1/v1', max_retries=0)
        model = FallbackChatModel(model='primary-model', api_key='placeholder-test-key',
                                  base_url='http://127.0.0.1:1/v1', max_retries=0,
                                  fallback_models=[scripted])
        model.fallback_callback = events.append
        bound = model.bind_tools([])
        result = bound.invoke([HumanMessage(content='ping')])
        self.assertEqual(result.content, 'fallback-ok')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['fallback'], 'backup-model')


class ProbeModelTests(unittest.TestCase):
    def setUp(self):
        # 用临时 data 目录，避免读到本机真实保存的模型凭证。
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_missing_credentials_are_reported(self):
        result = probe_model(Settings(model_api_key='', model_name='', model_base_url='',
                                      data_dir=self.root))
        self.assertFalse(result['ok'])
        self.assertEqual(result['message'], '未配置模型凭据，无法测试')

    def test_failure_does_not_echo_credentials(self):
        secret_key = 'secret-key-marker'
        secret_url = 'http://127.0.0.1:1/v1'
        result = probe_model(Settings(model_api_key=secret_key, model_name='probe-model',
                                      model_base_url=secret_url, data_dir=self.root))
        self.assertFalse(result['ok'])
        self.assertNotIn(secret_key, result['message'])
        self.assertNotIn(secret_url, result['message'])


class McpRouterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = RegistryStore(self.root / 'registry.db')
        self.pid_file = self.root / 'server.pid'
        self.script = _write_script(self.root, 'tool_server.py', FAKE_TOOL_SERVER)
        app = FastAPI()
        app.include_router(create_registry_router(self.store))
        app.include_router(create_mcp_router(self.store))
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def _create_tool(self):
        body = {'name': 'files', 'source': 'mcp:local', 'scope': 'workspace', 'risk': 'low',
                'status': 'configured', 'description': '', 'approval_policy': 'risk-based',
                'input_schema': {'type': 'object', 'properties': {},
                                 'mcp': {'command': sys.executable,
                                         'args': [self.script, str(self.pid_file)]}}}
        response = self.client.post('/harness/tools', json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['tool']

    def test_servers_list_includes_discovered_tools(self):
        tool = self._create_tool()
        items = self.client.get('/harness/mcp/servers').json()['items']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['tools'], ['echo'])
        self.assertEqual(items[0]['message'], '')
        self.assertEqual(items[0]['tool_id'], tool['tool_id'])

    def test_servers_list_reports_probe_failure_without_leaking(self):
        body = {'name': 'files', 'source': 'mcp:local', 'scope': 'workspace', 'risk': 'low',
                'status': 'configured', 'description': '', 'approval_policy': 'risk-based',
                'input_schema': {'type': 'object', 'properties': {},
                                 'mcp': {'command': 'no-such-mcp-command', 'args': [str(self.root)]}}}
        self.client.post('/harness/tools', json=body)
        items = self.client.get('/harness/mcp/servers').json()['items']
        self.assertEqual(items[0]['tools'], [])
        self.assertNotIn(str(self.root), items[0]['message'])

    def test_tool_call_returns_content(self):
        tool = self._create_tool()
        response = self.client.post(f"/harness/mcp/servers/{tool['tool_id']}/tools/echo/call",
                                    json={'arguments': {'text': 'hi'}})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body['ok'])
        self.assertFalse(body['isError'])
        self.assertEqual(body['content'][0]['text'], 'echo:hi')

    def test_unknown_tool_returns_404(self):
        tool = self._create_tool()
        response = self.client.post(f"/harness/mcp/servers/{tool['tool_id']}/tools/missing/call",
                                    json={'arguments': {}})
        self.assertEqual(response.status_code, 404, response.text)

    def test_unknown_server_returns_404(self):
        response = self.client.post('/harness/mcp/servers/tool-missing/tools/echo/call',
                                    json={'arguments': {}})
        self.assertEqual(response.status_code, 404, response.text)

    def test_invalid_arguments_return_400(self):
        tool = self._create_tool()
        response = self.client.post(f"/harness/mcp/servers/{tool['tool_id']}/tools/echo/call",
                                    json={'arguments': {}})
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn('text', response.json()['detail'])


class McpToolDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.pid_file = self.root / 'server.pid'
        self.script = _write_script(self.root, 'tool_server.py', FAKE_TOOL_SERVER)

    def tearDown(self):
        self.temp.cleanup()

    def _config(self, script=None):
        return {'command': sys.executable, 'args': [script or self.script, str(self.pid_file)]}

    def _server_pid(self):
        return int(self.pid_file.read_text(encoding='utf-8').strip())

    def _process_alive(self, pid):
        if os.name == 'nt':
            result = subprocess.run(['tasklist', '/FI', 'PID eq ' + str(pid)], capture_output=True, text=True)
            return str(pid) in result.stdout
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def test_tools_list_returns_tool_metadata(self):
        result = list_stdio_tools(self._config(), timeout=15)
        self.assertTrue(result['ok'], result)
        self.assertEqual([item['name'] for item in result['tools']], ['echo'])
        self.assertEqual(result['tools'][0]['description'], '回显文本')
        self.assertEqual(result['tools'][0]['inputSchema']['required'], ['text'])

    def test_tool_call_returns_content(self):
        result = call_stdio_tool(self._config(), 'echo', {'text': 'hi'}, timeout=15)
        self.assertTrue(result['ok'], result)
        self.assertFalse(result['isError'])
        self.assertEqual(result['content'][0]['text'], 'echo:hi')

    def test_tool_call_rejects_non_object_arguments(self):
        result = call_stdio_tool(self._config(), 'echo', ['not', 'object'], timeout=15)
        self.assertFalse(result['ok'])
        self.assertEqual(result['message'], '工具参数必须是 JSON 对象')

    def test_tool_call_rejects_empty_tool_name(self):
        result = call_stdio_tool(self._config(), '  ', {}, timeout=15)
        self.assertFalse(result['ok'])
        self.assertEqual(result['message'], '工具名称不能为空')

    def test_tools_list_times_out(self):
        script = _write_script(self.root, 'slow_server.py', SLOW_TOOL_SERVER)
        result = list_stdio_tools({'command': sys.executable, 'args': [script]}, timeout=1)
        self.assertFalse(result['ok'])
        self.assertIn('没有响应', result['message'])
        self.assertEqual(result['tools'], [])

    def test_tools_list_rejects_invalid_response(self):
        script = _write_script(self.root, 'garbage_server.py', GARBAGE_MCP_SERVER)
        result = list_stdio_tools({'command': sys.executable, 'args': [script]}, timeout=15)
        self.assertFalse(result['ok'])
        self.assertIn('JSON-RPC', result['message'])

    def test_failures_do_not_leak_command_or_arguments(self):
        secret = 'secret-tool-name-marker'
        result = call_stdio_tool({'command': 'definitely-not-a-real-command'}, secret, {'a': 'b'}, timeout=5)
        self.assertFalse(result['ok'])
        self.assertNotIn(secret, result['message'])
        self.assertNotIn('definitely-not-a-real-command', result['message'])

    def test_no_server_process_is_left_running(self):
        result = list_stdio_tools(self._config(), timeout=15)
        self.assertTrue(result['ok'], result)
        pid = self._server_pid()
        for _ in range(20):
            if not self._process_alive(pid):
                break
            time.sleep(0.1)
        self.assertFalse(self._process_alive(pid), 'MCP 服务器进程没有退出')


if __name__ == '__main__':
    unittest.main()
