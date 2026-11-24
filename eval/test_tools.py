"""Local integration checks with synthetic data and a fake model. No real API calls.

Run with .venv/Scripts/python.exe eval/test_tools.py after installing requirements-tools.
"""
import json
import os
import subprocess
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / 'eval/.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
OUTPUT = ROOT / 'data/evaluations/verification'


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        request = json.loads(self.rfile.read(length))
        answer = {'statements': ['The number is 42.'], 'verdicts': [
            {'statement': 'The number is 42.', 'reason': 'Synthetic fixture evidence', 'verdict': 1}],
            'reason': 'Synthetic fixture evidence', 'verdict': 1}
        if 'NLIStatementOutput' in json.dumps(request):
            answer['statements'] = answer['verdicts']
        payload = {'id': 'fixture', 'object': 'chat.completion', 'created': 0, 'model': 'fixture',
                   'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': json.dumps(answer)},
                                'finish_reason': 'stop'}],
                   'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}}
        content = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        if self.path.startswith('/agent/chat/stream'):
            success = self.server.success
            events = [{'type': 'step', 'content': 'fixture'}, {'type': 'text', 'content': '42'},
                      {'type': 'complete' if success else 'error', 'content': ''}]
            content = (''.join('data: ' + json.dumps(e) + '\n\n' for e in events) + 'data: [DONE]\n\n').encode()
            mime = 'text/event-stream'
        else:
            content, mime = b'{"status":"ok"}', 'application/json'
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)


class ToolIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        OUTPUT.mkdir(parents=True, exist_ok=True)
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)
        cls.server.success = True
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.host = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def run_tool(self, args, env, log):
        with log.open('w', encoding='utf-8') as stream:
            result = subprocess.run([str(PYTHON), *map(str, args)], cwd=ROOT, env=env,
                                    stdout=stream, stderr=subprocess.STDOUT, timeout=120)
        self.assertEqual(result.returncode, 0, f'Inspect local fixture log: {log.name}')

    def test_ragas_real_library_with_local_fake_judge(self):
        folder = OUTPUT / 'ragas-fixture'
        folder.mkdir(exist_ok=True)
        samples = folder / 'samples.jsonl'
        samples.write_text(json.dumps({'id': 'fixture', 'question': 'What is the number?',
            'answer': 'The number is 42.', 'contexts': ['The number is 42.']}) + '\n', 'utf-8')
        env = {k: v for k, v in os.environ.items() if not k.startswith(('DODO_', 'EVAL_', 'OPENAI_', 'DASHSCOPE_', 'DEEPSEEK_'))}
        env.update(EVAL_JUDGE_MODEL='fixture', EVAL_JUDGE_API_KEY='fixture-key',
                   EVAL_JUDGE_BASE_URL=self.host + '/v1', DODO_ENV_FILE=str(folder / 'absent.env'),
                   PYTHONUTF8='1', RAGAS_DO_NOT_TRACK='true')
        self.run_tool([ROOT / 'eval/score.py', '--samples', samples, '--out', folder], env, folder / 'tool.log')
        payload = json.loads((folder / 'scores.json').read_text('utf-8'))
        summary = payload['variants']['current']['summary']
        self.assertEqual(summary['faithfulness']['mean'], 1.0)
        self.assertEqual(summary['context_precision']['mean'], 1.0)

    def test_locust_http_and_sse_success_and_failure(self):
        for profile, success in [('http', True), ('sse', True), ('sse', False)]:
            self.server.success = success
            folder = OUTPUT / f'locust-{profile}-{success}'
            folder.mkdir(exist_ok=True)
            env = dict(os.environ, HOTLINE_LOAD_PROFILE=profile, HOTLINE_LOAD_OUTPUT=str(folder), PYTHONUTF8='1')
            self.run_tool(['-m', 'locust', '-f', ROOT / 'eval/locustfile.py', '--headless',
                '--host', self.host, '--users', '1', '--spawn-rate', '1', '--run-time', '5s',
                '--stop-timeout', '3', '--csv', folder / 'locust', '--only-summary', '--exit-code-on-error', '0'],
                env, folder / 'tool.log')
            row = json.loads((folder / 'load-summary.json').read_text('utf-8'))
            self.assertGreater(row['requestCount'], 0)
            self.assertEqual(row['failureCount'] == 0, success)
            if profile == 'sse':
                metrics = json.loads((folder / 'stream-summary.json').read_text('utf-8'))
                self.assertGreater(metrics['completed' if success else 'failed'], 0)
                self.assertEqual(metrics['completed'] == 0, not success)

    def test_bird_official_scorer_with_synthetic_database(self):
        import sqlite3
        from contextlib import closing
        folder = OUTPUT / 'bird-fixture'
        folder.mkdir(exist_ok=True)
        inputs = ROOT / 'data/benchmarks/verification-bird'
        (inputs / 'databases/toy').mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(inputs / 'databases/toy/toy.sqlite')) as db:
            db.execute('CREATE TABLE IF NOT EXISTS numbers (n INTEGER)')
            db.execute('DELETE FROM numbers')
            db.execute('INSERT INTO numbers VALUES (42)')
            db.commit()
        cases = [{'question_id': i, 'db_id': 'toy', 'question': 'What is the number?',
                  'SQL': 'SELECT n FROM numbers', 'difficulty': difficulty}
                 for i, difficulty in enumerate(('simple', 'moderate', 'challenging'))]
        (inputs / 'questions.json').write_text(json.dumps(cases), 'utf-8')
        (inputs / 'predictions.json').write_text(json.dumps({'0': 'SELECT n FROM numbers',
            '1': 'SELECT 0', '2': 'SELECT n FROM numbers'}), 'utf-8')
        job = {'kind': 'bird', 'spec': {'input': 'verification-bird/questions.json', 'limit': 3,
            'databases': 'verification-bird/databases', 'predictions': 'verification-bird/predictions.json',
            'evidence': False}}
        (folder / 'job.json').write_text(json.dumps(job), 'utf-8')
        self.run_tool([ROOT / 'eval/run_benchmark.py', folder / 'job.json'],
                      dict(os.environ, PYTHONUTF8='1', HOTLINE_BENCHMARK_DATA=str(ROOT / 'data')), folder / 'tool.log')
        result = json.loads((folder / 'result.json').read_text('utf-8'))
        self.assertAlmostEqual(result['summary']['executionAccuracy'], 2/3, places=3)
        self.assertIsNone(result['summary']['evidence'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
