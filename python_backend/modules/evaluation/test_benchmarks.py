"""No database server or model credentials are required for these checks."""
import importlib.util
import json
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from .benchmarks import BenchmarkService, ROOT
from ...api.routers.benchmarks import create_benchmark_router


def load_script(name):
    sys.path.insert(0, str(ROOT / 'eval'))
    spec = importlib.util.spec_from_file_location(name, ROOT / 'eval' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.service = BenchmarkService(self.root / 'data', self.root)
        self.tools = patch.object(self.service, 'tools', return_value={})
        self.tools.start()
        (self.root / 'eval').mkdir()
        (self.service.inputs / 'samples.jsonl').write_text('{}', 'utf-8')
        app = FastAPI()
        app.include_router(create_benchmark_router(self.service))
        self.client = TestClient(app)

    def tearDown(self):
        self.service.close()
        deadline = time.monotonic() + 5
        while self.service.processes and time.monotonic() < deadline:
            time.sleep(.05)
        self.tools.stop()
        self.temp.cleanup()

    def wait(self, job_id, heartbeat=True):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            job = self.service.touch(job_id) if heartbeat else self.service.get(job_id)
            if job['status'] not in {'queued', 'running'}:
                return job
            time.sleep(.05)
        self.fail('job did not finish')

    def script(self, body):
        (self.root / 'eval/run_benchmark.py').write_text(body, 'utf-8')

    def test_startup_and_read_only_pages_do_not_launch_tools(self):
        with patch('subprocess.Popen') as launch:
            self.assertEqual(self.client.get('/evaluation/benchmarks/runs?kind=rag').json(), {'items': []})
            self.client.get('/evaluation/benchmarks/tools')
            launch.assert_not_called()

    def test_request_validation_and_path_escape(self):
        for payload in ({'kind': 'load', 'users': 101}, {'kind': 'load', 'duration': 0},
                        {'kind': 'load', 'target': 'https://example.com'}, {'kind': 'unknown'}):
            self.assertEqual(self.client.post('/evaluation/benchmarks/runs', json=payload).status_code, 422)
        for path in ('../outside', '../../.env', 'private/file', 'missing.jsonl'):
            response = self.client.post('/evaluation/benchmarks/runs', json={'kind': 'rag', 'input': path})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get('/evaluation/benchmarks/runs/not-an-id').status_code, 404)

    def test_explicit_start_and_persisted_result(self):
        self.script("import sys,json,pathlib\np=pathlib.Path(sys.argv[1]).parent\n(p/'result.json').write_text(json.dumps({'summary':{'sampleCount':3}}))\n")
        response = self.client.post('/evaluation/benchmarks/runs', json={'kind': 'rag', 'input': 'samples.jsonl'})
        self.assertEqual(response.status_code, 200)
        job = self.wait(response.json()['id'])
        self.assertEqual(job['status'], 'completed')
        self.assertEqual(job['summary']['sampleCount'], 3)
        self.assertEqual(self.service.list('bird'), [])

    def test_cancel_and_single_job_limit(self):
        self.script('import time\ntime.sleep(60)\n')
        job = self.service.start({'kind': 'rag', 'input': 'samples.jsonl'})
        with self.assertRaises(ValueError):
            self.service.start({'kind': 'rag', 'input': 'samples.jsonl'})
        response = self.client.post(f"/evaluation/benchmarks/runs/{job['id']}/cancel")
        self.assertEqual(response.json()['status'], 'cancelled')

    def test_lost_page_lease_cancels_job(self):
        self.script('import time\ntime.sleep(60)\n')
        job = self.service.start({'kind': 'rag', 'input': 'samples.jsonl'})
        self.service.leases[job['id']] = time.monotonic() - 1
        self.assertEqual(self.wait(job['id'], heartbeat=False)['status'], 'cancelled')

    def test_restart_marks_jobs_interrupted(self):
        job = {'id': 'a' * 32, 'status': 'running', 'kind': 'rag', 'createdAt': 'now'}
        self.service._save(job)
        recovered = BenchmarkService(self.service.data_dir, self.root)
        self.assertEqual(recovered.get(job['id'])['status'], 'interrupted')

    def test_generator_return_is_used_for_retrieval(self):
        collect = load_script('collect')
        class Engine:
            def _choose_retrieval(self, question):
                yield {'type': 'step'}
                return 'keyword'
            def _retrieve(self, source, question, route):
                self.route = route
                yield {'type': 'step'}
                return ['evidence']
        engine = Engine()
        self.assertEqual(collect.retrieve(engine, 'question', 'file'), ('keyword', ['evidence']))
        self.assertEqual(engine.route, 'keyword')

    def test_retrieval_metrics_and_sse_parsing(self):
        runner = load_script('run_benchmark')
        result = runner.retrieval_metrics([{'relevant_ids': ['a', 'b'], 'retrieved_ids': ['x', 'a', 'a']}])
        self.assertEqual(result['recallAt5'], .5)
        self.assertEqual(result['mrrAt5'], .5)
        sse = load_script('sse_metrics')
        parsed = list(sse.events([': heartbeat', '', 'data: {"type":"error"}', '', 'data: [DONE]', '']))
        self.assertEqual([r['type'] for r in parsed], ['error', 'done'])
        with self.assertRaises(ValueError):
            list(sse.events(['data: {"type":"text"}']))

    def test_nonfinite_ragas_score_is_reported_unscored(self):
        import asyncio
        score = load_script('score')
        async def invalid_metric(sample):
            return float('nan')
        rows = asyncio.run(score.score_all([{'id': 'fixture', 'question': 'number?', 'answer': '42', 'contexts': ['42']}],
                                           {'faithfulness': invalid_metric}, 1))
        self.assertEqual(rows[0]['scores'], {})
        self.assertTrue(rows[0]['skipped'])

    def test_bird_sqlite_guard_prevents_writes(self):
        db_path = self.root / 'fixture.sqlite'
        with closing(sqlite3.connect(db_path)) as db:
            db.execute('CREATE TABLE sample (n INTEGER)')
        import os
        env = dict(os.environ, PYTHONPATH=str(ROOT / 'eval/bird_guard'))
        code = "import sqlite3,sys\nc=sqlite3.connect(sys.argv[1])\nprint(c.execute('SELECT count(*) FROM sample').fetchone()[0])\nc.execute('DROP TABLE sample')"
        result = subprocess.run([sys.executable, '-c', code, str(db_path)], env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('not authorized', result.stderr)
        with closing(sqlite3.connect(db_path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM sample').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
