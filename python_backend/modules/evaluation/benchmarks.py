"""Local benchmark jobs. Only fixed project scripts may be executed."""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]


def terminate_tree(process):
    if process.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=10)


class BenchmarkService:
    def __init__(self, data_dir: Path, root: Path = ROOT, recover=True):
        self.root = Path(root).resolve()
        self.data_dir = Path(data_dir).resolve()
        self.jobs = self.data_dir / 'evaluations/benchmarks'
        self.inputs = self.data_dir / 'benchmarks'
        self.jobs.mkdir(parents=True, exist_ok=True)
        self.inputs.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.processes = {}
        self.leases = {}
        self.closed = False
        for manifest in self.jobs.glob('*/job.json') if recover else ():
            job = json.loads(manifest.read_text('utf-8'))
            if job['status'] in {'queued', 'running'}:
                job.update(status='interrupted', error='服务重启，运行已中断；请重新启动')
                self._save(job)

    @property
    def python(self):
        return self.root / 'eval/.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')

    def input_path(self, relative: str, directory=False):
        path = (self.inputs / relative).resolve()
        if not relative or not path.is_relative_to(self.inputs) or any(
                re.search(r'(^|\.)env($|\.)|\.(private|local)\.', part, re.I)
                or part.lower() in {'secrets', 'private', '.git'} for part in path.parts):
            raise ValueError('输入必须位于 data/benchmarks 内，且不能是私密配置')
        if not (path.is_dir() if directory else path.is_file()):
            raise ValueError('输入文件或目录不存在，请先放入 data/benchmarks')
        return path

    def tools(self):
        installed = {}
        if self.python.is_file():
            try:
                result = subprocess.run([str(self.python), '-c',
                    'import importlib.metadata,json; print(json.dumps({k:importlib.metadata.version(k) for k in ("ragas","locust","func-timeout")}))'],
                    capture_output=True, text=True, timeout=15)
                if result.returncode == 0:
                    installed = json.loads(result.stdout)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                pass
        bird = self.inputs / 'bird-tool/version.json'
        revision = json.loads(bird.read_text('utf-8')).get('revision', '') if bird.is_file() else ''
        return {'pythonReady': self.python.is_file(), 'versions': installed,
                'birdRevision': revision, 'inputDirectory': 'data/benchmarks',
                'items': [{'kind': k, 'ready': bool(installed.get(package)) and (bool(revision) if k == 'bird' else True)}
                          for k, package in [('rag', 'ragas'), ('bird', 'func-timeout'), ('load', 'locust')]]}

    def _save(self, job):
        folder = self.jobs / job['id']
        folder.mkdir(exist_ok=True)
        temp = folder / 'job.tmp'
        temp.write_text(json.dumps(job, ensure_ascii=False, indent=2), 'utf-8')
        temp.replace(folder / 'job.json')

    def get(self, job_id):
        if not re.fullmatch(r'[a-f0-9]{32}', job_id):
            raise ValueError('运行不存在')
        with self.lock:
            path = self.jobs / job_id / 'job.json'
            if not path.is_file():
                raise ValueError('运行不存在')
            return json.loads(path.read_text('utf-8'))

    def list(self, kind=None):
        with self.lock:
            jobs = [json.loads(p.read_text('utf-8')) for p in self.jobs.glob('*/job.json')]
        return sorted((j for j in jobs if not kind or j['kind'] == kind),
                      key=lambda j: j['createdAt'], reverse=True)[:100]

    def start(self, spec):
        with self.lock:
            if self.closed:
                raise ValueError('服务正在关闭')
            if any(j['status'] in {'queued', 'running'} for j in self.list()):
                raise ValueError('已有基准任务运行中，请等待或取消后重试')
            kind = spec['kind']
            if kind != 'load':
                self.input_path(spec['input'])
            if kind == 'bird':
                self.input_path(spec['databases'], directory=True)
                if spec.get('predictions'):
                    self.input_path(spec['predictions'])
            job = {'id': uuid4().hex, 'kind': kind, 'status': 'queued',
                   'createdAt': datetime.now(timezone.utc).isoformat(), 'spec': spec,
                   'summary': {}, 'error': '', 'versions': self.tools()}
            self._save(job)
            self.leases[job['id']] = time.monotonic() + 30
            threading.Thread(target=self._run, args=(job['id'],), daemon=True).start()
            return job

    def _run(self, job_id):
        process = None
        try:
            with self.lock:
                job = self.get(job_id)
                if job['status'] != 'queued':
                    return
                folder = self.jobs / job_id
                job.update(status='running')
                self._save(job)
                env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8',
                           HOTLINE_BENCHMARK_DATA=str(self.data_dir))
                with (folder / 'run.log').open('w', encoding='utf-8') as log:
                    process = subprocess.Popen([sys.executable, str(self.root / 'eval/run_benchmark.py'),
                        str(folder / 'job.json')], cwd=self.root, env=env, stdout=log,
                        stderr=subprocess.STDOUT, start_new_session=os.name != 'nt',
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                self.processes[job_id] = process
            deadline = time.monotonic() + 3600
            while process.poll() is None:
                if time.monotonic() > self.leases.get(job_id, 0):
                    self.cancel(job_id)
                    break
                if time.monotonic() > deadline:
                    terminate_tree(process)
                    break
                time.sleep(.5)
            code = process.poll()
            with self.lock:
                job = self.get(job_id)
                if job['status'] == 'cancelled':
                    return
                result = folder / 'result.json'
                if result.is_file():
                    payload = json.loads(result.read_text('utf-8'))
                    from ..context_engineering.privacy import sanitize_value
                    job['summary'] = sanitize_value(payload.get('summary', {}))
                    job['error'] = sanitize_value(payload.get('error', ''))
                job['status'] = 'completed' if code == 0 and result.is_file() else 'failed'
                if job['status'] == 'failed' and not job['error']:
                    job['error'] = '工具运行失败或超时，请检查隔离环境与本地配置'
                job['finishedAt'] = datetime.now(timezone.utc).isoformat()
                self._save(job)
        except Exception:
            with self.lock:
                job = self.get(job_id)
                if job['status'] != 'cancelled':
                    job.update(status='failed', error='基准进程无法启动，请检查本地环境')
                    self._save(job)
        finally:
            if process is not None and job.get('kind') == 'load' and job['spec'].get('profile') == 'sse':
                self._cleanup_load(job)
            with self.lock:
                self.processes.pop(job_id, None)
                self.leases.pop(job_id, None)

    def touch(self, job_id):
        with self.lock:
            job = self.get(job_id)
            if job['status'] in {'queued', 'running'}:
                self.leases[job_id] = time.monotonic() + 30
            return job

    def _cleanup_load(self, job):
        import urllib.parse
        import urllib.request
        target = 'http://127.0.0.1:' + ('8888' if job['spec']['target'] == 'python' else '8080')
        for path in (self.jobs / job['id']).glob('active-*.json'):
            try:
                params = urllib.parse.urlencode(json.loads(path.read_text('utf-8')))
                with urllib.request.urlopen(target + '/agent/stop?' + params, timeout=2):
                    pass
                path.unlink(missing_ok=True)
            except Exception:
                pass

    def cancel(self, job_id):
        with self.lock:
            job = self.get(job_id)
            if job['status'] in {'queued', 'running'}:
                process = self.processes.get(job_id)
                if process:
                    terminate_tree(process)
                job.update(status='cancelled', finishedAt=datetime.now(timezone.utc).isoformat())
                self._save(job)
            return job

    def close(self):
        with self.lock:
            self.closed = True
            for job in self.list():
                if job['status'] in {'queued', 'running'}:
                    self.cancel(job['id'])
