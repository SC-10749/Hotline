import { createServer } from 'node:http';
import { existsSync, readFileSync, realpathSync } from 'node:fs';
import { join, relative, isAbsolute } from 'node:path';
import { spawn } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { stripVTControlCharacters } from 'node:util';
import { parse } from 'yaml';
import { discoverProjects, projectsDir, rootDir } from './projects.js';
const token = randomBytes(32).toString('hex');
const port = Number(process.env.HOTLINE_PORT ?? 4311);
const runs = new Map();
const subscribers = new Map();
const publish = (id, event, data) => {
    const payload = `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
    for (const subscriber of subscribers.get(id) ?? [])
        subscriber.res.write(payload);
};
const append = (id, run, value) => {
    value = stripVTControlCharacters(value);
    run.log = (run.log + value).slice(-65536);
    const clean = run.log.replace(/\u001b\[[0-?]*[ -/]*[@-~]/g, '');
    const match = clean.match(/Local:\s+(https?:\/\/[^\s]+)/i);
    if (match) {
        const url = match[1].replace(/[),\]]+$/, '');
        if (url !== run.url) {
            run.url = url;
        }
    }
    publish(id, 'output', { value });
};
async function checkReady(id, run) {
    if (run.state !== 'starting' || run.probing)
        return;
    const urls = [...new Set([run.url, ...run.healthChecks].filter((v) => !!v))];
    if (!urls.length)
        return;
    run.probing = true;
    try {
        const responses = await Promise.all(urls.map(url => fetch(url, { signal: AbortSignal.timeout(2000), redirect: 'manual' })));
        await Promise.all(responses.map(response => response.body?.cancel()));
        if (responses.every(response => response.ok) && run.state === 'starting' && runs.get(id) === run) {
            run.state = 'running';
            publish(id, 'ready', { url: run.url });
            publish(id, 'state', { state: run.state });
        }
    }
    catch { /* Services may still be starting; retry on the next tick. */ }
    finally {
        run.probing = false;
    }
}
const readinessTimer = setInterval(() => {
    for (const [id, run] of runs)
        void checkReady(id, run);
}, 1000);
readinessTimer.unref();
async function stop(id, run) {
    if (!run.child.pid || !['starting', 'running', 'stopping'].includes(run.state))
        return;
    const previousState = run.state;
    run.state = 'stopping';
    publish(id, 'state', { state: run.state });
    if (process.platform === 'win32') {
        await new Promise((resolve, reject) => {
            const killer = spawn('taskkill', ['/pid', String(run.child.pid), '/T', '/F'], { windowsHide: true });
            let message = '';
            killer.stderr?.on('data', data => { message += data.toString(); });
            killer.on('error', error => { run.state = previousState; reject(error); });
            killer.on('exit', code => {
                if (code === 0 || run.child.exitCode !== null)
                    resolve();
                else {
                    run.state = previousState;
                    append(id, run, `\n停止失败：${message}\n`);
                    publish(id, 'state', { state: run.state });
                    reject(new Error(`停止失败：${message || '请检查进程权限后重试'}`));
                }
            });
        });
    }
    else {
        try {
            process.kill(-run.child.pid, 'SIGKILL');
        }
        catch (error) {
            if (error.code !== 'ESRCH')
                throw error;
        }
    }
}
const server = createServer(async (req, res) => {
    const json = (code, data) => {
        res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
        res.end(JSON.stringify(data));
    };
    try {
        const origin = `http://127.0.0.1:${port}`;
        if (req.headers.host !== `127.0.0.1:${port}`)
            return json(403, { error: '请使用控制台输出的本地地址' });
        const url = new URL(req.url ?? '/', origin);
        if (req.method === 'POST' && (req.headers['x-hotline-token'] !== token || (req.headers.origin && req.headers.origin !== origin))) {
            return json(403, { error: '请求校验失败，请刷新页面' });
        }
        if (req.method === 'GET' && url.pathname === '/') {
            res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', 'X-Frame-Options': 'DENY' });
            return res.end(readFileSync(join(rootDir, 'tools/hotline-cli/public/index.html'), 'utf8').replace('__TOKEN__', token));
        }
        if (req.method === 'GET' && (url.pathname === '/favicon.svg' || url.pathname === '/favicon.ico')) {
            res.writeHead(200, { 'Content-Type': 'image/svg+xml', 'Cache-Control': 'no-cache' });
            return res.end(readFileSync(join(rootDir, 'tools/hotline-cli/public/favicon.svg'), 'utf8'));
        }
        if (req.method === 'GET' && url.pathname === '/dashboard.js') {
            res.writeHead(200, { 'Content-Type': 'text/javascript; charset=utf-8', 'Cache-Control': 'no-store' });
            return res.end(readFileSync(join(rootDir, 'tools/hotline-cli/public/dashboard.js'), 'utf8'));
        }
        if (req.method === 'GET' && url.pathname === '/dashboard.css') {
            res.writeHead(200, { 'Content-Type': 'text/css; charset=utf-8', 'Cache-Control': 'no-store' });
            return res.end(readFileSync(join(rootDir, 'tools/hotline-cli/public/dashboard.css'), 'utf8'));
        }
        if (req.method === 'GET' && url.pathname === '/api/projects') {
            const errors = [];
            const projects = discoverProjects(errors).map(p => ({ ...p, url: runs.get(p.path)?.url ?? p.url, state: runs.get(p.path)?.state ?? 'idle', code: runs.get(p.path)?.code ?? null }));
            return json(200, { projects, errors });
        }
        if (url.pathname === '/api/skills' && ['GET', 'POST'].includes(req.method ?? '')) {
            let request;
            if (req.method === 'GET') {
                const project = url.searchParams.get('project');
                request = project ? { action: 'runtime', args: { project } } : { action: 'list' };
            }
            else {
                let body = '';
                for await (const chunk of req) {
                    body += chunk.toString();
                    if (Buffer.byteLength(body) > 6 * 1024 * 1024)
                        return json(413, { error: '技能请求过大' });
                }
                request = JSON.parse(body);
                if (!['save', 'bind'].includes(request.action))
                    return json(400, { error: '不支持的技能操作' });
            }
            const result = await new Promise((resolve, reject) => {
                const python = process.env.HOTLINE_PYTHON ?? (process.platform === 'win32'
                    ? join(rootDir, 'projects/ai/dodo-agent/.venv/Scripts/python.exe') : 'python3');
                const child = spawn(python, [join(rootDir, 'tools/skill-center/center.py')], {
                    cwd: rootDir, windowsHide: true, env: { ...process.env, PYTHONUTF8: '1' },
                });
                let output = '';
                const timer = setTimeout(() => { child.kill(); reject(new Error('技能服务超时')); }, 15000);
                child.on('error', error => { clearTimeout(timer); reject(error); });
                child.stdout.on('data', chunk => { output += chunk.toString(); });
                child.stdin.on('error', () => { });
                child.on('close', code => {
                    clearTimeout(timer);
                    try {
                        resolve({ code: code === 0 ? 200 : 400, data: JSON.parse(output) });
                    }
                    catch {
                        reject(new Error('Python 技能服务启动失败，请配置 HOTLINE_PYTHON'));
                    }
                });
                child.stdin.end(JSON.stringify(request));
            });
            return json(result.code, result.data);
        }
        const id = url.searchParams.get('id') ?? '';
        if (req.method === 'GET' && url.pathname === '/api/readme') {
            const project = discoverProjects().find(p => p.path === id);
            if (!project)
                return json(404, { error: '项目不存在' });
            const cwd = realpathSync(join(rootDir, project.path));
            const rel = relative(realpathSync(projectsDir), cwd);
            if (!rel || rel.startsWith('..') || isAbsolute(rel))
                return json(403, { error: '项目目录超出 projects 范围' });
            const metadata = parse(readFileSync(join(cwd, 'project.yaml'), 'utf8'));
            const readmePath = join(cwd, 'README.md');
            let readme = '';
            if (existsSync(readmePath)) {
                const readmeRel = relative(cwd, realpathSync(readmePath));
                if (readmeRel.startsWith('..') || isAbsolute(readmeRel))
                    return json(403, { error: 'README 超出项目目录' });
                readme = readFileSync(readmePath, 'utf8');
            }
            return json(200, { name: project.name, description: project.description, language: project.language, overview: metadata.overview ?? {}, readme });
        }
        if (req.method === 'GET' && url.pathname === '/api/logs')
            return json(200, { log: runs.get(id)?.log ?? '' });
        if (req.method === 'GET' && url.pathname === '/api/events') {
            res.writeHead(200, { 'Content-Type': 'text/event-stream; charset=utf-8', 'Cache-Control': 'no-cache', Connection: 'keep-alive' });
            res.write(`event: snapshot\ndata: ${JSON.stringify({ log: runs.get(id)?.log ?? '', state: runs.get(id)?.state ?? 'idle', url: runs.get(id)?.url })}\n\n`);
            const subscriber = { res };
            const set = subscribers.get(id) ?? new Set();
            set.add(subscriber);
            subscribers.set(id, set);
            const cleanup = () => { set.delete(subscriber); if (!set.size)
                subscribers.delete(id); };
            req.on('close', cleanup);
            return;
        }
        if (req.method !== 'POST' || !['/api/start', '/api/stop'].includes(url.pathname))
            return json(404, { error: '接口不存在' });
        if (url.pathname === '/api/stop') {
            const run = runs.get(id);
            if (!run)
                return json(404, { error: '该项目尚未启动' });
            await stop(id, run);
            return json(200, { ok: true });
        }
        const project = discoverProjects().find(p => p.path === id);
        if (!project?.runCommand)
            return json(400, { error: '项目不存在或缺少 commands.run，请检查 project.yaml' });
        if (['starting', 'running', 'stopping'].includes(runs.get(id)?.state ?? ''))
            return json(409, { error: '项目已经在运行' });
        const cwd = realpathSync(join(rootDir, project.path));
        const rel = relative(realpathSync(projectsDir), cwd);
        if (!rel || rel.startsWith('..') || isAbsolute(rel))
            return json(403, { error: '项目目录超出 projects 范围' });
        const command = project.runCommand;
        const child = Array.isArray(command)
            ? spawn(command[0], command.slice(1), { cwd, windowsHide: true, detached: process.platform !== 'win32' })
            : spawn(command, { cwd, shell: true, windowsHide: true, detached: process.platform !== 'win32' });
        const run = { child, state: 'starting', log: `$ ${Array.isArray(command) ? command.join(' ') : command}\n`, code: null, url: project.url, healthChecks: project.healthChecks ?? [] };
        runs.set(id, run);
        publish(id, 'state', { state: run.state });
        child.stdout?.setEncoding('utf8');
        child.stderr?.setEncoding('utf8');
        child.stdout?.on('data', data => append(id, run, data));
        child.stderr?.on('data', data => append(id, run, data));
        child.on('error', error => { run.state = 'failed'; append(id, run, `\n启动失败：${error.message}\n`); publish(id, 'state', { state: run.state }); });
        child.on('close', code => { run.code = code; run.state = run.state === 'stopping' ? 'stopped' : code === 0 ? 'exited' : 'failed'; append(id, run, `\n进程结束，退出码：${code}\n`); publish(id, 'state', { state: run.state, code }); });
        return json(200, { ok: true });
    }
    catch (error) {
        json(500, { error: error instanceof Error ? error.message : '操作失败' });
    }
});
server.on('error', error => { console.error(`控制台启动失败：${error.message}`); process.exitCode = 1; });
server.listen(port, '127.0.0.1', () => console.log(`Hotline 控制台：http://127.0.0.1:${port}\n按 Ctrl+C 停止控制台及其项目进程。`));
let closing = false;
async function shutdown() {
    if (closing)
        return;
    closing = true;
    const results = await Promise.allSettled([...runs.entries()].map(([id, run]) => stop(id, run)));
    results.forEach(r => { if (r.status === 'rejected')
        console.error(r.reason); });
    server.close();
    process.exit(results.some(r => r.status === 'rejected') ? 1 : 0);
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
