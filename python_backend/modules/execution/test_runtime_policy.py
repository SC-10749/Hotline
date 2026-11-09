from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from ...agents import AgentEngine
from ...config import Settings
from ...infrastructure.resource_store import ResourceStore
from ...modules.execution import tools as tool_module
from ...workers.execution_worker import ExecutionWorker


class StubStore:
    def __init__(self, run: dict[str, Any] | None):
        self.run = run
        self.events: list[dict[str, Any]] = []
        self.finished: list[tuple[str, str, str | None]] = []

    def claim_next(self, worker_id: str):
        return self.run

    def heartbeat_worker(self, worker_id, process_id, current_run_id=None, capacity=None, runtime_version=None):
        return None

    def heartbeat_run(self, run_id, worker_id):
        return None

    def is_cancel_requested(self, run_id):
        return False

    def append_event(self, run_id, event):
        self.events.append(event)
        return len(self.events)

    def finish(self, run_id, status, error=None):
        self.finished.append((run_id, status, error))

    def get_run(self, run_id):
        return self.run

    def retry_run(self, run_id):
        return None

    def remove_worker(self, worker_id):
        return None


class StubRuntime:
    def __init__(self, events):
        self.events = events

    def stream(self, agent, conversation_id, query, file_id):
        yield from self.events


class StubTasks:
    def stop(self, conversation_id):
        return None

    def remove(self, conversation_id):
        return None


class StubObjectStore:
    def __init__(self, data_dir: Path):
        self.settings = type('S', (), {'data_dir': data_dir, 'generated_dir': data_dir})()
        self.backend = 'local'


class StepEventTests(unittest.TestCase):
    def test_retrieval_route_emits_step_event(self):
        engine = AgentEngine(Settings(model_api_key=''), None, None, None, None, None)
        events = list(engine._choose_retrieval('总共有多少条记录'))
        steps = [event for event in events if event.get('type') == 'step' and event.get('status') == 'completed']
        self.assertTrue(steps)
        self.assertEqual(steps[0]['stage'], 'retrieval_route')
        self.assertIn('durationMs', steps[0])
        self.assertNotIn('content', steps[0]['details'] if 'details' in steps[0] else {})

    def test_step_event_keeps_metadata_only(self):
        event = AgentEngine.step('retrieval', '召回 3 条片段', 12, hits=3)
        self.assertEqual(event['type'], 'step')
        self.assertEqual(event['stage'], 'retrieval')
        self.assertEqual(event['durationMs'], 12)
        self.assertEqual(event['details'], {'hits': 3})


class ToolPolicyTests(unittest.TestCase):
    def tearDown(self):
        tool_module.set_tool_policy(allowed=None, blocked=False)

    def test_allowed_list_blocks_other_tools(self):
        tool_module.set_tool_policy(allowed=['read_skill'])
        with self.assertRaises(ValueError):
            tool_module.prepare_tool_call('write_file', {})
        tool_module.prepare_tool_call('read_skill', {})

    def test_disabled_agent_blocks_all_tools(self):
        tool_module.set_tool_policy(blocked=True)
        with self.assertRaises(ValueError):
            tool_module.prepare_tool_call('read_skill', {})


class AgentAssemblyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.resources = ResourceStore(self.root / 'harness-resources.db')

    def tearDown(self):
        self.temp.cleanup()

    def _worker(self, store, policy):
        return ExecutionWorker(store, StubRuntime([]), StubTasks(), StubObjectStore(self.root), policy=policy)

    def test_disabled_agent_blocks_tools(self):
        agent = self.resources.create_agent({'name': '受限助手', 'tools': ['read_skill']})
        worker = self._worker(StubStore(None), {})
        resolved = worker._agent_policy({'agent_id': agent['agent_id']})
        self.assertFalse(resolved['enabled'])
        self.assertEqual(resolved['tools'], ['read_skill'])

    def test_enabled_agent_exposes_tools_and_skills(self):
        agent = self.resources.create_agent({
            'name': '装配助手',
            'tools': ['read_skill'], 'skills': ['skill-a'],
        })
        self.resources.set_agent_status(agent['agent_id'], True)
        worker = self._worker(StubStore(None), {})
        resolved = worker._agent_policy({'agent_id': agent['agent_id']})
        self.assertTrue(resolved['enabled'])
        self.assertEqual(resolved['tools'], ['read_skill'])
        self.assertEqual(resolved['skills'], ['skill-a'])

    def test_run_without_agent_has_no_policy(self):
        worker = self._worker(StubStore(None), {})
        self.assertEqual(worker._agent_policy({'agent_id': ''}), {})


class TokenBudgetTests(unittest.TestCase):
    def test_budget_exceeded_fails_the_run(self):
        store = StubStore({'run_id': 'run-1', 'conversation_id': 'conv-1', 'agent': 'chat',
                           'query': 'q', 'file_id': None, 'status': 'running'})
        worker = ExecutionWorker(store, StubRuntime([{'type': 'usage', 'content': '模型用量',
                                                       'usage': {'totalTokens': 30}}]),
                                 StubTasks(), StubObjectStore(Path(tempfile.gettempdir())),
                                 policy={'defaultTokenBudget': 10})
        worker.run_once()
        self.assertEqual(store.finished[0][1], 'failed')
        self.assertEqual(store.finished[0][2], 'token budget exceeded')
        usage_events = [event for event in store.events if event.get('type') == 'usage']
        self.assertEqual(usage_events[0]['usage']['runTotal'], 30)
        self.assertEqual(usage_events[0]['usage']['budget'], 10)

    def test_zero_budget_means_unlimited(self):
        store = StubStore({'run_id': 'run-1', 'conversation_id': 'conv-1', 'agent': 'chat',
                           'query': 'q', 'file_id': None, 'status': 'running'})
        worker = ExecutionWorker(store, StubRuntime([{'type': 'usage', 'content': '模型用量',
                                                       'usage': {'totalTokens': 9999}},
                                                      {'type': 'complete', 'content': ''}]),
                                 StubTasks(), StubObjectStore(Path(tempfile.gettempdir())),
                                 policy={'defaultTokenBudget': 0})
        worker.run_once()
        self.assertEqual(store.finished[0][1], 'completed')


if __name__ == '__main__':
    unittest.main()
