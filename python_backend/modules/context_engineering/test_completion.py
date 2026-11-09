from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from ...agents import AgentEngine, TaskManager
from ...api.routers.execution import create_execution_router
from ...api.routers.context_engineering import create_context_router
from ...api.routers.workspace_import import create_workspace_import_router
from ...application.execution_service import ExecutionApplicationService
from ...config import Settings
from ...infrastructure.resource_store import ResourceStore
from ...modules.execution.store import ActiveExecutionError, ExecutionStore
from ...modules.memory.openviking import OpenVikingClient
from ...modules.memory.store import MemoryStore
from ...modules.memory.tools import build_context_tools
from ...modules.retrieval.workspace_index import WorkspaceIndex
from ...modules.workspaces.context import load_workspace_rules, recall_workspace
from ...runtime import AgentEngineRuntime
from ...storage import Storage
from ...workers.execution_worker import ExecutionWorker
from .privacy import private_path, sanitize_text
from .service import ContextService
from .test_chain import ScriptedModel


class ContextCompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = Settings(data_dir=self.root, storage_backend='sqlite', file_storage_backend='local',
                                 redis_enabled=False, vector_enabled=False, model_api_key='',
                                 embedding_api_key='', openviking_url='', context_enabled=True)
        self.index = WorkspaceIndex(self.root / 'workspace.db')
        self.context = ContextService(self.settings)

    def engine(self, **kwargs):
        return AgentEngine(self.settings, Storage(self.settings), TaskManager(self.settings),
                           context_service=self.context, **kwargs)

    def test_private_paths_are_excluded_before_read_and_embedding(self):
        root = self.root / 'workspace'
        names = ['.env', '.ENV.backup', 'config.env.zip', 'settings.local.json', 'settings.private.toml',
                 'private/notes.txt', 'secrets/key.txt', 'nested/.ssh/id_ed25519', 'tls/server.pem',
                 'data/log.txt', 'node_modules/a.txt']
        for name in [*names, 'public.md']:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('opaque fixture marker ' + name, encoding='utf-8')
        with patch.object(self.index, '_read_text', wraps=self.index._read_text) as read:
            self.assertEqual(self.index.index_directory('w', root), 1)
            self.assertEqual([call.args[0].name for call in read.call_args_list], ['public.md'])
        outgoing = []
        def embed(texts):
            outgoing.extend(sanitize_text(value) for value in texts)
            return [[1., 0.] for _ in texts]
        self.index.embed_directory('w', root, embed)
        self.assertEqual(len(outgoing), 1)
        self.assertIn('public.md', outgoing[0])
        for name in names:
            self.assertTrue(private_path(name))

    def test_existing_private_index_rows_are_purged_on_open(self):
        with self.index.db() as db:
            db.execute('INSERT INTO workspace_source(workspace_id,source_id,marker,updated_at) VALUES(?,?,?,?)',
                       ('w', 'file:secrets/legacy.txt', 'old', 0))
            db.execute('INSERT INTO workspace_chunk_fts VALUES(?,?,?,?)',
                       ('legacy fixture', 'file:secrets/legacy.txt#0', 'w', 'file:secrets/legacy.txt'))
        reopened = WorkspaceIndex(self.index.path)
        self.assertEqual(reopened.list_sources('w'), {})
        self.assertEqual(reopened.search('w', 'legacy'), [])

    def test_layers_and_detail_pagination_keep_provenance_and_scope(self):
        chunks = [f'章节 {number}\n细节内容 {number}' for number in range(30)]
        self.index.index_source('w', 'file:notes#2026.md', chunks, 'version-1')
        overview = self.index.read_source('w', 'file:notes#2026.md', level='overview')
        self.assertEqual(json.loads(overview['content'])['sectionCount'], 30)
        self.assertEqual(overview['version'], 'version-1')
        pages = []
        offset = 0
        while True:
            page = self.index.read_source('w', 'file:notes#2026.md', offset=offset, limit=31)
            pages.append(page['content'])
            if page['next_offset'] is None:
                break
            offset = page['next_offset']
        self.assertEqual(''.join(pages), '\n'.join(chunks))
        self.assertIsNone(self.index.read_source('other', 'file:notes#2026.md'))
        self.assertEqual(self.index.overview('w')['totalSources'], 1)

    def test_global_recall_exposes_coverage_and_source_overviews(self):
        root = self.root / 'workspace'
        root.mkdir()
        (root / 'guide.md').write_text('项目介绍\n部署方式\n服务职责', encoding='utf-8')
        resources = Mock()
        resources.get_workspace.return_value = {'workspace_id': 'w', 'repository': str(root)}
        resources.get_workspace_checkout.return_value = None
        resources.resolve_local_repository.return_value = root
        result = recall_workspace(resources, Mock(), self.index, None, None, 'w', '总结整体项目介绍')
        self.assertIn('totalSources', result['hits'][0])
        self.assertIn('workspace:file:guide.md', repr(result))

    def test_workspace_import_persists_files_and_rules(self):
        resources = ResourceStore(self.root / 'resources.db')
        app = FastAPI()
        app.include_router(create_workspace_import_router(resources, self.root / 'imports'))
        with TestClient(app) as client:
            response = client.post('/harness/workspaces/import', data={'name': 'fixture workspace'}, files=[
                ('files', ('AGENTS.md', b'fixture workspace rules', 'text/plain')),
                ('files', ('docs/guide.md', b'fixture public guide', 'text/markdown')),
            ])
            self.assertEqual(response.status_code, 200)
            files = client.get('/harness/workspaces/' + response.json()['workspace']['workspace_id'] + '/files').json()
            self.assertEqual({file['name'] for file in files['files']}, {'AGENTS.md', 'docs/guide.md'})
        self.assertEqual(response.status_code, 200)
        workspace = response.json()['workspace']
        self.assertEqual(load_workspace_rules(resources, workspace['workspace_id']), 'fixture workspace rules')
        self.assertTrue((Path(workspace['repository']) / 'docs/guide.md').is_file())

    def test_workspace_import_rejects_private_paths_traversal_and_duplicates(self):
        resources = ResourceStore(self.root / 'resources.db')
        app = FastAPI()
        app.include_router(create_workspace_import_router(resources, self.root / 'imports'))
        with TestClient(app) as client:
            for path in ['../outside.txt', 'folder/.env', 'secrets/key.txt', '/absolute.txt', 'config.private.json']:
                with self.subTest(path=path):
                    response = client.post('/harness/workspaces/import', data={'name': 'fixture'},
                                           files={'files': (path, b'opaque fixture', 'text/plain')})
                    self.assertEqual(response.status_code, 400)
            response = client.post('/harness/workspaces/import', data={'name': 'fixture'},
                                   files=[('files', ('same.md', b'a')), ('files', ('SAME.md', b'b'))])
            self.assertEqual(response.status_code, 400)
        self.assertEqual(resources.list_workspaces(), [])

    def test_import_failure_removes_staging_and_unregistered_files(self):
        resources = Mock()
        resources.create_workspace.side_effect = RuntimeError('fixture storage failure')
        app = FastAPI()
        directory = self.root / 'imports'
        app.include_router(create_workspace_import_router(resources, directory))
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post('/harness/workspaces/import', data={'name': 'fixture'},
                                   files={'files': ('guide.md', b'fixture public guide')})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(list(directory.iterdir()), [])

    def test_skill_entrypoint_includes_workspace_evidence(self):
        settings = replace(self.settings, model_api_key='PLACEHOLDER')
        skills = Mock()
        skills.open_resource_session.return_value = Mock(descriptors=())
        recall = Mock(return_value={'hits': ['WORKSPACE_EVIDENCE_FIXTURE'], 'semantic': []})
        engine = AgentEngine(settings, Storage(settings), TaskManager(settings), skills=skills,
                             context_service=self.context, workspace_recall=recall)
        engine.model.chat = Mock(return_value='{}')
        model = ScriptedModel(responses=[AIMessage(content='fixture result')])
        with patch('python_backend.agents.build_chat_model', return_value=model):
            events = list(engine.stream('skills', 'a', '按工作区资料回答', workspace_id='w'))
        self.assertEqual(events[-1]['type'], 'complete')
        self.assertTrue(recall.called)
        self.assertIn('WORKSPACE_EVIDENCE_FIXTURE', repr(model.requests))

    def test_workspace_read_tool_enforces_bound_scope_and_layers(self):
        self.index.index_source('w', 'doc:a', ['owned fixture content'], 'v1')
        self.index.index_source('other', 'doc:b', ['foreign fixture content'], 'v1')
        self.context.begin('a', 'w', '1', 'fixture request', [])
        tools = {tool.name: tool for tool in build_context_tools(self.context, 'a', self.index.read_source)}
        page = tools['read_context_source'].invoke({'source_id': 'workspace:doc:a', 'level': 'abstract'})
        self.assertIn('owned', page['content'])
        self.assertEqual(page['source_id'], 'workspace:doc:a')
        self.assertIn('error', tools['read_context_source'].invoke({'source_id': 'workspace:doc:b'}))

    def test_openviking_uses_abstract_overview_and_bounded_details(self):
        peer = self.context.store.bind('a', 'w')['peer_id']
        uri = f'viking://user/fixture/peers/{peer}/memories/events/a.md'
        client = OpenVikingClient('http://127.0.0.1:1')
        calls = []
        def request(method, path, actor, payload=None, **kwargs):
            calls.append((path, payload))
            if path.startswith('/api/v1/search/'):
                return {'memories': [{'uri': uri, 'abstract': 'L0 fixture', 'level': 2}]}
            if path.startswith('/api/v1/content/overview'):
                return 'L1 fixture'
            if path.startswith('/api/v1/content/read'):
                return 'L2 fixture'
            raise AssertionError(path)
        client.request = request
        hits = client.recall(peer, 'fixture query')
        self.assertEqual(hits[0]['loadedLayers'], ['L0', 'L1', 'L2'])
        self.assertFalse(calls[0][1]['read_content'])
        self.assertEqual(parse_qs(urlsplit(calls[-1][0]).query)['limit'], ['80'])
        self.assertNotIn('/a.md', parse_qs(urlsplit(calls[1][0]).query)['uri'][0])

    def test_remote_tool_pages_by_lines_without_whole_file_read(self):
        scope = self.context.begin('a', 'w', '1', 'fixture request', [])
        uri = f"viking://user/fixture/peers/{scope['peer_id']}/memories/events/a.md"
        self.context.client = Mock()
        self.context.client.read.return_value = '\n'.join(['fixture'] * 80)
        tools = {tool.name: tool for tool in build_context_tools(self.context, 'a')}
        result = tools['read_context_source'].invoke({'source_id': uri, 'offset': 2, 'limit': 4000})
        self.assertEqual(result['next_offset'], 82)
        self.assertEqual(result['offsetUnit'], 'lines')
        self.context.client.read.assert_called_once_with(scope['peer_id'], uri, offset=2, limit=80)

    def test_blocked_memory_cannot_be_read_through_home_alias(self):
        scope = self.context.begin('a', 'w', '1', 'fixture request', [])
        uri = f"viking://user/fixture/peers/{scope['peer_id']}/memories/events/a.md"
        self.context.store.block_uri('a', uri)
        self.context.client = Mock()
        tools = {tool.name: tool for tool in build_context_tools(self.context, 'a')}
        alias = f"viking://~/peers/{scope['peer_id']}/memories/events/a.md"
        self.assertIn('error', tools['read_context_source'].invoke({'source_id': alias}))
        self.context.client.read.assert_not_called()

    def test_multihop_retrieval_stops_when_coverage_is_sufficient(self):
        engine = self.engine()
        engine.settings = replace(self.settings, model_api_key='PLACEHOLDER')
        engine.model.chat = Mock(side_effect=[json.dumps({'sufficient': False, 'queries': ['next evidence']}),
                                              json.dumps({'sufficient': True})])
        engine._workspace_evidence = Mock(return_value=['second evidence with source fixture'])
        stream = engine._expand_evidence('关联问题', 'first evidence with source fixture', 'w', None)
        events = []
        while True:
            try:
                events.append(next(stream))
            except StopIteration as done:
                evidence = done.value
                break
        self.assertIn('second evidence', evidence)
        self.assertEqual(events[-1]['details']['stopReason'], 'coverage_sufficient')
        self.assertEqual(events[-1]['details']['hops'], 1)

    def test_multihop_repeated_query_stops_without_new_evidence(self):
        engine = self.engine()
        engine.settings = replace(self.settings, model_api_key='PLACEHOLDER')
        engine.model.chat = Mock(return_value=json.dumps({'sufficient': False, 'queries': ['关联问题']}))
        events = list(engine._expand_evidence('关联问题', 'first evidence with source fixture', 'w', None))
        self.assertEqual(events[-1]['details']['stopReason'], 'no_new_evidence')
        self.assertEqual(engine.model.chat.call_count, 1)

    def test_segmented_checkpoints_remain_queryable_after_summary_updates(self):
        self.context.begin('a', 'w', '1', 'fixture task', [])
        scope = self.context.store.conversation('a')
        self.context.store.save_summary('a', '4', 'first overview', scope['revision'],
                                       segment='TOPIC_ALPHA fixture source 1', start='1')
        scope = self.context.store.conversation('a')
        self.context.store.save_summary('a', '8', 'new overview', scope['revision'],
                                       segment='TOPIC_BETA fixture source 5', start='5')
        hits = self.context.store.search_checkpoints('a', 'TOPIC_ALPHA')
        self.assertEqual(hits[0]['through_id'], '4')
        self.assertIn('TOPIC_ALPHA', self.context.store.source('a', 'checkpoint:4')['answer'])
        self.assertEqual(self.context.store.search_checkpoints('other', 'TOPIC_ALPHA'), [])
        self.context.forget('a')
        self.assertEqual(self.context.store.search_checkpoints('a', 'TOPIC_ALPHA'), [])

    def test_task_api_accepts_a_quote_from_the_sanitized_user_source(self):
        question = '必须保护 https://example.test/service'
        scope = self.context.begin('a', 'w', '1', question, [])
        app = FastAPI()
        app.include_router(create_context_router(self.context))
        with TestClient(app) as client:
            response = client.put('/harness/context/a/task', json={'revision': scope['revision'],
                'goal': 'fixture task', 'constraints': [{'key': 'privacy', 'quote': sanitize_text(question),
                                                        'sourceId': '1'}]})
        self.assertEqual(response.status_code, 200)

    def test_legacy_chat_route_carries_workspace_to_worker_and_context(self):
        queue = ExecutionStore(self.root / 'execution.db')
        queue.has_live_worker = lambda: True
        engine = self.engine(workspace_recall=lambda *_: {'hits': ['fixture workspace evidence'], 'semantic': []})
        engine._search = Mock(return_value=[])
        worker = ExecutionWorker(queue, AgentEngineRuntime(engine), engine.tasks, object())
        app = FastAPI()
        app.include_router(create_execution_router(ExecutionApplicationService(queue), lambda _: True))
        def execute():
            for _ in range(200):
                if worker.run_once():
                    return
                time.sleep(.01)
        thread = threading.Thread(target=execute)
        thread.start()
        try:
            with TestClient(app) as client:
                response = client.get('/agent/chat/stream', params={'query': 'fixture question',
                                     'conversationId': 'a', 'workspaceId': 'w'})
            self.assertEqual(response.status_code, 200)
            self.assertIn('context_snapshot', response.text)
            self.assertEqual(self.context.store.conversation('a')['workspace_id'], 'w')
        finally:
            thread.join(timeout=5)

    def test_same_active_request_cannot_switch_workspace(self):
        queue = ExecutionStore(self.root / 'execution.db')
        queue.enqueue('a', 'chat', 'fixture question', None, workspace_id='w')
        with self.assertRaises(ActiveExecutionError):
            queue.enqueue('a', 'chat', 'fixture question', None, workspace_id='other')


if __name__ == '__main__':
    unittest.main()
