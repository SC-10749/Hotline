from __future__ import annotations

import unittest
from typing import Any

from ...workers.execution_worker import ExecutionWorker


class StubStore:
    """Minimal queue double: records what the worker asks the store to do."""

    def __init__(self, run: dict[str, Any]):
        self.run = run
        self.events: list[dict[str, Any]] = []
        self.finished: list[tuple[str, str, str | None]] = []
        self.retried: list[str] = []

    def claim_next(self, worker_id: str):
        return self.run if self.run else None

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
        self.run['status'] = status
        self.finished.append((run_id, status, error))

    def get_run(self, run_id):
        return self.run

    def retry_run(self, run_id):
        self.retried.append(run_id)
        return {'run_id': 'retry-run-1', 'conversation_id': self.run['conversation_id']}

    def remove_worker(self, worker_id):
        return None


class StubRuntime:
    def stream(self, agent, conversation_id, query, file_id):
        yield {'type': 'error', 'content': 'boom'}


class StubTasks:
    def __init__(self):
        self.stopped = []

    def stop(self, conversation_id):
        self.stopped.append(conversation_id)

    def remove(self, conversation_id):
        return None


def make_worker(store, policy):
    return ExecutionWorker(store, StubRuntime(), StubTasks(), object_store=None, policy=policy)


class WorkerPolicyTest(unittest.TestCase):
    def test_failed_run_is_retried_up_to_configured_count(self):
        store = StubStore({'run_id': 'run-1', 'conversation_id': 'conv-1', 'agent': 'chat',
                           'query': 'q', 'file_id': None, 'status': 'running'})
        worker = make_worker(store, {'defaultTimeoutSeconds': 900, 'defaultRetryCount': 1})
        worker.run_once()
        self.assertEqual(store.finished[0][1], 'failed')
        self.assertEqual(store.retried, ['run-1'])
        self.assertTrue(any(event.get('type') == 'retry' for event in store.events))

    def test_retry_budget_is_not_exceeded(self):
        store = StubStore({'run_id': 'run-1', 'conversation_id': 'conv-1', 'agent': 'chat',
                           'query': 'q', 'file_id': None, 'status': 'running'})
        worker = make_worker(store, {'defaultTimeoutSeconds': 900, 'defaultRetryCount': 1})
        worker.run_once()
        worker.run_once()
        self.assertEqual(len(store.retried), 1)

    def test_cancelled_run_is_not_retried(self):
        store = StubStore({'run_id': 'run-1', 'conversation_id': 'conv-1', 'agent': 'chat',
                           'query': 'q', 'file_id': None, 'status': 'running'})

        class CancelledStore(StubStore):
            def is_cancel_requested(self, run_id):
                return True

        store = CancelledStore(store.run)
        worker = make_worker(store, {'defaultTimeoutSeconds': 900, 'defaultRetryCount': 3})
        worker.run_once()
        self.assertEqual(store.finished[0][1], 'cancelled')
        self.assertEqual(store.retried, [])


if __name__ == '__main__':
    unittest.main()
