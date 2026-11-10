from __future__ import annotations

import copy
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ...agents import AgentEngine
from ...api.routers.execution import create_execution_router
from ...application.execution_service import ExecutionApplicationService
from ...modules.execution.store import ExecutionStore
from ...runtime import AgentEngineRuntime
from ...workers.execution_worker import ExecutionWorker
from .snapshots import context_snapshot


class ContextSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.settings = SimpleNamespace(model_api_key='', model_name='offline-model', tavily_api_key='')
        self.storage = Mock()
        self.storage.save_question.return_value = 'current'
        self.storage.session_messages.return_value = []
        self.storage.conversation_file_id.return_value = None
        self.storage.get_file.return_value = None
        self.storage.get_document.return_value = None
        self.tasks = Mock()
        self.tasks.register.side_effect = lambda _: threading.Event()
        self.engine = AgentEngine(self.settings, self.storage, self.tasks)
        self.engine.model.chat = Mock(return_value='answer')

    def snapshots(self, events):
        return [event['snapshot'] for event in events if event['type'] == 'context_snapshot']

    def test_history_snapshot_matches_prepared_messages_and_is_detached(self):
        history = [SimpleNamespace(id=f'row-{i}', question=f'question-{i}', answer=f'answer-{i}') for i in range(6)]
        history += [SimpleNamespace(id='empty', question='unused', answer=''),
                    SimpleNamespace(id='current', question='current', answer='not history')]
        history[5].answer = 'x' * 1600
        self.storage.session_messages.return_value = history
        events = list(self.engine.stream('chat', 'conversation', 'current question'))
        snapshot = self.snapshots(events)[0]
        actual = self.engine.model.chat.call_args.args[0]
        self.assertEqual([{'role': item['role'], 'content': item['content']} for item in snapshot['messages']], actual)
        self.assertEqual(snapshot['sources']['historyIds'], ['row-2', 'row-3', 'row-4', 'row-5'])
        self.assertEqual(len(actual[-2]['content']), 1500)
        history[5].answer = 'CHANGED_HISTORY'
        self.settings.model_name = 'CHANGED_MODEL'
        self.assertNotIn('CHANGED_', repr(snapshot))
        self.assertEqual(snapshot['modelName'], 'offline-model')
        self.assertFalse(snapshot['modelConfigured'])

    def test_retrieval_route_sql_and_answer_capture_actual_inputs(self):
        self.settings.model_api_key = 'placeholder-key'
        self.storage.get_file.return_value = SimpleNamespace(embed=1, extractedText='UNUSED_FALLBACK')
        self.engine.vector_store = Mock()
        self.engine.vector_store.search_text2sql.return_value = ['RETRIEVAL_SENTINEL']
        self.engine.model.chat.side_effect = ['{"route":"text2sql"}', 'SELECT content FROM vector_file_info LIMIT 1', 'grounded answer']
        self.engine._search = Mock()
        events = list(self.engine.stream('file', 'conversation', '统计文档数量', 'file-id'))
        snapshots = self.snapshots(events)
        self.assertEqual([item['stage'] for item in snapshots], ['retrieval-route', 'retrieval-sql', 'answer'])
        for snapshot, call in zip(snapshots, self.engine.model.chat.call_args_list):
            self.assertEqual([item['content'] for item in snapshot['messages']], [item['content'] for item in call.args[0]])
        self.assertEqual(snapshots[-1]['sources']['fileId'], 'file-id')
        self.assertTrue(snapshots[-1]['sources']['grounded'])
        self.assertEqual(snapshots[-1]['sources']['retrievalRoute'], 'text2sql')
        self.assertIn('RETRIEVAL_SENTINEL', repr(snapshots[-1]))
        self.assertNotIn('UNUSED_FALLBACK', repr(snapshots[-1]))
        self.engine._search.assert_not_called()
        self.assertEqual(events[-1]['type'], 'complete')

    def test_missing_source_and_web_evidence_keep_valid_context_shape(self):
        self.engine._search = Mock(return_value=[{'title': 'evidence', 'content': 'SEARCH_SENTINEL', 'url': 'http://127.0.0.1:9/example'}])
        events = list(self.engine.stream('chat', 'conversation', 'question', 'missing-file'))
        snapshot = self.snapshots(events)[0]
        self.assertFalse(snapshot['sources']['grounded'])
        self.assertEqual(snapshot['sources']['referenceCount'], 1)
        self.assertIn('SEARCH_SENTINEL', snapshot['messages'][-1]['content'])
        self.assertEqual(events[-1]['type'], 'complete')

    def test_failure_retains_context_and_source_failure_does_not_invent_one(self):
        self.engine.model.chat.side_effect = RuntimeError('offline model')
        events = list(self.engine.stream('chat', 'conversation', 'question'))
        self.assertEqual(len(self.snapshots(events)), 1)
        self.assertEqual(events[-1]['type'], 'error')
        self.storage.get_file.side_effect = RuntimeError('source unavailable')
        events = list(self.engine.stream('file', 'conversation', 'question', 'file-id'))
        self.assertEqual(self.snapshots(events), [])
        self.assertEqual(events[-1]['type'], 'error')

    def test_local_fallback_is_labelled_as_unconfigured(self):
        self.engine.model.chat.return_value = ''
        events = list(self.engine.stream('chat', 'conversation', 'question'))
        self.assertFalse(self.snapshots(events)[0]['modelConfigured'])
        self.assertEqual(events[-1]['type'], 'complete')

    def test_preview_limits_redaction_and_tool_protocol_do_not_change_inputs(self):
        messages = [{'role': 'user', 'content': 'password=PLACEHOLDER_SECRET ' + 'x' * 7000,
                     'tool_calls': [{'id': 'call-A', 'name': 'read_skill', 'args': {'api_key': 'PLACEHOLDER_KEY'}}]}] * 28
        tools = [{'name': 'read_skill', 'description': 'x' * 13000, 'parameters': {}}] * 10
        original = copy.deepcopy(messages)
        event = context_snapshot('answer', messages, tools=tools, sources={'connection_string': 'PLACEHOLDER_DSN'})
        snapshot = event['snapshot']
        self.assertEqual(snapshot['messageCount'], 28)
        self.assertEqual(len(snapshot['messages']), 24)
        self.assertEqual(snapshot['omittedMessages'], 4)
        self.assertEqual(snapshot['omittedTools'], 2)
        self.assertTrue(snapshot['messages'][0]['truncated'])
        self.assertTrue(snapshot['tools'][0]['truncated'])
        self.assertLessEqual(len(snapshot['messages'][0]['content']), 6001)
        self.assertNotIn('PLACEHOLDER_', repr(snapshot))
        self.assertEqual(messages, original)

    def test_worker_persistence_api_and_retry_are_scoped_to_each_run(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = ExecutionStore(Path(directory) / 'execution.db')
            worker = ExecutionWorker(queue, AgentEngineRuntime(self.engine), self.tasks, object())
            first = queue.enqueue('conversation', 'chat', 'FIRST_INPUT', None)
            worker.run_once()
            saved = [item for item in queue.get_events(first['run_id']) if item['event']['type'] == 'context_snapshot']
            self.assertEqual(len(saved), 1)
            self.settings.model_name = 'changed-model'
            second = queue.retry_run(first['run_id'])
            app = FastAPI()
            app.include_router(create_execution_router(ExecutionApplicationService(queue), lambda _: True))
            client = TestClient(app)
            self.assertEqual(client.get(f"/execution/runs/{second['run_id']}/context").json()['items'], [])
            worker.run_once()
            first_context = client.get(f"/execution/runs/{first['run_id']}/context").json()['items']
            second_context = client.get(f"/execution/runs/{second['run_id']}/context").json()['items']
            self.assertEqual(first_context, saved)
            self.assertEqual(first_context[0]['event']['snapshot']['modelName'], 'offline-model')
            self.assertEqual(second_context[0]['event']['snapshot']['modelName'], 'changed-model')
            self.assertNotEqual(first_context[0]['event_id'], second_context[0]['event_id'])
            self.assertEqual(client.get('/execution/runs/missing/context').status_code, 404)
            self.assertEqual(queue.list_runs()[1], 2)
            replay = client.get(f"/execution/runs/{first['run_id']}/stream").text
            self.assertIn('context_snapshot', replay)
            self.assertIn('FIRST_INPUT', replay)
            self.assertEqual(ExecutionStore(queue.path).get_events(first['run_id']), queue.get_events(first['run_id']))

    def test_parallel_workers_do_not_mix_context(self):
        barrier = threading.Barrier(2)
        self.storage.save_question.side_effect = lambda conversation, *args: f'row-{conversation}'

        def answer(messages):
            barrier.wait(timeout=5)
            return messages[-1]['content']

        self.engine.model.chat.side_effect = answer
        with tempfile.TemporaryDirectory() as directory:
            queue = ExecutionStore(Path(directory) / 'execution.db')
            runs = [queue.enqueue(f'conversation-{index}', 'chat', f'INPUT-{index}', None) for index in range(2)]
            workers = [ExecutionWorker(queue, AgentEngineRuntime(self.engine), self.tasks, object()) for _ in range(2)]
            with ThreadPoolExecutor(max_workers=2) as pool:
                self.assertTrue(all(pool.map(lambda worker: worker.run_once(), workers)))
            for index, run in enumerate(runs):
                self.assertEqual(queue.get_status(run['run_id']), 'completed')
                snapshot = self.snapshots([item['event'] for item in queue.get_events(run['run_id'])])[0]
                self.assertEqual(snapshot['messages'][-1]['content'], f'INPUT-{index}')
                self.assertNotIn(f'INPUT-{1 - index}', repr(snapshot))


if __name__ == '__main__':
    unittest.main()
