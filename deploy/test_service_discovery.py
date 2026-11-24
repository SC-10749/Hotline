"""Opt-in real Nacos integration test. Uses isolated local data and ephemeral ports.

Build java_backend first; set HOTLINE_TEST_NACOS_SERVER_ADDR to a test registry.
No model provider is contacted: the task must reach a terminal state even without credentials.
"""
import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def request(url, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    try:
        with urlopen(Request(url, body, {'Content-Type': 'application/json'}), timeout=10) as response:
            return json.load(response)
    except HTTPError as error:
        raise AssertionError(f'Integration HTTP {error.code}: {error.read().decode()}') from None


async def wait_ready(url, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return await asyncio.to_thread(request, url)
        except Exception:
            await asyncio.sleep(0.5)
    raise AssertionError('Integration service readiness timed out; inspect local integration logs')


async def main():
    import uvicorn
    python_port, java_port = free_port(), free_port()
    service = 'hotline-test-' + uuid4().hex
    directory = ROOT / 'data' / 'integration' / service
    directory.mkdir(parents=True)
    registry = os.environ.get('HOTLINE_TEST_NACOS_SERVER_ADDR', '127.0.0.1:18848')
    os.environ.update({
        'DODO_ENV_FILE': str(directory / 'absent.env'), 'DODO_DATA_DIR': str(directory),
        'DODO_UPLOAD_DIR': str(directory / 'uploads'), 'DODO_GENERATED_DIR': str(directory / 'generated'),
        'SKILLS_DIRECTORY': str(directory / 'skills'), 'DODO_SKILL_CATALOG_DB': str(directory / 'catalog.db'),
        'DODO_STORAGE_BACKEND': 'sqlite', 'DODO_FILE_STORAGE_BACKEND': 'local',
        'DODO_VECTOR_ENABLED': 'false', 'DODO_REDIS_ENABLED': 'false',
        'HOTLINE_CONTEXT_ENABLED': 'false', 'HOTLINE_PYTHON_NACOS_ENABLED': 'true',
        'HOTLINE_NACOS_SERVER_ADDR': registry, 'HOTLINE_PYTHON_ADVERTISED_IP': '127.0.0.1',
        'HOTLINE_PYTHON_ADVERTISED_PORT': str(python_port), 'HOTLINE_PYTHON_SERVICE_NAME': service,
        'HOTLINE_JAVA_PORT': str(java_port), 'HOTLINE_NACOS_ENABLED': 'true',
        'HOTLINE_NACOS_REGISTER_ENABLED': 'false', 'HOTLINE_PYTHON_MODE': 'nacos',
        'PYTHONUTF8': '1',
    })
    for name in ('DEEPSEEK_API_KEY', 'DODO_API_KEY', 'DASHSCOPE_API_KEY', 'OPENAI_API_KEY', 'DODO_DECISION_API_KEY', 'DODO_EMBEDDING_API_KEY'):
        os.environ[name] = ''
    from main import app
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=python_port, log_level='error'))
    api = asyncio.create_task(server.serve())
    logs = [open(directory / name, 'w', encoding='utf-8') for name in ('worker.log', 'java.log')]
    worker = subprocess.Popen([sys.executable, '-m', 'python_backend.modules.execution.worker'], cwd=ROOT,
                              stdout=logs[0], stderr=subprocess.STDOUT)
    jar = ROOT / 'java_backend/target/hotline-java-api-1.0.0-SNAPSHOT.jar'
    # Windows javapath can be a launcher process; use the actual VM so cleanup owns it.
    properties = subprocess.run(['java', '-XshowSettings:properties', '-version'], capture_output=True, text=True)
    java_home = re.search(r'java.home = (.+)', properties.stderr).group(1).strip()
    java_binary = Path(java_home) / 'bin' / ('java.exe' if os.name == 'nt' else 'java')
    java = subprocess.Popen([str(java_binary), '-jar', str(jar)], cwd=ROOT / 'java_backend',
                            stdout=logs[1], stderr=subprocess.STDOUT)
    base = f'http://127.0.0.1:{java_port}'
    try:
        await wait_ready(base + '/health/ready')
        print('PASS: FastAPI registered; Java discovered Python; API and Worker ready', flush=True)
        for path in ('/skill/list', '/session/list', '/harness/workspaces', '/evaluation/datasets'):
            await asyncio.to_thread(request, base + path)
        result = await asyncio.to_thread(request, base + '/execution/runs', {
            'conversationId': service, 'agent': 'chat', 'query': 'integration test'})
        run_id = result['run']['run_id']
        def events():
            with urlopen(base + '/execution/runs/' + run_id + '/stream', timeout=20) as response:
                return response.read().decode()
        stream = await asyncio.to_thread(events)
        assert 'event: done' in stream and 'id:' in stream, 'Unexpected isolated SSE response: ' + repr(stream[:1000])
        result = await asyncio.to_thread(request, base + '/execution/runs/' + run_id)
        assert result['run']['status'] in ('completed', 'failed', 'cancelled')
        print('PASS: capability queries, task submission/status and SSE via Java', flush=True)
    finally:
        server.should_exit = True
        await asyncio.wait_for(api, 30)
        for process in (java, worker):
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                process.terminate()
            await asyncio.to_thread(process.wait, 15)
        for log in logs:
            log.close()
    query = urlencode({'serviceName': service, 'groupName': os.getenv('HOTLINE_NACOS_GROUP', 'DEFAULT_GROUP'),
                       'namespaceId': os.getenv('HOTLINE_NACOS_NAMESPACE', ''), 'healthyOnly': 'false'})
    # This assertion targets a dedicated test registry with auth disabled.
    for _ in range(20):
        instances = await asyncio.to_thread(request, 'http://' + registry + '/nacos/v1/ns/instance/list?' + query)
        if not instances.get('hosts'):
            break
        # Nacos's HTTP instance list is eventually consistent with gRPC deregistration.
        await asyncio.sleep(0.5)
    assert not instances.get('hosts'), 'FastAPI must deregister on graceful shutdown'
    print('PASS: FastAPI shutdown removed the Nacos instance', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
