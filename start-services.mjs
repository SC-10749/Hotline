import { spawn, spawnSync } from 'node:child_process';
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { inspectService, isReady } from './deploy/service-status.mjs';

const root = dirname(fileURLToPath(import.meta.url));
const port = process.env.DODO_PORT || '8888';
const javaPort = process.env.HOTLINE_JAVA_PORT || '8080';
const pythonCommand = process.platform === 'win32' ? 'python' : 'python3';
const hasUv = spawnSync('uv', ['--version'], { windowsHide: true, stdio: 'ignore' }).status === 0;
const command = hasUv ? 'uv' : pythonCommand;
const prefix = hasUv ? ['run', 'python'] : [];
const children = [];
let closing = false;
let monitor;

const shutdown = async (code = 0) => {
  if (closing) return;
  closing = true;
  clearInterval(monitor);
  await Promise.all(children.map(child => {
    if (!child.pid || child.exitCode !== null) return;
    if (process.platform !== 'win32') {
      child.kill('SIGTERM');
      return;
    }
    return new Promise(resolve => {
      const killer = spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], {
        windowsHide: true,
        stdio: 'ignore',
      });
      killer.on('error', resolve);
      killer.on('close', resolve);
    });
  }));
  process.exitCode = code;
};

const start = (name, args, executable = command, commandPrefix = prefix) => {
  const child = spawn(executable, [...commandPrefix, ...args], {
    cwd: root,
    windowsHide: true,
    stdio: 'inherit',
    env: { ...process.env, HOTLINE_PYTHON_BASE_URL: process.env.HOTLINE_PYTHON_BASE_URL || `http://127.0.0.1:${port}`,
      HOTLINE_PYTHON_ADVERTISED_PORT: process.env.HOTLINE_PYTHON_ADVERTISED_PORT || port,
      PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' },
  });
  child.on('error', error => {
    console.error(`${name} failed to start: ${error.message}`);
    void shutdown(1);
  });
  child.on('exit', (code, signal) => {
    if (!closing) {
      console.error(`${name} exited (${signal || code}).`);
      void shutdown(code || 1);
    }
  });
  children.push(child);
  return child;
};

process.on('SIGINT', () => void shutdown());
process.on('SIGTERM', () => void shutdown());

console.log(`Hotline Agent API: http://127.0.0.1:${port}/docs`);
console.log(`Java 21 API: http://127.0.0.1:${javaPort}/health/ready`);
let pythonRunning;
let javaRunning;
try {
  // Check both ports before launching any child so a conflict cannot leave partial startup.
  pythonRunning = await inspectService('Python', port, '/health', 'hotline-agent');
  javaRunning = await inspectService('Java', javaPort, '/health/live', 'hotline-java-api');
} catch (error) {
  console.error(`✗ ${error.message}`);
  process.exit(1);
}
if (closing) process.exit(process.exitCode || 0);
if (javaRunning) console.log(`✓ 复用已运行的 Java 21 服务（端口 ${javaPort}）`);
else start('Java 21 API', ['deploy/start-java.mjs'], process.execPath, []);

if (pythonRunning) console.log(`✓ 复用已运行的 Python 能力服务（端口 ${port}）`);
else start('FastAPI Gateway', ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', port]);

if (pythonRunning && await isReady(port)) console.log('✓ 复用已就绪的执行 Worker');
else start('Execution Worker', ['-m', 'python_backend.modules.execution.worker']);

const deadline = Date.now() + 120_000;
let ready = false;
while (Date.now() < deadline && !closing) {
  try {
    if (await isReady(port) && await isReady(javaPort)) {
      ready = true;
      break;
    }
  } catch { /* The API or Worker is still starting. */ }
  await new Promise(resolve => setTimeout(resolve, 500));
}

if (ready) {
  console.log('✓ Java 21、Python 能力服务与执行 Worker 已就绪。Ctrl+C 停止本次启动的服务。');
  // Keep reused sessions alive so the development launcher can run its frontend.
  let previouslyReady = true;
  let checking = false;
  monitor = setInterval(async () => {
    if (checking || closing) return;
    checking = true;
    try {
      const available = await isReady(port) && await isReady(javaPort);
      if (!closing && available !== previouslyReady) {
        console.log(available ? '✓ 后端服务已恢复就绪' : '… 后端服务暂未就绪，正在等待恢复');
        previouslyReady = available;
      }
    } finally {
      checking = false;
    }
  }, 3000);
}
else if (!closing) {
  console.error('Hotline did not become ready within 120 seconds.');
  await shutdown(1);
}
