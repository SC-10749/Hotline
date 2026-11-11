from __future__ import annotations

import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.language_models import BaseChatModel
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import StructuredTool
from pydantic import Field

from python_backend.modules.execution.engine import AgentEngine, TaskManager, ModelClient
from ...api.routers.context_engineering import create_context_router
from ...api.routers.execution import create_execution_router
from ...application.execution_service import ExecutionApplicationService
from ...config import Settings
from ...modules.execution.langchain_agent import run_agent
from ...modules.execution.store import ExecutionStore
from ...modules.memory.openviking import OpenVikingClient, memory_uri_belongs
from ...modules.memory.tools import build_context_tools
from ...modules.memory.store import MemoryConflict, MemoryStore
from ...modules.retrieval.fusion import fuse_evidence
from ...runtime import AgentEngineRuntime
from python_backend.modules.storage.relational import Storage
from ...workers.execution_worker import ExecutionWorker, build_worker
from ...infrastructure.resource_store import ResourceStore
from ...modules.workspaces.context import load_workspace_rules
from .budget import ContextBudget, ContextBudgetExceeded, assemble_context
from .privacy import sanitize_text
from .service import ContextService


class OpenVikingFixture:
    """Real loopback HTTP with the documented OpenViking request/response envelopes."""
    def __init__(self):
        self.requests = []
        self.sessions = {}
        self.memories = {}
        self.tasks = {}
        self.fail_path = ''
        self.lose_commit_response = False
        self.foreign_hit = False
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.handle_request()

            def do_POST(self):
                self.handle_request()

            def do_PATCH(self):
                self.handle_request()

            def do_DELETE(self):
                self.handle_request()

            def handle_request(self):
                path = urlsplit(self.path).path
                body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
                peer = self.headers.get('X-OpenViking-Actor-Peer')
                fixture.requests.append((self.command, path, body, peer))
                status, result = 200, {}
                if fixture.fail_path == path:
                    fixture.fail_path = ''
                    self.send_error(503)
                    return
                if path == '/api/v1/sessions' and self.command == 'POST':
                    fixture.sessions[body['session_id']] = {'peer': peer, 'messages': [], 'committed': False,
                                                          'memory_policy': body['memory_policy']}
                    result = {'session_id': body['session_id']}
                elif path.startswith('/api/v1/sessions/'):
                    identity = path.split('/')[4]
                    session = fixture.sessions.get(identity)
                    if self.command == 'DELETE':
                        fixture.sessions.pop(identity, None)
                    elif session is None:
                        status = 404
                    elif path.endswith('/messages/batch'):
                        session['messages'].extend(body['messages'])
                    elif path.endswith('/commit'):
                        if not session['committed']:
                            session['committed'] = True
                            content = '\n'.join(item['content'] for item in session['messages'])
                            uri = f'viking://user/local/peers/{peer}/memories/events/{identity}.md'
                            fixture.memories.setdefault(peer, []).append({'uri': uri, 'content': content, 'score': 0.9})
                            fixture.tasks['task-' + identity] = {'status': 'completed', 'resource_id': identity,
                                                                 'task_id': 'task-' + identity}
                            result = {'task_id': 'task-' + identity}
                        else:
                            result = {}
                        if fixture.lose_commit_response:
                            fixture.lose_commit_response = False
                            self.send_error(503)
                            return
                elif path == '/api/v1/search/search':
                    expected = f'viking://~/peers/{peer}/memories'
                    if body.get('target_uri') != expected or body.get('mode') != 'list':
                        status = 400
                    hits = list(fixture.memories.get(peer, []))
                    if fixture.foreign_hit:
                        hits.append({'uri': 'viking://user/local/peers/foreign/memories/a.md',
                                     'content': 'FOREIGN_SCOPE_SENTINEL'})
                    result = {'memories': hits, 'total': len(hits)}
                elif path.startswith('/api/v1/tasks/'):
                    result = fixture.tasks.get(path.split('/')[-1], {'status': 'running'})
                elif path == '/api/v1/tasks':
                    resource = parse_qs(urlsplit(self.path).query).get('resource_id', [''])[0]
                    result = [item for item in fixture.tasks.values() if item.get('resource_id') == resource]
                elif path == '/api/v1/fs' and self.command == 'DELETE':
                    uri = parse_qs(urlsplit(self.path).query)['uri'][0]
                    fixture.memories[peer] = [item for item in fixture.memories.get(peer, [])
                                              if not (item['uri'] == uri or '/memories' == uri[-9:])]
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'status': 'ok' if status == 200 else 'error', 'result': result}).encode())

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


class ScriptedModel(BaseChatModel):
    responses: list[AIMessage]
    requests: list = Field(default_factory=list)

    @property
    def _llm_type(self):
        return 'context-test'

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.requests.append(messages)
        return ChatResult(generations=[ChatGeneration(message=self.responses[len(self.requests) - 1])])


class ContextChainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = Settings(data_dir=self.root, storage_backend='sqlite', redis_enabled=False,
                                 vector_enabled=False, file_storage_backend='local', model_api_key='',
                                 openviking_url='', context_enabled=True)
        self.store = MemoryStore(self.root / 'memory.db')
        self.service = ContextService(self.settings, store=self.store)

    def attach_server(self):
        fixture = OpenVikingFixture()
        self.addCleanup(fixture.close)
        self.service.client = OpenVikingClient(fixture.url, 'PLACEHOLDER_KEY', timeout=1)
        return fixture

    def drain(self):
        for _ in range(20):
            with self.store.db() as db:
                db.execute('UPDATE memory_delivery SET available_at=0,lease_until=0')
            if not self.service.deliver_once():
                break

    def test_budget_preserves_rules_and_current_question_with_large_evidence(self):
        budget = ContextBudget(window=10000, input_limit=4000, output_reserve=1000, safety_margin=100)
        history = [SimpleNamespace(id=str(i), question='历史' * 100, answer='结果' * 100) for i in range(30)]
        messages, manifest = assemble_context('必须保留规则', '当前问题', history,
                                             [{'source': 'doc', 'content': '资料' * 100000}], budget)
        self.assertIn('必须保留规则', messages[0]['content'])
        self.assertEqual(messages[-1]['content'], '当前问题')
        self.assertLessEqual(budget.check(messages), 4000)
        self.assertGreater(manifest['omittedHistoryTurns'], 0)
        with self.assertRaises(ContextBudgetExceeded):
            assemble_context('规则', '问题' * 10000, [], [], budget)

    def test_privacy_covers_config_credentials_addresses_and_keeps_rules(self):
        raw = ('必须保护 .env 文件\nPRIVATE_KEY=ENV_SENTINEL\npassword=PASSWORD_SENTINEL\n'
               'https://example.test/private 192.0.2.8:9000 internal.local:1234\n'
               '<private>PRIVATE_SENTINEL</private>\nBearer BEARER_SENTINEL')
        safe = sanitize_text(raw)
        self.assertIn('必须保护', safe)
        for forbidden in ('ENV_SENTINEL', 'PASSWORD_SENTINEL', 'example.test', '192.0.2.8',
                          'internal.local', 'PRIVATE_SENTINEL', 'BEARER_SENTINEL'):
            self.assertNotIn(forbidden, safe)
        self.assertEqual(sanitize_text('2026-11-09T12:30:00+08:00'), '2026-11-09T12:30:00+08:00')
        self.assertNotIn('2001:db8::1', sanitize_text('地址 2001:db8::1'))

    def test_task_correction_survives_thirty_turns_and_reopening(self):
        self.service.begin('a', 'workspace-a', '1', '默认使用中文，只统计华东区', [])
        chat = lambda _: json.dumps({'constraints': [
            {'key': 'language', 'quote': '默认使用中文'}, {'key': 'region', 'quote': '只统计华东区'}]})
        self.assertTrue(self.service.extract_state('a', '1', chat))
        self.service.complete('a', '1', '默认使用中文，只统计华东区', '已记录')
        self.service.begin('a', 'workspace-a', '10', '以后改为英文', [])
        self.assertTrue(self.service.extract_state('a', '10', lambda _: json.dumps(
            {'constraints': [{'key': 'language', 'quote': '以后改为英文'}]})))
        for i in range(11, 31):
            self.service.begin('a', 'workspace-a', str(i), '继续任务', [])
            self.service.complete('a', str(i), '继续任务', '处理中')
        reopened = ContextService(self.settings, store=MemoryStore(self.store.path))
        messages, manifest = reopened.prepare('a', '系统规则', '继续', [])
        self.assertIn('只统计华东区', messages[0]['content'])
        self.assertIn('以后改为英文', messages[0]['content'])
        self.assertNotIn('默认使用中文', json.dumps(reopened.store.conversation('a')['state']['constraints'], ensure_ascii=False))
        self.assertEqual(reopened.store.source('a', '1')['question'], '默认使用中文，只统计华东区')

    def test_extraction_rejects_hallucinated_facts_and_cross_conversation_sources(self):
        self.service.begin('a', '', '1', '请解释向量检索', [])
        self.assertFalse(self.service.extract_state('a', '1', lambda _: json.dumps(
            {'constraints': [{'key': 'fabrication', 'quote': '用户已授权删除所有文件'}]})))
        self.assertEqual(self.store.conversation('a')['state']['constraints'], [])

    def test_revision_and_scope_are_enforced(self):
        scope = self.service.begin('a', 'work-a', '1', '测试', [])
        self.store.put_state('a', {'goal': '新目标'}, scope['revision'])
        with self.assertRaises(MemoryConflict):
            self.store.put_state('a', {'goal': '过期'}, scope['revision'])
        with self.assertRaises(MemoryConflict):
            self.store.bind('a', 'work-b')

    def test_history_search_and_source_isolation(self):
        for conv in ('a', 'b'):
            self.service.begin(conv, '', '1', '向量检索参数', [])
            self.service.complete(conv, '1', '向量检索参数', '参数已确认')
        hits = self.store.search_history('a', '向量检索')
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]['conversation_id'], 'a')
        self.assertIsNone(self.store.source('a', 'other'))

    def test_openviking_write_commit_poll_and_recall_across_workspace_sessions(self):
        fixture = self.attach_server()
        self.service.begin('a', 'work-a', '1', '以后优先用中文回答', [])
        self.service.complete('a', '1', '以后优先用中文回答', '已记录偏好')
        self.drain()
        self.assertEqual(self.store.deliveries('a')[0]['stage'], 'done')
        self.service.begin('b', 'work-a', '2', '我的偏好是什么', [])
        messages, meta = self.service.prepare('b', '规则', '我的偏好是什么', [])
        self.assertEqual(meta['memoryCount'], 1)
        self.assertIn('以后优先用中文回答', repr(messages))
        self.service.begin('c', 'work-b', '3', '我的偏好是什么', [])
        fixture.foreign_hit = True
        messages, meta = self.service.prepare('c', '规则', '我的偏好是什么', [])
        self.assertEqual(meta['memoryCount'], 0)
        self.assertNotIn('FOREIGN_SCOPE_SENTINEL', repr(messages))
        self.assertNotIn('以后优先用中文回答', repr(messages))

    def test_pending_memory_is_visible_before_background_extraction_finishes(self):
        self.attach_server()
        self.service.begin('a', 'work-a', '1', '回答时优先使用中文', [])
        self.service.complete('a', '1', '回答时优先使用中文', '已经记录')
        self.service.begin('b', 'work-a', '2', '继续之前的偏好', [])
        messages, meta = self.service.prepare('b', '规则', '继续之前的偏好', [])
        self.assertEqual(meta['pendingMemoryCount'], 1)
        self.assertIn('回答时优先使用中文', repr(messages))
        source_id = 'delivery:' + self.store.deliveries('a')[0]['job_id']
        self.assertEqual(self.store.source('b', source_id)['question'], '回答时优先使用中文')
        self.service.begin('c', 'work-b', '3', '其他任务', [])
        self.assertIsNone(self.store.source('c', source_id))

    def test_retry_upload_and_lost_commit_response_do_not_duplicate_memories(self):
        fixture = self.attach_server()
        self.service.begin('a', '', '1', '记住这个偏好', [])
        self.service.complete('a', '1', '记住这个偏好', '已记录')
        job = self.store.deliveries('a')[0]['job_id']
        fixture.fail_path = f'/api/v1/sessions/{job}/messages/batch'
        self.service.deliver_once()
        self.assertEqual(self.store.deliveries('a')[0]['stage'], 'pending')
        fixture.lose_commit_response = True
        self.drain()
        peer = self.store.conversation('a')['peer_id']
        self.assertEqual(len(fixture.memories[peer]), 1)
        self.assertEqual(self.store.deliveries('a')[0]['stage'], 'done')
        self.assertEqual(len(fixture.sessions[job]['messages']), 2)

    def test_delivery_is_durable_and_claimed_by_one_worker(self):
        self.attach_server()
        self.service.begin('a', '', '1', '偏好', [])
        self.service.complete('a', '1', '偏好', '已记录')
        self.service.complete('a', '1', '偏好', '已记录')
        reopened = MemoryStore(self.store.path)
        with ThreadPoolExecutor(max_workers=8) as executor:
            claims = list(executor.map(lambda _: reopened.claim(), range(8)))
        self.assertEqual(sum(item is not None for item in claims), 1)
        self.assertEqual(len(reopened.deliveries('a')), 1)

    def test_outbound_memory_payload_is_sanitized_and_raw_evidence_stays_local(self):
        fixture = self.attach_server()
        query = '请记住 password=PRIVATE_TEST_VALUE https://example.test/internal'
        self.service.begin('a', '', '1', query, [])
        self.service.complete('a', '1', query, '收到')
        self.drain()
        self.assertNotIn('PRIVATE_TEST_VALUE', repr(fixture.requests))
        self.assertNotIn('example.test', repr(fixture.requests))
        self.assertIn('PRIVATE_TEST_VALUE', self.store.source('a', '1')['question'])

    def test_memory_outage_keeps_local_answer_path_and_visible_retry(self):
        self.service.client = OpenVikingClient('http://127.0.0.1:1', timeout=0.1)
        self.service.begin('a', '', '1', '当前问题', [])
        messages, manifest = self.service.prepare('a', '规则', '当前问题', [])
        self.assertEqual(manifest['memoryStatus'], 'unavailable')
        self.service.complete('a', '1', '当前问题', '本地结果')
        self.service.deliver_once()
        self.assertEqual(self.store.deliveries('a')[0]['error_code'], 'unavailable')
        self.assertEqual(messages[-1]['content'], '当前问题')

    def test_forget_rotates_namespace_and_removes_derived_memories(self):
        fixture = self.attach_server()
        self.service.begin('a', 'shared', '1', 'PRIVATE_OLD_FACT', [])
        self.service.complete('a', '1', 'PRIVATE_OLD_FACT', '旧结果')
        self.drain()
        old_peer = self.store.conversation('a')['peer_id']
        self.service.begin('b', 'shared', '2', '保留的会话', [])
        self.service.complete('b', '2', '保留的会话', '保留结果')
        self.service.forget('a')
        messages, _ = self.service.prepare('b', '规则', '问题', [])
        self.assertNotIn('PRIVATE_OLD_FACT', repr(messages))
        self.assertNotEqual(self.store.conversation('b')['peer_id'], old_peer)
        self.drain()
        self.assertEqual(fixture.memories.get(old_peer), [])
        self.assertIsNone(self.store.source('a', '1'))

    def test_api_source_pagination_state_conflict_and_forget(self):
        self.service.begin('a', '', '1', '必须使用中文', [])
        self.service.complete('a', '1', '必须使用中文', '结果' * 100)
        app = FastAPI()
        app.include_router(create_context_router(self.service))
        client = TestClient(app)
        status = client.get('/harness/context/a').json()
        payload = {'revision': status['task']['revision'], 'goal': '报告',
                   'constraints': [{'key': 'language', 'quote': '必须使用中文', 'sourceId': '1'}]}
        self.assertEqual(client.put('/harness/context/a/task', json=payload).status_code, 200)
        self.assertEqual(client.put('/harness/context/a/task', json=payload).status_code, 409)
        payload['constraints'][0]['sourceId'] = 'other-conversation'
        self.assertEqual(client.put('/harness/context/a/task', json=payload).status_code, 400)
        source = client.get('/harness/context/a/sources/1?limit=10').json()
        self.assertEqual(len(source['content']), 10)
        self.assertEqual(source['nextOffset'], 10)
        self.assertEqual(client.delete('/harness/context/a').status_code, 200)
        self.assertEqual(client.get('/harness/context/a').status_code, 404)

    def test_worker_normal_entrypoint_persists_context_and_sse(self):
        storage = Storage(self.settings)
        engine = AgentEngine(self.settings, storage, TaskManager(self.settings), context_service=self.service)
        engine.model.stream = Mock(return_value=iter(['端到端回答']))
        engine._search = Mock(return_value=[])
        queue = ExecutionStore(self.root / 'execution.db')
        run = queue.enqueue('a', 'chat', '请解释参数', None, workspace_id='workspace-a')
        worker = ExecutionWorker(queue, AgentEngineRuntime(engine), engine.tasks, object())
        self.assertTrue(worker.run_once())
        self.assertEqual(queue.get_run(run['run_id'])['status'], 'completed')
        self.assertEqual(self.store.conversation('a')['workspace_id'], 'workspace-a')
        self.assertEqual(self.store.events('a')[-1]['answer'], '端到端回答')
        app = FastAPI()
        app.include_router(create_execution_router(ExecutionApplicationService(queue), lambda _: True))
        response = TestClient(app).get(f"/execution/runs/{run['run_id']}/stream")
        self.assertEqual(response.status_code, 200)
        self.assertIn('context_snapshot', response.text)
        self.assertIn('utf8-byte-upper-bound', response.text)

    def test_preexisting_history_can_be_retrieved_beyond_recent_window(self):
        storage = Storage(self.settings)
        first = storage.save_question('a', '唯一的历史项目编号 ALPHA123', 'chat', None)
        storage.update_answer(first, '原始结果')
        for i in range(70):
            identity = storage.save_question('a', '普通问题 ' + str(i), 'chat', None)
            storage.update_answer(identity, '普通结果')
        self.assertNotIn(first, [row.id for row in storage.context_messages('a')])
        self.assertEqual(storage.search_session_messages('a', 'ALPHA123')[0].id, first)

    def test_skill_loop_archives_large_tool_result_and_sanitizes_each_call(self):
        self.service.begin('a', '', '1', '读取内容', [])
        def read_blob() -> str:
            """Read the synthetic blob."""
            return 'password=PRIVATE_TOOL_VALUE\n' + 'x' * 100000
        tool = StructuredTool.from_function(read_blob)
        model = ScriptedModel(responses=[AIMessage(content='', tool_calls=[
            {'name': 'read_blob', 'args': {}, 'id': 'call-1'}]), AIMessage(content='读取完成')])
        events = list(run_agent(model, '规则', '读取内容', [tool], lambda: False,
                                archive_tool=lambda message: self.service.record_tool('a', message)))
        self.assertEqual(events[-1].type, 'done')
        self.assertNotIn('PRIVATE_TOOL_VALUE', repr(model.requests))
        source = self.store.source('a', 'tool:call-1')
        self.assertGreater(len(source['answer']), 100000)
        self.assertIn('PRIVATE_TOOL_VALUE', source['answer'])
        results = [item for item in model.requests[-1] if isinstance(item, ToolMessage)]
        self.assertEqual(results[0].tool_call_id, 'call-1')
        self.assertLess(len(results[0].content), 13000)

    def test_fusion_rewards_agreement_and_deduplicates_parent_content(self):
        hits = fuse_evidence([['first', 'shared', 'shared'], ['shared', 'second']], 'shared')
        self.assertEqual(hits[0], 'shared')
        self.assertEqual(hits.count('shared'), 1)

    def test_skill_entrypoint_restores_history_and_exposes_readonly_memory_tools(self):
        storage = Storage(self.settings)
        previous = storage.save_question('a', '使用精确的项目编号 ALPHA123', 'skills', None)
        storage.update_answer(previous, '已经确认项目编号')
        settings = replace(self.settings, model_api_key='PLACEHOLDER')
        skills = Mock()
        skills.open_resource_session.return_value = Mock(descriptors=())
        engine = AgentEngine(settings, storage, TaskManager(settings), skills=skills, context_service=self.service)
        engine.model.chat = Mock(return_value='{}')
        model = ScriptedModel(responses=[AIMessage(content='已恢复任务')])
        with patch('python_backend.agents.build_chat_model', return_value=model):
            events = list(engine.stream('skills', 'a', '继续这个项目', workspace_id='work-a'))
        self.assertEqual(events[-1]['type'], 'complete')
        self.assertIn('ALPHA123', repr(model.requests))
        snapshots = [item['snapshot'] for item in events if item['type'] == 'context_snapshot']
        tool_names = [item['definition']['name'] for item in snapshots[-1]['tools']]
        self.assertIn('search_memory', tool_names)
        self.assertIn('read_context_source', tool_names)
        self.assertEqual(snapshots[-1]['sources']['historyPolicy'], 'task-history-and-memory')

    def test_memory_tools_recover_archived_results_and_reject_foreign_uris(self):
        self.service.begin('a', 'work-a', '1', '任务', [])
        identity = self.service.record_tool('a', ToolMessage(content='完整结果' * 5000,
                                                            tool_call_id='call-1', name='reader'), 'turn-1')
        tools = {tool.name: tool for tool in build_context_tools(self.service, 'a')}
        result = tools['read_context_source'].invoke({'source_id': identity, 'offset': 0, 'limit': 100})
        self.assertEqual(len(result['content']), 100)
        self.assertEqual(result['next_offset'], 100)
        result = tools['read_context_source'].invoke({'source_id': 'viking://user/local/peers/other/memories/x.md'})
        self.assertIn('error', result)
        peer = self.store.conversation('a')['peer_id']
        self.assertFalse(memory_uri_belongs(peer, f'viking://user/local/peers/other/memories/peers/{peer}/memories/a.md'))
        self.assertFalse(memory_uri_belongs(peer, f'viking://user/local/peers/{peer}/memories/%2e%2e/secret'))

    def test_model_input_is_sanitized_and_budgeted_before_http_transport(self):
        settings = replace(self.settings, model_api_key='PLACEHOLDER', model_base_url='http://127.0.0.1:1')
        client = ModelClient(settings)
        with patch('urllib.request.urlopen', side_effect=OSError) as opened:
            client.chat([{'role': 'user', 'content': 'password=MODEL_PRIVATE_VALUE'}])
        payload = json.loads(opened.call_args.args[0].data)
        self.assertNotIn('MODEL_PRIVATE_VALUE', repr(payload['messages']))
        self.assertEqual(payload['max_tokens'], settings.context_output_reserve)
        with patch('urllib.request.urlopen') as opened:
            with self.assertRaises(ContextBudgetExceeded):
                client.chat([{'role': 'user', 'content': 'x' * 100000}])
            opened.assert_not_called()

    def test_parallel_model_usage_is_scoped_to_current_thread(self):
        client = ModelClient(self.settings)
        barrier = threading.Barrier(2)
        def record(value):
            client._record_usage({'usage': {'input_tokens': value}})
            barrier.wait(timeout=5)
            return client.last_usage['inputTokens']
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(record, [10, 20]))
        self.assertEqual(results, [10, 20])

    def test_workspace_rules_are_loaded_and_protected_in_normal_entrypoint(self):
        root = self.root / 'workspace'
        root.mkdir()
        (root / 'AGENTS.md').write_text('必须遵循 PROJECT_RULE_SENTINEL', encoding='utf-8')
        resources = Mock()
        resources.get_workspace.return_value = {'repository': str(root)}
        resources.get_workspace_checkout.return_value = None
        resources.resolve_local_repository.return_value = root
        self.assertIn('PROJECT_RULE_SENTINEL', load_workspace_rules(resources, 'work-a'))
        storage = Storage(self.settings)
        engine = AgentEngine(self.settings, storage, TaskManager(self.settings), context_service=self.service,
                              workspace_rules_reader=lambda identity: load_workspace_rules(resources, identity))
        engine.model.stream = Mock(return_value=iter(['回答']))
        engine._search = Mock(return_value=[])
        events = list(engine.stream('chat', 'a', '问题', workspace_id='work-a'))
        self.assertEqual(events[-1]['type'], 'complete')
        self.assertIn('PROJECT_RULE_SENTINEL', engine.model.stream.call_args.args[0][0]['content'])

    def test_explicit_cancellation_replaces_active_constraint_with_provenance(self):
        self.service.begin('a', '', '1', '以后必须使用中文', [])
        self.service.extract_state('a', '1', lambda _: json.dumps({'constraints': [
            {'key': 'language', 'quote': '以后必须使用中文'}]}))
        self.service.begin('a', '', '2', '取消必须使用中文的要求', [])
        self.service.extract_state('a', '2', lambda _: json.dumps({'constraints': [
            {'key': 'language', 'quote': '取消必须使用中文的要求', 'status': 'cancelled'}]}))
        fact = self.store.conversation('a')['state']['constraints'][0]
        self.assertEqual(fact['status'], 'cancelled')
        self.assertEqual(fact['sourceId'], '2')

    def test_multi_step_tool_compaction_preserves_current_tool_protocol(self):
        def read_blob() -> str:
            """Read a large fixture."""
            return 'x' * 20000
        tool = StructuredTool.from_function(read_blob)
        responses = [AIMessage(content='', tool_calls=[{'name': 'read_blob', 'args': {}, 'id': f'call-{i}'}])
                     for i in range(6)] + [AIMessage(content='完成')]
        model = ScriptedModel(responses=responses)
        events = list(run_agent(model, '保留规则', '用户目标', [tool], lambda: False,
                                budget=ContextBudget(window=20000, input_limit=9000, output_reserve=1000),
                                archive_tool=lambda message: 'tool:turn-1:' + message.tool_call_id))
        self.assertEqual(events[-1].type, 'done')
        self.assertIn('tool:turn-1:call-0', repr(model.requests[-1]))
        self.assertIn('保留规则', model.requests[-1][0].content)
        self.assertIn('用户目标', repr(model.requests[-1]))
        for request in model.requests:
            calls = {call['id'] for message in request if isinstance(message, AIMessage) for call in message.tool_calls}
            results = {message.tool_call_id for message in request if isinstance(message, ToolMessage)}
            self.assertEqual(calls, results)

    def test_memory_write_failure_preserves_answer_and_repairs_on_next_turn(self):
        storage = Storage(self.settings)
        engine = AgentEngine(self.settings, storage, TaskManager(self.settings), context_service=self.service)
        engine.model.stream = Mock(return_value=iter(['已生成的回答']))
        engine._search = Mock(return_value=[])
        with patch.object(self.service, 'complete', side_effect=OSError('fixture storage unavailable')):
            events = list(engine.stream('chat', 'a', '第一个问题'))
        self.assertEqual(events[-1]['type'], 'complete')
        self.assertTrue(any(event.get('stage') == 'memory_write' and event.get('status') == 'failed' for event in events))
        first = storage.session_messages('a')[0]
        self.assertEqual(first.answer, '已生成的回答')
        engine.model.stream = Mock(return_value=iter(['下一轮回答']))
        list(engine.stream('chat', 'a', '继续'))
        self.assertTrue(self.store.source('a', str(first.id))['completed'])

    def test_worker_factory_wires_workspace_rules_and_context_service(self):
        repository = self.root / 'repository'
        repository.mkdir()
        (repository / 'AGENTS.md').write_text('FACTORY_WORKSPACE_RULE', encoding='utf-8')
        config = replace(self.settings, upload_dir=self.root / 'uploads', generated_dir=self.root / 'generated',
                         skills_dir=self.root / 'skills', repo_skills_dir=self.root / 'repo-skills',
                         skill_catalog_db=self.root / 'catalog.db', skill_project='context-test')
        with patch('python_backend.workers.execution_worker.settings', config):
            worker = build_worker()
        self.addCleanup(worker.runtime.engine.documents.events.shutdown)
        self.addCleanup(worker.runtime.close)
        resources = ResourceStore(self.root / 'harness-resources.db')
        workspace = resources.create_workspace({'name': 'fixture', 'repository': str(repository), 'branch': 'main'})
        engine = worker.runtime.engine
        engine.model.stream = Mock(return_value=iter(['工厂装配完成']))
        engine._search = Mock(return_value=[])
        run = worker.store.enqueue('factory', 'chat', '问题', None, workspace_id=workspace['workspace_id'])
        self.assertTrue(worker.run_once())
        self.assertEqual(worker.store.get_run(run['run_id'])['status'], 'completed')
        self.assertIn('FACTORY_WORKSPACE_RULE', engine.model.stream.call_args.args[0][0]['content'])


if __name__ == '__main__':
    unittest.main()
