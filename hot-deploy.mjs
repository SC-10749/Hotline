import { spawn, spawnSync } from 'node:child_process';
import { watch } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

// Hot-deploy mode: ONE service on the backend port.
// - Backend: this script supervises uvicorn itself. uvicorn's built-in --reload
//   is unreliable on Windows (it restarts the child via CTRL_C_EVENT, which is
//   silently dropped when the process has no attached console), so we watch for
//   .py changes with fs.watch and restart the child with taskkill /T /F.
// - Frontend: `vite build --watch` rewrites frontend/dist on Vue changes.
// - The served page (see /__build in fastapi_app.py) polls the backend boot id
//   and the dist fingerprint and reloads itself when either changes.
const port = process.env.DODO_HOT_PORT || '8888';
const root = dirname(fileURLToPath(import.meta.url));
const children = [];
let closing = false;
let backendChild = null;
let workerChild = null;
let restartTimer = null;
let restartCount = 0;
const pythonCommand = process.platform === 'win32' ? 'python' : 'python3';
// Backend deps live in the uv-managed .venv (uv.lock); system python may lack
// fastapi and the rest, so prefer `uv run python` and fall back to plain python.
const hasUv = spawnSync('uv', ['--version'], { windowsHide: true }).status === 0;
const backendCommand = hasUv ? 'uv' : pythonCommand;
const backendPrefix = hasUv ? ['run', 'python'] : [];

const terminateProcessTree = (child) => {
  if (!child?.pid || child.exitCode !== null) return Promise.resolve();
  if (process.platform !== 'win32') {
    child.kill('SIGTERM');
    return Promise.resolve();
  }
  return new Promise(resolve => {
    const killer = spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' });
    killer.on('error', resolve);
    killer.on('close', resolve);
  });
};

const shutdown = async (code = 0) => {
  if (closing) return;
  closing = true;
  await Promise.all(children.map(child => {
    if (!child.pid || child.exitCode !== null) return;
    return terminateProcessTree(child);
  }));
  process.exitCode = code;
};

const makeLinePump = onLine => {
  let buffer = '';
  return chunk => {
    buffer += chunk;
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop() ?? '';
    lines.forEach(onLine);
  };
};

const pipeChildOutput = (child, onLine) => {
  child.stdout.setEncoding('utf8');
  child.stderr.setEncoding('utf8');
  if (onLine) {
    const pump = makeLinePump(onLine);
    child.stdout.on('data', chunk => { process.stdout.write(chunk); pump(chunk); });
    child.stderr.on('data', chunk => { process.stderr.write(chunk); pump(chunk); });
  } else {
    child.stdout.on('data', chunk => process.stdout.write(chunk));
    child.stderr.on('data', chunk => process.stderr.write(chunk));
  }
};

let bindWarned = false;
const warnIfPortBusy = line => {
  if (bindWarned || !/error while attempting to bind|WinError 100(48|13)/i.test(line)) return;
  bindWarned = true;
  console.error(`\n✗ 端口 ${port} 已被占用，常见原因是之前的豆豆服务还在运行。`);
  console.error(`  查询占用：netstat -ano | findstr :${port}`);
  console.error(`  结束进程：taskkill /PID <PID> /F\n`);
};

const startBackend = () => {
  console.log(`▶ 启动后端服务（${[backendCommand, ...backendPrefix, '-m', 'uvicorn'].join(' ')}）…`);
  const child = spawn(backendCommand, [...backendPrefix, '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', port, '--no-use-colors'], {
    cwd: root,
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8', NO_COLOR: '1', FORCE_COLOR: '0' },
  });
  pipeChildOutput(child, line => warnIfPortBusy(line));
  child.on('error', error => {
    console.error(`Failed to start backend: ${error.message}`);
    shutdown(1);
  });
  // A crash (e.g. a syntax error right after an edit) must not kill the whole
  // hot-deploy session: stay up and let the next save restart the backend.
  child.on('exit', code => {
    if (closing || code === 0 || backendChild !== child || child._hotRestarting) return;
    console.error(`✗ 后端进程退出（退出码 ${code}），修复代码后保存即自动重启。`);
  });
  children.push(child);
  return child;
};

const startWorker = () => {
  console.log(`▶ 启动执行 Worker（${[backendCommand, ...backendPrefix, '-m', 'python_backend.modules.execution.worker'].join(' ')}）…`);
  const child = spawn(backendCommand, [...backendPrefix, '-m', 'python_backend.modules.execution.worker'], {
    cwd: root,
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8', NO_COLOR: '1', FORCE_COLOR: '0' },
  });
  pipeChildOutput(child);
  child.on('error', error => {
    console.error(`Failed to start execution worker: ${error.message}`);
    shutdown(1);
  });
  child.on('exit', code => {
    if (closing || code === 0 || workerChild !== child || child._hotRestarting) return;
    console.error(`✗ 执行 Worker 退出（退出码 ${code}），修复代码后保存即自动重启。`);
  });
  children.push(child);
  return child;
};

const restartBackend = (trigger) => {
  if (closing) return;
  restartCount += 1;
  const old = backendChild;
  const oldWorker = workerChild;
  const killOld = async () => {
    const targets = [old, oldWorker].filter(child => child?.pid && child.exitCode === null);
    targets.forEach(child => { child._hotRestarting = true; });
    await Promise.all(targets.map(terminateProcessTree));
  };
  void killOld().then(async () => {
    if (closing) return;
    // Give Windows a beat to actually release the listen socket; spawning too
    // early loses the bind race (WinError 10048) and the backend stays down.
    await new Promise(resolve => setTimeout(resolve, 800));
    if (closing) return;
    backendChild = startBackend();
    workerChild = startWorker();
    console.log(`✓ 检测到 Python 改动${trigger ? `（${trigger}）` : ''}，后端与 Worker 重启中（第 ${restartCount} 次），页面将自动刷新`);
  });
};

// uvicorn's watcher only cares about .py sources; ignore dependency and cache
// trees so dependency installs and bytecode writes never trigger restarts.
try {
  watch(root, { recursive: true }, (_event, filename) => {
    if (closing || !filename || !filename.endsWith('.py')) return;
    const normal = filename.replace(/\\/g, '/');
    if (normal.startsWith('.venv/') || normal.startsWith('venv/') || normal.includes('node_modules/') || normal.includes('__pycache__/')) return;
    clearTimeout(restartTimer);
    restartTimer = setTimeout(() => restartBackend(normal), 400);
  });
} catch (error) {
  console.error(`✗ 无法监听 Python 文件变动：${error.message}（后端将不会自动重启）`);
}

const frontendChild = spawn(process.execPath, [join(root, 'frontend', 'node_modules', 'vite', 'bin', 'vite.js'), 'build', '--watch'], {
  cwd: join(root, 'frontend'),
  windowsHide: true,
  stdio: ['ignore', 'pipe', 'pipe'],
  env: { ...process.env, NO_COLOR: '1', FORCE_COLOR: '0' },
});
pipeChildOutput(frontendChild);
frontendChild.on('error', error => {
  console.error(`Failed to start vite build watcher: ${error.message}`);
  shutdown(1);
});
children.push(frontendChild);

console.log('Hotline Agent 热部署：改 Python 自动重启网关与 Execution Worker，改 Vue 自动重建前端并刷新页面。');
console.log(`服务地址：http://127.0.0.1:${port}/（Ctrl+C 退出）`);

let frontendBuilt = false;
let backendReady = false;
const reportAllReady = () => {
  if (frontendBuilt && backendReady) {
    console.log(`\n全部就绪：打开 http://127.0.0.1:${port}/ 开始使用（改完代码稍等一两秒，页面会自动刷新）\n`);
  }
};
backendChild = startBackend();
workerChild = startWorker();

frontendChild.stdout.on('data', chunk => {
  // `watching for file changes` prints before the initial build; only a real
  // `built in` line means dist is ready to serve.
  if (frontendBuilt || !/built in/i.test(String(chunk))) return;
  frontendBuilt = true;
  console.log('✓ 前端构建完成（改动 frontend/src 会自动重建）');
  reportAllReady();
});

// Probe the service instead of parsing logs; readiness requires the backend's
// own process to still be alive so a stale service cannot fake it.
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
void waitUntilReady('后端', `http://127.0.0.1:${port}/health`, () => {
  if (!backendChild || backendChild.exitCode !== null) return;
  backendReady = true;
  console.log(`✓ 后端启动完成  http://127.0.0.1:${port}/docs`);
  reportAllReady();
});

process.on('SIGINT', () => shutdown());
process.on('SIGTERM', () => shutdown());

