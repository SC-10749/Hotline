import { spawn, spawnSync } from 'node:child_process';
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));
const port = process.env.DODO_PORT || '8888';
const pythonCommand = process.platform === 'win32' ? 'python' : 'python3';
const hasUv = spawnSync('uv', ['--version'], { windowsHide: true, stdio: 'ignore' }).status === 0;
const command = hasUv ? 'uv' : pythonCommand;
const prefix = hasUv ? ['run', 'python'] : [];
const children = [];
let closing = false;

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

const start = (name, args) => {
  const child = spawn(command, [...prefix, ...args], {
    cwd: root,
    windowsHide: true,
    stdio: 'inherit',
    env: { ...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' },
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
start('Execution Worker', ['-m', 'python_backend.modules.execution.worker']);
start('FastAPI Gateway', ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', port]);

const deadline = Date.now() + 60_000;
let ready = false;
while (Date.now() < deadline && !closing) {
  try {
    const response = await fetch(`http://127.0.0.1:${port}/health/ready`, {
      signal: AbortSignal.timeout(1500),
    });
    if (response.ok) {
      ready = true;
      break;
    }
  } catch { /* The API or Worker is still starting. */ }
  await new Promise(resolve => setTimeout(resolve, 500));
}

if (ready) console.log('Gateway and Execution Worker are ready. Press Ctrl+C to stop both.');
else if (!closing) {
  console.error('Hotline did not become ready within 60 seconds.');
  await shutdown(1);
}
