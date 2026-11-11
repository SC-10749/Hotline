from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ...api.routers.artifacts import create_artifact_router
from ...api.routers.observability import create_observability_router
from ...modules.execution.store import ExecutionStore
from ...modules.execution.test_execution import FakeEngine, FakeTasks
from python_backend.modules.storage.objects import ObjectStorage
from ...workers.execution_worker import ExecutionWorker
from .store import (ArtifactStore, legacy_run_id, register_generated_file,
                     register_legacy_artifact)


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.generated = self.root / 'generated'
        self.generated.mkdir()
        self.artifacts = ArtifactStore(self.root / 'artifacts.db')
        self.queue = ExecutionStore(self.root / 'execution.db')
        self.storage = ObjectStorage(SimpleNamespace(file_storage_backend='local', generated_dir=self.generated))

    def tearDown(self):
        self.temp.cleanup()

    def client(self, storage=None):
        app = FastAPI()
        app.include_router(create_artifact_router(self.artifacts, storage or self.storage))
        return TestClient(app)

    def register(self, run_id='run-A', key='run-A/result.txt', content=b'result', backend='local'):
        if backend == 'local':
            target = self.generated / key
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        return self.artifacts.register(run_id=run_id, name=Path(key).name, size=len(content),
                                       sha256=hashlib.sha256(content).hexdigest(), content_type='text/plain',
                                       storage_backend=backend, storage_key=key)

    def test_index_filters_real_ownership_and_survives_reopen(self):
        (self.generated / 'unregistered.txt').write_text('legacy', encoding='utf-8')
        first = self.register()
        second = self.register('run-B', 'run-B/result.txt', b'second')
        client = self.client()
        all_items = client.get('/harness/artifacts').json()
        self.assertEqual(all_items['total'], 2)
        self.assertEqual({item['run_id'] for item in all_items['items']}, {'run-A', 'run-B'})
        selected = client.get('/harness/artifacts?runId=run-A').json()
        self.assertEqual([item['artifact_id'] for item in selected['items']], [first['artifact_id']])
        self.assertNotIn('storage_key', selected['items'][0])
        self.assertEqual(client.get('/harness/artifacts?runId=missing').json()['items'], [])
        reopened = ArtifactStore(self.root / 'artifacts.db')
        self.assertEqual(reopened.get(second['artifact_id']), second)
        self.assertEqual(self.register()['artifact_id'], first['artifact_id'])

    def test_pagination_is_stable_and_counts_matching_run(self):
        ids = [self.register('run-A', f'run-A/{number}.txt')['artifact_id'] for number in range(5)]
        self.register('run-B', 'run-B/other.txt')
        with self.artifacts._db() as db:
            db.execute("UPDATE run_artifact SET created_at='2026-01-01T00:00:00Z'")
        pages = [self.client().get('/harness/artifacts', params={'runId': 'run-A', 'limit': 2, 'offset': offset}).json()
                 for offset in (0, 2, 4)]
        self.assertEqual([page['total'] for page in pages], [5, 5, 5])
        self.assertEqual([item['artifact_id'] for page in pages for item in page['items']], ids[::-1])

    def test_registration_rejects_traversal_and_conflicting_replacement(self):
        record = self.register()
        for key in ('../outside.txt', '/absolute.txt', 'C:/file.txt', 'nested\\file.txt'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.artifacts.register(run_id='run-A', name='test', size=1, sha256='a' * 64,
                                        content_type='text/plain', storage_backend='local', storage_key=key)
        with self.assertRaises(ValueError):
            self.artifacts.register(**{key: record[key] for key in ('run_id', 'name', 'size', 'content_type',
                                                                  'storage_backend', 'storage_key')}, sha256='b' * 64)
        self.assertEqual(self.artifacts.get(record['artifact_id'])['sha256'], record['sha256'])

    def test_local_download_and_missing_or_outside_files(self):
        record = self.register(content=b'expected content')
        url = f"/harness/artifacts/{record['artifact_id']}/download"
        response = self.client().get(url)
        self.assertEqual(response.content, b'expected content')
        self.assertEqual(hashlib.sha256(response.content).hexdigest(), record['sha256'])
        self.assertIn('attachment', response.headers['content-disposition'])
        self.assertEqual(self.client().get('/harness/artifacts/missing/download').status_code, 404)
        (self.generated / record['storage_key']).unlink()
        self.assertEqual(self.client().get(url).status_code, 404)
        (self.root / 'outside.txt').write_text('outside', encoding='utf-8')
        with self.artifacts._db() as db:
            db.execute('UPDATE run_artifact SET storage_key=? WHERE artifact_id=?', ('../outside.txt', record['artifact_id']))
        self.assertEqual(self.client().get(url).status_code, 404)

    def test_object_download_is_proxied_and_releases_connection(self):
        record = self.register(backend='minio')
        response = Mock()
        response.stream.return_value = iter([b'result'])
        storage = SimpleNamespace(backend='minio', open_download=Mock(return_value=response))
        result = self.client(storage).get(f"/harness/artifacts/{record['artifact_id']}/download")
        self.assertEqual(result.content, b'result')
        storage.open_download.assert_called_once_with('run-A/result.txt')
        response.close.assert_called_once()
        response.release_conn.assert_called_once()
        self.assertEqual(self.client().get(f"/harness/artifacts/{record['artifact_id']}/download").status_code, 503)

    def test_object_download_errors_do_not_echo_provider_details(self):
        record = self.register(backend='minio')
        storage = SimpleNamespace(backend='minio', open_download=Mock(side_effect=RuntimeError('PLACEHOLDER_PROVIDER_DETAIL')))
        response = self.client(storage).get(f"/harness/artifacts/{record['artifact_id']}/download")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('PLACEHOLDER_PROVIDER_DETAIL', response.text)
        missing = RuntimeError('not found')
        missing.code = 'NoSuchKey'
        storage.open_download.side_effect = missing
        self.assertEqual(self.client(storage).get(f"/harness/artifacts/{record['artifact_id']}/download").status_code, 404)

    def test_worker_uses_run_id_for_repeated_conversation_and_publishes_download(self):
        worker = ExecutionWorker(self.queue, FakeEngine(), FakeTasks(), self.storage, artifacts=self.artifacts)
        ids = []
        for query in ('first presentation', 'second presentation'):
            run = self.queue.enqueue('same-conversation', 'ppt', query, None)
            ids.append(run['run_id'])
            self.assertTrue(worker.run_once())
            self.assertEqual(self.queue.get_status(run['run_id']), 'completed')
            items, total = self.artifacts.list(run['run_id'])
            self.assertEqual(total, 1)
            self.assertTrue(items[0]['storage_key'].startswith(run['run_id'] + '/'))
            events = [item['event'] for item in self.queue.get_events(run['run_id'])]
            self.assertEqual([event['type'] for event in events][-3:], ['artifact', 'text', 'complete'])
            metadata = events[-3]['artifact']
            self.assertEqual(metadata['run_id'], run['run_id'])
            download = self.client().get(metadata['download'])
            self.assertEqual(download.status_code, 200)
            self.assertEqual(hashlib.sha256(download.content).hexdigest(), metadata['sha256'])
            self.assertIn(metadata['download'], events[-2]['content'])
        first = self.artifacts.list(ids[0])[0][0]
        second = self.artifacts.list(ids[1])[0][0]
        self.assertNotEqual(first['artifact_id'], second['artifact_id'])
        self.assertNotEqual(first['storage_key'], second['storage_key'])

    def test_worker_indexes_object_storage_before_deleting_local_output(self):
        storage = SimpleNamespace(backend='minio', settings=SimpleNamespace(generated_dir=self.generated),
                                  upload_bytes=Mock(return_value='ignored-provider-address'))
        run = self.queue.enqueue('conversation', 'ppt', 'test', None)
        worker = ExecutionWorker(self.queue, FakeEngine(), FakeTasks(), storage, artifacts=self.artifacts)
        worker.run_once()
        record = self.artifacts.list(run['run_id'])[0][0]
        self.assertEqual(record['storage_backend'], 'minio')
        self.assertTrue(record['storage_key'].startswith(f"ppt/{run['run_id']}/"))
        self.assertEqual(storage.upload_bytes.call_args.args[1], record['storage_key'])
        self.assertEqual(list(self.generated.rglob('*.pptx')), [])
        self.assertNotIn('ignored-provider-address', repr(self.queue.get_events(run['run_id'])))

    def test_failed_runtime_does_not_generate_or_claim_an_artifact(self):
        runtime = Mock()
        runtime.stream.return_value = iter([{'type': 'error', 'content': 'failed'}])
        run = self.queue.enqueue('conversation', 'ppt', 'test', None)
        with patch('python_backend.workers.execution_worker.generate_ppt') as generate:
            ExecutionWorker(self.queue, runtime, FakeTasks(), self.storage, artifacts=self.artifacts).run_once()
        generate.assert_not_called()
        self.assertEqual(self.queue.get_status(run['run_id']), 'failed')
        self.assertEqual(self.artifacts.list(run['run_id'])[1], 0)

    def test_cancelled_runtime_does_not_generate_an_artifact(self):
        run = self.queue.enqueue('conversation', 'ppt', 'test', None)

        def stream(*args):
            self.queue.request_cancel_run(run['run_id'])
            yield {'type': 'complete', 'content': ''}

        with patch('python_backend.workers.execution_worker.generate_ppt') as generate:
            ExecutionWorker(self.queue, SimpleNamespace(stream=stream), FakeTasks(), self.storage,
                            artifacts=self.artifacts).run_once()
        generate.assert_not_called()
        self.assertEqual(self.queue.get_status(run['run_id']), 'cancelled')
        self.assertEqual(self.artifacts.list(run['run_id'])[1], 0)

    def test_cancel_during_generation_retains_actual_artifact_without_success(self):
        from python_backend.modules.documents.ppt import generate_ppt
        run = self.queue.enqueue('conversation', 'ppt', 'test', None)

        def generate_then_cancel(*args):
            output = generate_ppt(*args)
            self.queue.request_cancel_run(run['run_id'])
            return output

        with patch('python_backend.workers.execution_worker.generate_ppt', generate_then_cancel):
            ExecutionWorker(self.queue, FakeEngine(), FakeTasks(), self.storage, artifacts=self.artifacts).run_once()
        self.assertEqual(self.queue.get_status(run['run_id']), 'cancelled')
        self.assertEqual(self.artifacts.list(run['run_id'])[1], 1)
        types = [item['event']['type'] for item in self.queue.get_events(run['run_id'])]
        self.assertIn('artifact', types)
        self.assertEqual(types[-1], 'error')
        self.assertNotIn('complete', types)

    def test_registration_failure_does_not_publish_artifact_or_success(self):
        run = self.queue.enqueue('conversation', 'ppt', 'test', None)
        with patch.object(self.artifacts, 'register', side_effect=ValueError('PLACEHOLDER_PRIVATE_DETAIL')), patch('builtins.print'):
            ExecutionWorker(self.queue, FakeEngine(), FakeTasks(), self.storage, artifacts=self.artifacts).run_once()
        self.assertEqual(self.queue.get_status(run['run_id']), 'failed')
        self.assertEqual(self.artifacts.list(run['run_id'])[1], 0)
        events = self.queue.get_events(run['run_id'])
        types = [item['event']['type'] for item in events]
        self.assertEqual(types[-1], 'error')
        self.assertNotIn('artifact', types)
        self.assertNotIn('complete', types)
        self.assertNotIn('PLACEHOLDER_PRIVATE_DETAIL', repr(events))


    def test_expire_and_delete_registration(self):
        record = self.register()
        with self.artifacts._db() as db:
            db.execute("UPDATE run_artifact SET created_at='2000-01-01T00:00:00.000Z'")
        self.assertEqual(self.artifacts.expire(30), [record['artifact_id']])
        self.assertIsNone(self.artifacts.get(record['artifact_id']))
        self.assertFalse(self.artifacts.delete(record['artifact_id']))
        fresh = self.register('run-B', 'run-B/other.txt')
        self.assertTrue(self.artifacts.delete(fresh['artifact_id']))
        self.assertIsNone(self.artifacts.get(fresh['artifact_id']))

    def test_list_reports_age_days(self):
        self.register()
        items, total = self.artifacts.list()
        self.assertEqual(total, 1)
        self.assertEqual(items[0]['ageDays'], 0)
        payload = self.client().get('/harness/artifacts').json()['items'][0]
        self.assertEqual(payload['ageDays'], 0)

    def test_preview_returns_text_and_rejects_binary(self):
        record = self.register(content=b'hello preview')
        client = self.client()
        response = client.get(f"/harness/artifacts/{record['artifact_id']}/preview")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['content'], 'hello preview')
        self.assertEqual(body['artifactId'], record['artifact_id'])
        self.assertEqual(body['contentType'], 'text/plain')
        self.assertFalse(body['truncated'])
        self.assertEqual(client.get('/harness/artifacts/missing/preview').status_code, 404)

        binary = self.artifacts.register(run_id='run-A', name='deck.pdf', size=3,
                                         sha256=hashlib.sha256(b'pdf').hexdigest(),
                                         content_type='application/pdf', storage_backend='local',
                                         storage_key='run-A/deck.pdf')
        self.assertEqual(client.get(f"/harness/artifacts/{binary['artifact_id']}/preview").status_code, 415)

        with self.artifacts._db() as db:
            db.execute('UPDATE run_artifact SET storage_key=? WHERE artifact_id=?',
                       ('../outside.txt', record['artifact_id']))
        self.assertEqual(client.get(f"/harness/artifacts/{record['artifact_id']}/preview").status_code, 404)

    def test_preview_truncates_long_content(self):
        record = self.register(content=b'a' * 25000)
        body = self.client().get(f"/harness/artifacts/{record['artifact_id']}/preview").json()
        self.assertTrue(body['truncated'])
        self.assertEqual(len(body['content']), 20000)

    def test_preview_is_unsupported_for_object_storage(self):
        record = self.register(backend='minio')
        storage = SimpleNamespace(backend='minio', open_download=Mock())
        response = self.client(storage).get(f"/harness/artifacts/{record['artifact_id']}/preview")
        self.assertEqual(response.status_code, 503)

    def test_cleanup_expires_old_registrations_and_removes_files(self):
        record = self.register(content=b'old')
        with self.artifacts._db() as db:
            db.execute("UPDATE run_artifact SET created_at='2000-01-01T00:00:00.000Z'")
        client = self.client()
        response = client.post('/harness/artifacts/cleanup',
                                json={'retentionDays': 30, 'deleteFiles': True})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['removed'], 1)
        self.assertEqual(body['artifactIds'], [record['artifact_id']])
        self.assertFalse((self.generated / record['storage_key']).exists())
        self.assertIsNone(self.artifacts.get(record['artifact_id']))
        self.assertEqual(client.post('/harness/artifacts/cleanup', json={'retentionDays': 0}).status_code, 400)



    def test_owner_scopes_download_and_preview(self):
        record = self.register(content=b'owned')
        with self.artifacts._db() as db:
            db.execute('UPDATE run_artifact SET owner=? WHERE artifact_id=?', ('alice', record['artifact_id']))
        client = self.client()
        url = f"/harness/artifacts/{record['artifact_id']}/download"
        self.assertEqual(client.get(url).status_code, 403)
        self.assertIn('X-Harness-Owner', client.get(url).json()['detail'])
        self.assertEqual(client.get(url, headers={'X-Harness-Owner': 'bob'}).status_code, 403)
        self.assertNotIn('alice', client.get(url, headers={'X-Harness-Owner': 'bob'}).text)
        self.assertEqual(client.get(url, headers={'X-Harness-Owner': 'alice'}).status_code, 200)
        preview = f"/harness/artifacts/{record['artifact_id']}/preview"
        self.assertEqual(client.get(preview).status_code, 403)
        self.assertEqual(client.get(preview, headers={'X-Harness-Owner': 'alice'}).status_code, 200)

    def test_empty_owner_keeps_legacy_download_open(self):
        record = self.register(content=b'legacy')
        client = self.client()
        self.assertEqual(record['owner'], '')
        self.assertEqual(client.get(f"/harness/artifacts/{record['artifact_id']}/download").status_code, 200)

    def test_owner_header_name_follows_harness_settings(self):
        record = self.register(content=b'owned')
        with self.artifacts._db() as db:
            db.execute('UPDATE run_artifact SET owner=? WHERE artifact_id=?', ('alice', record['artifact_id']))
        app = FastAPI()
        app.include_router(create_artifact_router(
            self.artifacts, self.storage, settings_reader=lambda: {'artifactOwnerHeader': 'X-Team-Owner'}))
        client = TestClient(app)
        url = f"/harness/artifacts/{record['artifact_id']}/download"
        self.assertEqual(client.get(url, headers={'X-Harness-Owner': 'alice'}).status_code, 403)
        self.assertIn('X-Team-Owner', client.get(url).json()['detail'])
        self.assertEqual(client.get(url, headers={'X-Team-Owner': 'alice'}).status_code, 200)

    def test_list_filters_by_owner(self):
        first = self.register('run-A', 'run-A/one.txt')
        second = self.register('run-B', 'run-B/two.txt')
        with self.artifacts._db() as db:
            db.execute('UPDATE run_artifact SET owner=? WHERE artifact_id=?', ('alice', first['artifact_id']))
            db.execute('UPDATE run_artifact SET owner=? WHERE artifact_id=?', ('bob', second['artifact_id']))
        client = self.client()
        alice = client.get('/harness/artifacts', params={'owner': 'alice'}).json()
        self.assertEqual(alice['total'], 1)
        self.assertEqual(alice['items'][0]['artifact_id'], first['artifact_id'])
        self.assertEqual(alice['items'][0]['owner'], 'alice')
        self.assertEqual(client.get('/harness/artifacts', params={'owner': 'carol'}).json()['total'], 0)

    def test_owner_column_is_added_to_legacy_database(self):
        legacy = self.root / 'legacy.db'
        db = sqlite3.connect(legacy)
        db.executescript('''
            CREATE TABLE run_artifact (
                artifact_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, name TEXT NOT NULL,
                size INTEGER NOT NULL, sha256 TEXT NOT NULL, content_type TEXT NOT NULL,
                storage_backend TEXT NOT NULL, storage_key TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                UNIQUE(run_id, storage_backend, storage_key));
            INSERT INTO run_artifact VALUES ('old','run-old','old.txt',1,'a','text/plain','local','run-old/old.txt','2026-01-01T00:00:00.000Z');
        ''')
        db.commit()
        db.close()
        store = ArtifactStore(legacy)
        record = store.get('old')
        self.assertEqual(record['owner'], '')
        self.assertEqual(store.list()[1], 1)

    def test_generated_file_registration_uses_disk_digest(self):
        target = self.generated / 'deck.pptx'
        target.write_bytes(b'pptx-bytes')
        record, failure = register_generated_file(
            self.artifacts, target, run_id='run-A', content_type='text/plain',
            storage_backend='local', storage_key='deck.pptx')
        self.assertEqual(failure, '')
        self.assertEqual(record['sha256'], hashlib.sha256(b'pptx-bytes').hexdigest())
        self.assertEqual(record['size'], len(b'pptx-bytes'))
        self.assertEqual(record['name'], 'deck.pptx')

    def test_generated_file_registration_failure_is_reported_not_raised(self):
        missing = self.generated / 'missing.pptx'
        record, failure = register_generated_file(
            self.artifacts, missing, run_id='run-A', content_type='text/plain',
            storage_backend='local', storage_key='missing.pptx')
        self.assertIsNone(record)
        self.assertTrue(failure)

    def test_legacy_artifact_registration_uses_session_id_as_run_id(self):
        target = self.generated / 'legacy.pptx'
        target.write_bytes(b'legacy-deck')
        record, failure = register_legacy_artifact(
            self.artifacts, target, conversation_id='conversation-9',
            storage_backend='local', content_type='application/vnd.ms-powerpoint')
        self.assertEqual(failure, '')
        self.assertEqual(record['run_id'], 'conversation-9')
        self.assertEqual(record['storage_key'], 'legacy.pptx')
        self.assertEqual(record['owner'], '')
        self.assertEqual(record['sha256'], hashlib.sha256(b'legacy-deck').hexdigest())
        items, total = self.artifacts.list('conversation-9')
        self.assertEqual(total, 1)
        self.assertEqual(items[0]['artifact_id'], record['artifact_id'])

    def test_legacy_artifact_registration_keeps_object_storage_layout(self):
        target = self.generated / 'legacy.pptx'
        target.write_bytes(b'legacy-deck')
        record, failure = register_legacy_artifact(
            self.artifacts, target, conversation_id='conversation-9',
            storage_backend='minio', content_type='application/vnd.ms-powerpoint')
        self.assertEqual(failure, '')
        self.assertEqual(record['storage_key'], 'ppt/conversation-9/legacy.pptx')

    def test_legacy_run_id_uses_session_identifier_then_timestamp(self):
        self.assertEqual(legacy_run_id('conversation-7'), 'conversation-7')
        fallback = legacy_run_id('  ')
        self.assertTrue(fallback.startswith('legacy-'))
        self.assertNotEqual(fallback, legacy_run_id(''))

class ObservabilityExportTests(unittest.TestCase):
    """Cross-run export and trend endpoints run against their own temporary database."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.execution = self.root / 'execution.db'
        db = sqlite3.connect(self.execution)
        db.executescript('''
            CREATE TABLE execution_run (run_id TEXT PRIMARY KEY, status TEXT, created_at TEXT);
            CREATE TABLE execution_event (event_id INTEGER PRIMARY KEY, run_id TEXT,
                                          event_json TEXT, created_at TEXT);
        ''')
        db.executemany('INSERT INTO execution_run VALUES (?,?,?)', [
            ('run-a', 'completed', '2026-03-15T10:10:00Z'),
            ('run-b', 'failed', '2026-03-15T11:30:00Z'),
        ])
        db.executemany('INSERT INTO execution_event VALUES (?,?,?,?)', [
            (1, 'run-a', json.dumps({'type': 'text', 'content': 'hello'}), '2026-03-15T10:10:00Z'),
            (2, 'run-a', json.dumps({'type': 'tool_start', 'tool': 'search'}), '2026-03-15T10:11:00Z'),
            (3, 'run-b', json.dumps({'type': 'error', 'content': 'boom'}), '2026-03-15T11:30:00Z'),
        ])
        db.commit()
        db.close()

    def tearDown(self):
        self.temp.cleanup()

    def client(self):
        app = FastAPI()
        app.include_router(create_observability_router(
            lambda **kwargs: ([], 0), lambda run_id: None, lambda *args, **kwargs: [],
            self.execution))
        return TestClient(app)

    def test_export_returns_json_items_total_and_truncation(self):
        body = self.client().get('/harness/observability/exports').json()
        self.assertEqual(body['total'], 3)
        self.assertEqual(body['limit'], 1000)
        self.assertFalse(body['truncated'])
        self.assertEqual([item['event_id'] for item in body['items']], [1, 2, 3])
        self.assertEqual(body['items'][1]['tool'], 'search')
        self.assertEqual(body['items'][2]['level'], 'error')

    def test_export_filters_by_run_time_and_limit(self):
        client = self.client()
        by_run = client.get('/harness/observability/exports', params={'runId': 'run-a'}).json()
        self.assertEqual([item['event_id'] for item in by_run['items']], [1, 2])
        by_time = client.get('/harness/observability/exports',
                             params={'from': '2026-03-15T11:00:00Z'}).json()
        self.assertEqual([item['event_id'] for item in by_time['items']], [3])
        limited = client.get('/harness/observability/exports', params={'limit': 1}).json()
        self.assertEqual(len(limited['items']), 1)
        self.assertTrue(limited['truncated'])
        self.assertEqual(limited['total'], 3)
        self.assertEqual(client.get('/harness/observability/exports',
                                     params={'from': 'not-a-time'}).status_code, 400)

    def test_export_csv_has_the_expected_columns(self):
        response = self.client().get('/harness/observability/exports', params={'format': 'csv'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response.headers['content-type'])
        rows = list(csv.DictReader(io.StringIO(response.text)))
        self.assertEqual(list(rows[0]), ['run_id', 'event_id', 'created_at', 'type', 'level',
                                          'tool', 'status', 'summary'])
        self.assertEqual(rows[0]['run_id'], 'run-a')
        self.assertEqual(rows[2]['summary'], 'boom')

    def test_trends_bucket_runs_and_events_without_inventing_points(self):
        points = self.client().get('/harness/observability/trends').json()
        self.assertEqual(points['bucket'], 'hour')
        self.assertEqual(len(points['points']), 2)
        first, second = points['points']
        self.assertEqual(first['bucketStart'], '2026-03-15T10:00:00Z')
        self.assertEqual(first['runs'], 1)
        self.assertEqual(first['completed'], 1)
        self.assertEqual(first['toolCalls'], 1)
        self.assertEqual(second['bucketStart'], '2026-03-15T11:00:00Z')
        self.assertEqual(second['failed'], 1)
        self.assertEqual(second['errors'], 1)

    def test_trends_day_bucket_and_empty_database(self):
        day = self.client().get('/harness/observability/trends', params={'bucket': 'day'}).json()
        self.assertEqual(len(day['points']), 1)
        self.assertEqual(day['points'][0]['bucketStart'], '2026-03-15T00:00:00Z')
        self.assertEqual(day['points'][0]['runs'], 2)
        self.assertEqual(self.client().get('/harness/observability/trends',
                                           params={'bucket': 'week'}).status_code, 400)
        missing = self.root / 'missing.db'
        app = FastAPI()
        app.include_router(create_observability_router(
            lambda **kwargs: ([], 0), lambda run_id: None, lambda *args, **kwargs: [], missing))
        body = TestClient(app).get('/harness/observability/trends').json()
        self.assertEqual(body['points'], [])


if __name__ == '__main__':
    unittest.main()
