from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ...api.routers.execution import create_execution_router
from ...api.routers.observability import create_observability_router
from ...application.execution_service import ExecutionApplicationService
from .store import ActiveExecutionError, ExecutionStore, event_level
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

    def execution_client(self, service=None):
        app = FastAPI()
        app.include_router(create_execution_router(service or ExecutionApplicationService(self.store), lambda _: True))
        return TestClient(app)

    def test_pagination_has_stable_ties_and_server_filters(self):
        ids = [self.store.enqueue(f"conversation-{i}", "chat", f"query-{i}", None)["run_id"]
               for i in range(55)]
        with self.store._db() as db:
            db.execute("UPDATE execution_run SET created_at='2026-01-01T00:00:00'")
        client = self.execution_client()
        pages = [client.get("/execution/runs", params={"limit": 25, "offset": offset}).json()
                 for offset in (0, 25, 50)]
        self.assertEqual([page["total"] for page in pages], [55, 55, 55])
        self.assertEqual([run["run_id"] for page in pages for run in page["items"]], ids[::-1])
        self.store.request_cancel_run(ids[4])
        result = client.get("/execution/runs", params={"status": "cancelled", "search": "conversation-4"}).json()
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["run_id"], ids[4])

    def test_read_only_stream_replays_cursor_and_preserves_chat_format(self):
        run = self.store.enqueue("conversation-stream", "chat", "hello", None)
        run_id = run["run_id"]
        first = self.store.append_event(run_id, {"type": "text", "content": "a"})
        second = self.store.append_event(run_id, {"type": "text", "content": "b"})
        third = self.store.append_event(run_id, {"type": "complete", "content": ""})
        self.store.finish(run_id, "completed")
        client = self.execution_client()
        response = client.get(f"/execution/runs/{run_id}/stream?after={first}",
                              headers={"Last-Event-ID": str(second)})
        self.assertEqual(response.status_code, 200)
        self.assertIn(f"id: {third}\n", response.text)
        self.assertNotIn(f"id: {second}\n", response.text)
        self.assertIn('"event_id":', response.text)
        self.assertIn('event: done\ndata: {"status": "completed"}', response.text)
        self.assertEqual(self.store.list_runs()[1], 1)
        legacy = client.get("/agent/chat/stream", params={"conversationId": "conversation-stream", "query": "hello"},
                            headers={"Last-Event-ID": str(first)})
        self.assertIn('data: {"type": "text", "content": "b"}', legacy.text)
        self.assertIn("data: [DONE]", legacy.text)
        self.assertNotIn('"event_id":', legacy.text)
        self.assertEqual(client.get("/execution/runs/missing/stream").status_code, 404)
        self.assertEqual(client.get(f"/execution/runs/{run_id}/stream?after=-1").status_code, 422)
        self.assertEqual(client.get(f"/execution/runs/{run_id}/stream", headers={"Last-Event-ID": "bad"}).status_code, 400)

    def test_stream_drains_events_written_during_terminal_transition(self):
        run = self.store.enqueue("conversation-race", "chat", "hello", None)
        run_id = run["run_id"]
        service = ExecutionApplicationService(self.store)
        original = ExecutionApplicationService.get_events
        calls = 0

        def read_then_finish(instance, target, cursor=0):
            nonlocal calls
            batch = original(instance, target, cursor)
            calls += 1
            if calls == 1:
                self.store.append_event(run_id, {"type": "text", "content": "final output"})
                self.store.finish(run_id, "completed")
            return batch

        with patch.object(ExecutionApplicationService, "get_events", read_then_finish):
            response = self.execution_client(service).get(f"/execution/runs/{run_id}/stream")
        self.assertIn("final output", response.text)
        self.assertIn("event: done", response.text)


class HarnessConsoleTests(unittest.TestCase):
    """Console-facing read models: event filters, metrics, trace export, worker state."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = ExecutionStore(Path(self.temp_dir.name) / "execution.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def observability_client(self):
        app = FastAPI()
        app.include_router(create_observability_router(self.store.list_runs, self.store.get_run,
                                                       self.store.get_events))
        return TestClient(app)

    def test_event_level_is_inferred_from_type_and_status(self):
        self.assertEqual(event_level({'type': 'error'}), 'error')
        self.assertEqual(event_level({'type': 'tool_end', 'status': 'error'}), 'error')
        self.assertEqual(event_level({'type': 'tool_end', 'status': 'ok'}), 'info')
        self.assertEqual(event_level({'type': 'text'}), 'info')
        self.assertEqual(event_level({'type': 'text', 'level': 'warn'}), 'warn')
        self.assertEqual(event_level({'type': 'text', 'level': 'error'}), 'error')

    def test_events_after_filters_by_level_tool_type_and_time(self):
        run = self.store.enqueue('conversation-filters', 'chat', 'hello', None)
        run_id = run['run_id']
        self.store.append_event(run_id, {'type': 'text', 'content': 'ok'})
        self.store.append_event(run_id, {'type': 'tool_start', 'tool': 'search'})
        self.store.append_event(run_id, {'type': 'tool_end', 'tool': 'search', 'status': 'error'})
        self.store.append_event(run_id, {'type': 'error', 'content': 'boom'})

        self.assertEqual([item['event']['type'] for item in self.store.events_after(run_id, level='error')],
                         ['tool_end', 'error'])
        self.assertEqual(len(self.store.events_after(run_id, tool='search')), 2)
        self.assertEqual(len(self.store.events_after(run_id, has_error=True)), 2)
        self.assertEqual(len(self.store.events_after(run_id, event_type='text')), 1)
        self.assertEqual(len(self.store.events_after(run_id)), 4)

        with self.store._db() as db:
            db.execute("UPDATE execution_event SET created_at='2026-03-15T00:00:00Z'")
            db.execute("UPDATE execution_event SET created_at='2026-01-15T00:00:00Z' WHERE event_id=1")
        self.assertEqual(len(self.store.events_after(run_id, since='2026-02-01T00:00:00Z')), 3)
        self.assertEqual(len(self.store.events_after(run_id, until='2026-02-01T00:00:00Z')), 1)

        cursor = self.store.events_after(run_id)[0]['event_id']
        self.assertTrue(all(item['event_id'] > cursor for item in self.store.events_after(run_id, cursor)))

    def test_observability_events_endpoint_passes_filters_through(self):
        run = self.store.enqueue('conversation-obs', 'chat', 'hello', None)
        run_id = run['run_id']
        self.store.append_event(run_id, {'type': 'tool_start', 'tool': 'search'})
        self.store.append_event(run_id, {'type': 'error', 'content': 'boom'})
        client = self.observability_client()
        self.assertEqual(len(client.get(f'/harness/observability/runs/{run_id}/events',
                                        params={'level': 'error'}).json()['items']), 1)
        self.assertEqual(len(client.get(f'/harness/observability/runs/{run_id}/events',
                                        params={'tool': 'search'}).json()['items']), 1)
        self.assertEqual(len(client.get(f'/harness/observability/runs/{run_id}/events',
                                        params={'hasError': 'true'}).json()['items']), 1)
        self.assertEqual(len(client.get(f'/harness/observability/runs/{run_id}/events',
                                        params={'type': 'tool_start'}).json()['items']), 1)
        replay = client.get(f'/harness/observability/runs/{run_id}/events', params={'after': 1}).json()
        self.assertEqual([item['event']['type'] for item in replay['items']], ['error'])
        self.assertEqual(client.get('/harness/observability/runs/missing/events').json()['items'], [])

    def test_observability_metrics_aggregates_runs_statuses_and_events(self):
        first = self.store.enqueue('conversation-m1', 'chat', 'hello', None)
        self.store.finish(first['run_id'], 'completed')
        second = self.store.enqueue('conversation-m2', 'chat', 'hello', None)
        self.store.append_event(second['run_id'], {'type': 'tool_start', 'tool': 'search'})
        self.store.append_event(second['run_id'], {'type': 'error', 'content': 'boom'})
        metrics = self.observability_client().get('/harness/observability/metrics').json()
        self.assertEqual(metrics['runs'], 2)
        self.assertEqual(metrics['byStatus']['completed'], 1)
        self.assertEqual(metrics['byStatus']['queued'], 1)
        self.assertEqual(metrics['byStatus']['failed'], 0)
        self.assertEqual(metrics['errors'], 1)
        self.assertEqual(metrics['toolCalls'], 1)
        self.assertEqual([run['run_id'] for run in metrics['recentRuns']],
                         [second['run_id'], first['run_id']])

    def test_observability_export_returns_trace_attachment(self):
        run = self.store.enqueue('conversation-export', 'chat', 'hello', None)
        self.store.append_event(run['run_id'], {'type': 'text', 'content': '你好'})
        client = self.observability_client()
        response = client.get(f"/harness/observability/runs/{run['run_id']}/export")
        self.assertEqual(response.status_code, 200)
        self.assertIn(f"filename=\"{run['run_id']}-trace.json\"", response.headers['content-disposition'])
        payload = json.loads(response.content.decode('utf-8'))
        self.assertEqual(payload['runId'], run['run_id'])
        self.assertEqual(payload['events'][0]['event']['content'], '你好')
        self.assertEqual(client.get('/harness/observability/runs/missing/export').status_code, 404)

    def test_worker_capacity_runtime_version_and_drain_state(self):
        self.store.heartbeat_worker('worker-1', 1234, None, capacity=4, runtime_version='1.2.3')
        worker = self.store.list_workers()[0]
        self.assertEqual(worker['capacity'], 4)
        self.assertEqual(worker['runtime_version'], '1.2.3')
        self.assertEqual(worker['state'], 'online')
        self.assertTrue(worker['online'])

        self.assertEqual(self.store.set_worker_state('worker-1', 'draining')['state'], 'draining')
        self.store.heartbeat_worker('worker-1', 1234, None)
        after = self.store.list_workers()[0]
        self.assertEqual(after['state'], 'draining')
        self.assertEqual(after['capacity'], 4)
        self.assertIsNone(self.store.set_worker_state('missing', 'draining'))
        with self.assertRaises(ValueError):
            self.store.set_worker_state('worker-1', 'broken')

    def test_daily_stats_counts_runs_and_model_usage(self):
        run = self.store.enqueue("conversation-stats", "chat", "hello", None)
        self.store.claim_next("worker-stats")
        self.store.append_event(run["run_id"], {"type": "usage", "content": "模型用量", "usage": {"totalTokens": 120}})
        self.store.append_event(run["run_id"], {"type": "tool_start", "content": "调用工具"})
        self.store.finish(run["run_id"], "completed")

        stats = self.store.daily_stats()
        self.assertEqual(stats["activeRuns"], 0)
        self.assertEqual(stats["runsToday"], 1)
        self.assertEqual(stats["completedToday"], 1)
        self.assertEqual(stats["tokensToday"], 120)
        self.assertEqual(stats["toolCallsToday"], 1)

    def test_worker_error_log_lists_failed_runs_and_error_events(self):
        run = self.store.enqueue("conversation-error", "chat", "boom", None)
        self.store.claim_next("worker-error")
        self.store.append_event(run["run_id"], {"type": "error", "content": "模型调用失败"})
        self.store.finish(run["run_id"], "failed", error="模型调用失败")

        items = self.store.list_worker_errors("worker-error")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["run_id"], run["run_id"])
        self.assertEqual(items[0]["error"], "模型调用失败")
        self.assertEqual([event["content"] for event in items[0]["events"]], ["模型调用失败"])
        self.assertEqual(self.store.list_worker_errors("worker-other"), [])

    def test_stale_worker_is_reported_offline(self):
        self.store.heartbeat_worker('worker-stale', 1)
        with self.store._db() as db:
            db.execute('UPDATE execution_worker SET last_seen=? WHERE worker_id=?',
                       (time.time() - 3600, 'worker-stale'))
        worker = self.store.list_workers()[0]
        self.assertEqual(worker['state'], 'offline')
        self.assertFalse(worker['online'])

    def test_existing_database_is_migrated_without_losing_rows(self):
        path = Path(self.temp_dir.name) / 'legacy.db'
        db = sqlite3.connect(path)
        db.executescript("""
            CREATE TABLE execution_run (run_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
                agent TEXT NOT NULL, query TEXT NOT NULL, file_id TEXT, status TEXT NOT NULL,
                cancel_requested INTEGER NOT NULL DEFAULT 0, worker_id TEXT, created_at TEXT NOT NULL,
                started_at TEXT, finished_at TEXT, lease_until REAL, error TEXT);
            CREATE TABLE execution_event (event_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                event_json TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE execution_worker (worker_id TEXT PRIMARY KEY, process_id INTEGER NOT NULL,
                last_seen REAL NOT NULL, current_run_id TEXT);
            INSERT INTO execution_run VALUES ('legacy-1','c-1','chat','hi',NULL,'completed',0,NULL,
                '2026-01-01T00:00:00Z',NULL,'2026-01-01T00:01:00Z',NULL,NULL);
        """)
        db.commit()
        db.close()
        store = ExecutionStore(path)
        self.assertEqual(store.get_run('legacy-1')['status'], 'completed')
        self.assertEqual(store.get_run('legacy-1')['agent_id'], '')
        store.heartbeat_worker('worker-legacy', 7)
        self.assertEqual(store.list_workers()[0]['capacity'], 1)
        self.assertEqual(store.list_workers()[0]['state'], 'online')

    def test_run_keeps_agent_and_workspace_and_retry_inherits_them(self):
        run = self.store.enqueue('conversation-links', 'chat', 'hello', None,
                                 agent_id='agent-9', workspace_id='ws-3')
        self.assertEqual(run['agent_id'], 'agent-9')
        self.assertEqual(run['workspace_id'], 'ws-3')
        self.assertEqual(self.store.get_run(run['run_id'])['agent_id'], 'agent-9')
        self.assertEqual(self.store.list_runs()[0][0]['workspace_id'], 'ws-3')
        self.store.finish(run['run_id'], 'failed')
        retried = self.store.retry_run(run['run_id'])
        self.assertEqual(retried['agent_id'], 'agent-9')
        self.assertEqual(retried['workspace_id'], 'ws-3')


if __name__ == "__main__":
    unittest.main()
