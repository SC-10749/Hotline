from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from .store import ActiveExecutionError, ExecutionStore
from .worker import ExecutionWorker


class FakeTasks:
    def __init__(self):
        self.events = {}

    def register(self, conversation_id):
        event = threading.Event()
        self.events[conversation_id] = event
        return event

    def stop(self, conversation_id):
        event = self.events.get(conversation_id)
        if not event:
            return False
        event.set()
        return True

    def remove(self, conversation_id):
        self.events.pop(conversation_id, None)


class FakeEngine:
    def stream(self, agent, conversation_id, query, file_id):
        yield {"type": "thinking", "content": "started"}
        yield {"type": "text", "content": query}
        yield {"type": "complete", "content": ""}


class ExecutionStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = ExecutionStore(Path(self.temp_dir.name) / "execution.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_enqueue_is_idempotent_for_same_active_request(self):
        first = self.store.enqueue("conversation-1", "chat", "hello", None)
        retry = self.store.enqueue("conversation-1", "chat", "hello", None)

        self.assertEqual(first["run_id"], retry["run_id"])
        self.assertEqual(self.store.get_status(first["run_id"]), "queued")

    def test_active_conversation_rejects_different_request(self):
        self.store.enqueue("conversation-1", "chat", "hello", None)

        with self.assertRaises(ActiveExecutionError):
            self.store.enqueue("conversation-1", "chat", "different", None)

    def test_queued_cancel_is_terminal_and_replayable(self):
        run = self.store.enqueue("conversation-1", "chat", "hello", None)

        self.assertTrue(self.store.request_cancel("conversation-1"))
        self.assertEqual(self.store.get_status(run["run_id"]), "cancelled")
        self.assertEqual(self.store.events_after(run["run_id"])[0]["event"], {
            "type": "error", "content": "任务已停止"
        })

    def test_worker_persists_events_and_terminal_state(self):
        run = self.store.enqueue("conversation-1", "chat", "hello", None)
        worker = ExecutionWorker(self.store, FakeEngine(), FakeTasks(), object())

        self.assertTrue(worker.run_once())
        self.assertEqual(self.store.get_status(run["run_id"]), "completed")
        events = self.store.events_after(run["run_id"])
        self.assertEqual([item["event"]["type"] for item in events], ["thinking", "text", "complete"])
        self.assertFalse(worker.run_once())

    def test_event_replay_cursor_is_scoped_to_run(self):
        first = self.store.enqueue("conversation-1", "chat", "one", None)
        second = self.store.enqueue("conversation-2", "chat", "two", None)
        first_id = self.store.append_event(first["run_id"], {"type": "text", "content": "a"})
        self.store.append_event(second["run_id"], {"type": "text", "content": "b"})
        later_id = self.store.append_event(first["run_id"], {"type": "complete", "content": ""})

        replay = self.store.events_after(first["run_id"], first_id)
        self.assertEqual(len(replay), 1)
        self.assertEqual(replay[0]["event_id"], later_id)

    def test_event_cursor_resolves_completed_run_for_reconnect(self):
        run = self.store.enqueue("conversation-1", "chat", "hello", None)
        event_id = self.store.append_event(run["run_id"], {"type": "complete", "content": ""})
        self.store.finish(run["run_id"], "completed")

        replayed_run = self.store.find_run_by_event("conversation-1", "chat", "hello", None, event_id)
        self.assertEqual(replayed_run["run_id"], run["run_id"])


if __name__ == "__main__":
    unittest.main()
