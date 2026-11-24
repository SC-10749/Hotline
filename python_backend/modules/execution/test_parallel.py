from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ...api.routers.execution import create_execution_router
from ...application.execution_service import ExecutionApplicationService
from .parallel import allocate_task_workspace
from .store import ActiveExecutionError, ExecutionStore


class ParallelStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = ExecutionStore(Path(self.temp_dir.name) / "execution.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parallel_enqueue_creates_one_run_per_task(self):
        runs = self.store.enqueue_parallel(
            "conversation-1",
            [
                {"agent": "chat", "query": "任务甲"},
                {"agent": "chat", "query": "任务乙"},
                {"agent": "chat", "query": "任务丙"},
            ],
            parent_run_id="parent-1",
        )

        self.assertEqual(len(runs), 3)
        self.assertEqual([run["slot"] for run in runs], ["sub-0", "sub-1", "sub-2"])
        self.assertEqual({run["parent_run_id"] for run in runs}, {"parent-1"})
        self.assertEqual({run["status"] for run in runs}, {"queued"})
        self.assertEqual(len({run["run_id"] for run in runs}), 3)

    def test_parallel_enqueue_is_atomic(self):
        with self.assertRaises(ValueError):
            self.store.enqueue_parallel(
                "conversation-1",
                [
                    {"agent": "chat", "query": "任务甲"},
                    {"agent": "chat", "query": "  "},
                ],
            )

        self.assertEqual(self.store.list_runs()[1], 0)

    def test_slot_runs_run_side_by_side_in_one_conversation(self):
        self.store.enqueue_parallel(
            "conversation-1",
            [{"agent": "chat", "query": "甲"}, {"agent": "chat", "query": "乙"}],
            parent_run_id="parent-1",
        )

        children = self.store.list_children("parent-1")
        self.assertEqual([run["status"] for run in children], ["queued", "queued"])
        self.assertEqual([run["slot"] for run in children], ["sub-0", "sub-1"])

    def test_same_slot_stays_exclusive(self):
        self.store.enqueue_parallel("conversation-1", [{"agent": "chat", "query": "甲"}])

        with self.assertRaises(ActiveExecutionError):
            self.store.enqueue_parallel("conversation-1", [{"agent": "chat", "query": "乙"}])

    def test_plain_run_keeps_single_active_per_conversation(self):
        self.store.enqueue("conversation-1", "chat", "普通对话", None)

        with self.assertRaises(ActiveExecutionError):
            self.store.enqueue("conversation-1", "chat", "另一轮", None)

    def test_concurrent_workers_claim_distinct_runs(self):
        self.store.enqueue_parallel(
            "conversation-1",
            [{"agent": "chat", "query": f"任务{i}"} for i in range(8)],
        )

        claimed: list[str] = []
        lock = threading.Lock()

        def worker(index: int) -> None:
            while True:
                run = self.store.claim_next(f"worker-{index}")
                if not run:
                    return
                with lock:
                    claimed.append(run["run_id"])

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(claimed), 8)
        self.assertEqual(len(set(claimed)), 8)

    def test_children_are_listed_by_parent(self):
        self.store.enqueue_parallel(
            "conversation-1",
            [{"agent": "chat", "query": "甲"}, {"agent": "chat", "query": "乙"}],
            parent_run_id="parent-1",
        )

        children = self.store.list_children("parent-1")

        self.assertEqual([child["slot"] for child in children], ["sub-0", "sub-1"])


class ToolPolicyIsolationTests(unittest.TestCase):
    def test_tool_policy_does_not_leak_between_threads(self):
        from .tools import current_tool_policy, set_tool_policy

        set_tool_policy(allowed=["read_skill"])
        try:
            seen: dict[str, object] = {}

            def other_thread() -> None:
                set_tool_policy(allowed=["other"])
                seen["other"] = current_tool_policy()["allowed"]
                set_tool_policy(allowed=None, blocked=True)
                seen["other_blocked"] = current_tool_policy()["blocked"]

            thread = threading.Thread(target=other_thread)
            thread.start()
            thread.join()

            self.assertEqual(seen["other"], ["other"])
            self.assertEqual(current_tool_policy()["allowed"], ["read_skill"])
            self.assertFalse(current_tool_policy()["blocked"])
        finally:
            set_tool_policy(allowed=None, blocked=False)


class ParallelRouterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = ExecutionStore(Path(self.temp_dir.name) / "execution.db")
        self.store.heartbeat_worker("worker-1", os.getpid(), capacity=1)
        service = ExecutionApplicationService(queue=self.store)
        app = FastAPI()
        app.include_router(create_execution_router(service, lambda _file_id: True))
        self.client = TestClient(app)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parallel_endpoint_creates_runs(self):
        response = self.client.post("/execution/runs/parallel", json={
            "conversationId": "conversation-1",
            "tasks": [
                {"agent": "chat", "query": "任务甲"},
                {"agent": "chat", "query": "任务乙"},
            ],
        })

        self.assertEqual(response.status_code, 200)
        runs = response.json()["runs"]
        self.assertEqual(len(runs), 2)
        self.assertEqual([run["slot"] for run in runs], ["sub-0", "sub-1"])

    def test_parallel_endpoint_rejects_empty_task_list(self):
        response = self.client.post("/execution/runs/parallel", json={
            "conversationId": "conversation-1",
            "tasks": [],
        })

        self.assertEqual(response.status_code, 400)

    def test_parallel_stream_fans_in_events_of_every_run(self):
        runs = self.store.enqueue_parallel(
            "conversation-1",
            [{"agent": "chat", "query": "甲"}, {"agent": "chat", "query": "乙"}],
        )
        for run in runs:
            self.store.append_event(run["run_id"], {"type": "text", "content": run["query"]})
            self.store.finish(run["run_id"], "completed")

        with self.client.stream("GET", "/execution/parallel/stream", params={
            "runIds": ",".join(run["run_id"] for run in runs),
        }) as response:
            body = "".join(response.iter_text())

        self.assertIn(run_id_of(runs, 0), body)
        self.assertIn(run_id_of(runs, 1), body)
        self.assertIn("甲", body)
        self.assertIn("乙", body)


class TaskWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_git_repository_gets_its_own_worktree(self):
        source = self.root / 'repo'
        source.mkdir()
        _git(source, 'init')
        _git(source, 'config', 'user.email', 'test@example.com')
        _git(source, 'config', 'user.name', 'test')
        (source / 'README.md').write_text('项目说明', encoding='utf-8')
        _git(source, 'add', '.')
        _git(source, 'commit', '-m', 'init')

        result = allocate_task_workspace(source, self.root / 'tasks' / 'sub-0')

        self.assertEqual(result['mode'], 'worktree')
        self.assertTrue((Path(result['workspacePath']) / 'README.md').is_file())
        self.assertNotEqual(Path(result['workspacePath']).resolve(), source.resolve())

    def test_plain_directory_is_copied(self):
        source = self.root / 'plain'
        source.mkdir()
        (source / 'notes.txt').write_text('笔记', encoding='utf-8')

        result = allocate_task_workspace(source, self.root / 'tasks' / 'sub-0')

        self.assertEqual(result['mode'], 'copy')
        self.assertTrue((Path(result['workspacePath']) / 'notes.txt').is_file())

    def test_missing_source_still_yields_an_output_directory(self):
        result = allocate_task_workspace(None, self.root / 'tasks' / 'sub-0')

        self.assertEqual(result['mode'], 'outputs-only')
        self.assertTrue(Path(result['outputsPath']).is_dir())

    def test_existing_target_is_reused(self):
        source = self.root / 'plain'
        source.mkdir()
        (source / 'notes.txt').write_text('笔记', encoding='utf-8')
        target = self.root / 'tasks' / 'sub-0'

        first = allocate_task_workspace(source, target)
        second = allocate_task_workspace(source, target)

        self.assertEqual(first['path'], second['path'])
        self.assertTrue((Path(second['workspacePath']) / 'notes.txt').is_file())

    def test_failed_allocation_degrades_to_outputs_only(self):
        source = self.root / 'plain'
        source.mkdir()
        target = self.root / 'tasks' / 'sub-0'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('占用', encoding='utf-8')

        result = allocate_task_workspace(source, target)

        self.assertEqual(result['mode'], 'outputs-only')


def _build_engine():
    from types import SimpleNamespace
    from unittest.mock import Mock

    from .engine import AgentEngine

    storage = Mock()
    storage.save_question.return_value = 'current'
    storage.session_messages.return_value = []
    storage.conversation_file_id.return_value = None
    storage.get_file.return_value = None
    storage.get_document.return_value = None
    tasks = Mock()
    tasks.register.side_effect = lambda _key: threading.Event()
    settings = SimpleNamespace(model_api_key='', model_name='offline-model', tavily_api_key='')
    engine = AgentEngine(settings, storage, tasks)
    engine.model.stream = Mock(return_value=iter(['回答']))
    engine.model.chat = Mock(return_value='回答')
    return engine, storage, tasks


class SubTaskEngineTests(unittest.TestCase):
    """子任务按独立任务键注册，且不写入父会话历史。"""

    def _engine(self):
        return _build_engine()

    def test_sub_task_uses_its_own_task_key(self):
        engine, storage, tasks = self._engine()

        list(engine.stream('chat', 'conversation', '问题', run_id='run-1',
                           task_key='conversation#sub-0', persist_history=False))

        tasks.register.assert_called_with('conversation#sub-0')

    def test_sub_task_does_not_write_session_history(self):
        engine, storage, tasks = self._engine()

        list(engine.stream('chat', 'conversation', '问题', run_id='run-1',
                           task_key='conversation#sub-0', persist_history=False))

        storage.save_question.assert_not_called()

    def test_normal_run_still_writes_history(self):
        engine, storage, tasks = self._engine()

        list(engine.stream('chat', 'conversation', '问题'))

        storage.save_question.assert_called_once()


class TaskKeyTests(unittest.TestCase):
    """任务键贯穿：注册、释放、记忆作用域、重试都按 slot 区分。"""

    def test_task_key_derives_from_slot(self):
        from .parallel import task_key_for

        self.assertEqual(task_key_for('conv', 'sub-0'), 'conv#sub-0')
        self.assertEqual(task_key_for('conv', ''), 'conv')

    def test_runtime_passes_slot_task_key_and_skips_history(self):
        from unittest.mock import Mock

        from ...runtime.agent_runtime import AgentEngineRuntime

        engine = Mock()
        runtime = AgentEngineRuntime(engine)
        runtime.stream_run({'agent': 'chat', 'conversation_id': 'conv', 'query': 'q',
                            'file_id': None, 'run_id': 'r1', 'slot': 'sub-0'})

        kwargs = engine.stream.call_args.kwargs
        self.assertEqual(kwargs['task_key'], 'conv#sub-0')
        self.assertFalse(kwargs['persist_history'])

    def test_sub_task_uses_its_own_memory_scope(self):
        from unittest.mock import Mock

        engine, storage, tasks = _build_engine()
        engine.context = Mock()

        list(engine.stream('chat', 'conversation', '问题', run_id='run-1',
                           task_key='conversation#sub-0', persist_history=False))

        self.assertEqual(engine.context.begin.call_args[0][0], 'conversation#sub-0')

    def test_retry_keeps_slot_and_parent(self):
        with tempfile.TemporaryDirectory() as temp:
            store = ExecutionStore(Path(temp) / 'execution.db')
            run = store.enqueue_parallel('conv-1', [{'agent': 'chat', 'query': '甲'}],
                                        parent_run_id='parent-1')[0]
            store.finish(run['run_id'], 'failed')

            retried = store.retry_run(run['run_id'])

            self.assertEqual(retried['slot'], 'sub-0')
            self.assertEqual(retried['parent_run_id'], 'parent-1')


class WorkerIsolationTests(unittest.TestCase):
    def test_child_run_gets_its_own_workspace(self):
        from ...workers.execution_worker import ExecutionWorker

        class FakeStore:
            def __init__(self):
                self.roots = {}
                self.events = []

            def set_workspace_root(self, run_id, workspace_root):
                self.roots[run_id] = workspace_root

            def append_event(self, run_id, event):
                self.events.append(event)
                return len(self.events)

        with tempfile.TemporaryDirectory() as temp:
            store = FakeStore()
            worker = ExecutionWorker.__new__(ExecutionWorker)
            worker.store = store
            worker.resources = None
            worker.object_store = type('Holder', (), {'settings': type('Config', (), {'data_dir': Path(temp)})()})()
            run = {'run_id': 'run-1', 'parent_run_id': 'parent-1', 'slot': 'sub-0', 'workspace_id': ''}

            root = worker._prepare_workspace(run)

            self.assertEqual(store.roots['run-1'], root)
            self.assertTrue(Path(root).is_dir())
            self.assertIn('parallel', str(Path(root)))
            self.assertTrue(store.events)

    def test_plain_run_keeps_shared_workspace(self):
        from ...workers.execution_worker import ExecutionWorker

        worker = ExecutionWorker.__new__(ExecutionWorker)
        worker.store = type('Store', (), {})()
        worker.resources = None
        worker.object_store = None

        self.assertEqual(worker._prepare_workspace({'run_id': 'run-1'}), '')


def _git(root: Path, *args: str) -> None:
    subprocess.run(['git', *args], cwd=root, check=True, capture_output=True)


def run_id_of(runs: list[dict], index: int) -> str:
    return str(runs[index]["run_id"])


if __name__ == "__main__":
    unittest.main()