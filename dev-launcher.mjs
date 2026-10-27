import { spawn, spawnSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const backendPort = process.env.DODO_DEV_BACKEND_PORT || '8888';
const frontendPort = process.env.DODO_DEV_FRONTEND_PORT || '5180';
const children = [];
let closing = false;
let backendChild = null;
let backendReused = false;
let workerChild = null;
let frontendChild = null;
const pythonCommand = process.platform === 'win32' ? 'python' : 'python3';
// Backend deps live in the uv-managed .venv (uv.lock); system python may lack
// fastapi and the rest, so prefer `uv run python` and fall back to plain python.
const hasUv = spawnSync('uv', ['--version'], { windowsHide: true }).status === 0;
const backendCommand = hasUv ? 'uv' : pythonCommand;
const backendPrefix = hasUv ? ['run', 'python'] : [];
const shutdown = async (code = 0) => {
  if (closing) return;
  closing = true;
  await Promise.all(children.map(child => {
    if (!child.pid || child.exitCode !== null) return;
    if (process.platform !== 'win32') {
      child.kill('SIGTERM');
      return;
    }
    return new Promise(resolve => {
      const killer = spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' });
      killer.on('error', resolve);
      killer.on('close', resolve);
    });
  }));
  process.exitCode = code;
};
const start = (command, args, cwd) => {
  const child = spawn(command, args, {
    cwd,
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: {
      ...process.env,
      PYTHONUTF8: '1',
      PYTHONIOENCODING: 'utf-8',
      NO_COLOR: '1',
      FORCE_COLOR: '0',
      DODO_DEV_FRONTEND_URL: `http://127.0.0.1:${frontendPort}/`,
    },
  });
  let bindWarned = false;
  const warnIfPortBusy = (stream, data) => {
    stream.write(data);
    if (!bindWarned && /error while attempting to bind|WinError 100(48|13)/i.test(String(data))) {
      bindWarned = true;
      console.error(`\n✗ 端口 ${backendPort} 已被占用，常见原因是上次开发模式残留的旧服务。`);
      console.error(`  查询占用：netstat -ano | findstr :${backendPort}`);
      console.error(`  结束进程：taskkill /PID <PID> /F\n`);
    }
  };
  child.stdout.on('data', data => warnIfPortBusy(process.stdout, data));
  child.stderr.on('data', data => warnIfPortBusy(process.stderr, data));
  child.on('error', error => {
    console.error(`Failed to start ${command}: ${error.message}`);
    shutdown(1);
  });
  child.on('exit', (code, signal) => {
    if (!closing) shutdown(code ?? 1);
  });
  children.push(child);
  return child;
};

const listeningPid = (port) => {
  if (process.platform !== 'win32') return null;
  const result = spawnSync('netstat', ['-ano', '-p', 'tcp'], { encoding: 'utf8', windowsHide: true });
  const pattern = new RegExp(`(?:127\\.0\\.0\\.1|0\\.0\\.0\\.0|\\[::\\]):${port}\\s+\\S+\\s+LISTENING\\s+(\\d+)`, 'i');
  return String(result.stdout || '').split(/\r?\n/).map(line => line.match(pattern)?.[1]).find(Boolean) || null;
};

const releaseFrontendPort = () => {
  const pid = listeningPid(frontendPort);
  if (!pid || Number(pid) === process.pid) return;
  console.log(`• 清理前端端口 ${frontendPort} 的旧进程（PID ${pid}）`);
  spawnSync('taskkill', ['/PID', pid, '/T', '/F'], { windowsHide: true, stdio: 'ignore' });
};

const root = dirname(fileURLToPath(import.meta.url));
console.log('Hotline Agent: starting Vue frontend, FastAPI gateway and Python Execution Worker.');
console.log(`Backend API: http://127.0.0.1:${backendPort}/docs`);
// Start one ordinary backend process and one ordinary Vite server.
// Development hot reload is intentionally disabled to avoid stale duplicate
// processes competing for the fixed local ports.
// Reuse a healthy Dodo backend already listening on the fixed local port.
// This prevents a second uvicorn process from racing with the previous run.
try {
  const response = await fetch(`http://127.0.0.1:${backendPort}/health`, { signal: AbortSignal.timeout(800) });
  const payload = await response.json().catch(() => null);
  backendReused = response.ok && payload?.service === 'hotline-agent';
} catch { /* No existing backend; start one below. */ }

if (backendReused) {
  console.log(`✓ 复用已运行的后端  http://127.0.0.1:${backendPort}/docs`);
} else {
  backendChild = start(backendCommand, [
    ...backendPrefix, '-m', 'uvicorn', 'main:app',
    '--host', '127.0.0.1', '--port', backendPort, '--no-use-colors',
  ], root);
}
workerChild = start(backendCommand, [...backendPrefix, '-m', 'python_backend.modules.execution.worker'], root);
releaseFrontendPort();
frontendChild = start(process.execPath, [join(root, 'frontend', 'node_modules', 'vite', 'bin', 'vite.js'), 'preview', '--host', '127.0.0.1', '--port', frontendPort, '--strictPort'], join(root, 'frontend'));

// Probe both services instead of parsing child logs, so the readiness hints
// stay correct even if uvicorn/vite change their banner wording.
const waitUntilReady = async (name, url, mark) => {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline && !closing) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(1500) });
      await response.body?.cancel();
      if (response.ok) {
        mark();
        return;
      }
    } catch { /* service not up yet; retry */ }
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  if (!closing) console.error(`✗ ${name}启动超时（${url}），请检查上方日志。`);
};

let frontendReady = false;
let backendReady = false;
const reportAllReady = () => {
  if (frontendReady && backendReady) {
    console.log(`\n全部就绪：打开 http://127.0.0.1:${frontendPort}/ 开始使用（Ctrl+C 退出）\n`);
  }
};
void waitUntilReady('前端', `http://127.0.0.1:${frontendPort}/`, () => {
  frontendReady = true;
  console.log(`✓ 前端启动完成  http://127.0.0.1:${frontendPort}/`);
  reportAllReady();
});
void waitUntilReady('后端与执行 Worker', `http://127.0.0.1:${backendPort}/health/ready`, () => {
  // A reused service is already verified above. For a newly started service,
  // only report readiness while its own child process is still alive.
  if ((!backendReused && (!backendChild || backendChild.exitCode !== null))
      || !workerChild || workerChild.exitCode !== null) return;
  backendReady = true;
  console.log(`✓ 后端启动完成  http://127.0.0.1:${backendPort}/docs`);
  reportAllReady();
});

process.on('SIGINT', () => shutdown());
process.on('SIGTERM', () => shutdown());

