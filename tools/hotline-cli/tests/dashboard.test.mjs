import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { createServer } from 'node:net';
import vm from 'node:vm';
const cli = resolve(fileURLToPath(new URL('..', import.meta.url)));
const root = resolve(cli, '../..');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function freePort() {
  const server = createServer();
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  return port;
}
async function until(fn) {
  for (let i = 0; i < 100; i++) { const result = await fn(); if (result) return result; await delay(100); }
  throw Error('Timed out waiting for dashboard');
}
test('cards wait for readiness, never navigate automatically, and show safe Readme', async () => {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, { innerHTML: '', textContent: '', value: '', open: false, hidden: false, children: [], classList: { add() {}, remove() {} }, setAttribute() {}, appendChild(child) { this.children.push(child); }, querySelectorAll: () => [], addEventListener() {}, showModal() { this.open = true; }, close() { this.open = false; } });
    return elements.get(id);
  };
  const project = { path: 'projects/ai/demo', name: 'Demo', state: 'starting', url: 'http://127.0.0.1:5180/', runCommand: ['node'], language: ['Vue'] };
  const sources = [];
  class Events { constructor() { this.handlers = {}; sources.push(this); } addEventListener(name, fn) { this.handlers[name] = fn; } close() {} }
  const context = vm.createContext({ document: { getElementById: element, createElement: tag => ({ tag, dataset: {}, hidden: false, remove() { this.removed = true; } }) }, window: { HOTLINE_TOKEN: '', location: { href: 'dashboard', hash: '' }, history: { pushState(_state, _title, hash) { context.window.location.hash = hash; } }, addEventListener() {} }, EventSource: Events, setTimeout: () => 1, clearTimeout() {}, setInterval() {}, fetch: async path => ({ ok: true, json: async () => path.startsWith('/api/skills') ? { skills: [], bindings: [] } : path.startsWith('/api/readme') ? { overview: { techStack: ['Vue 3'], features: ['Chat'], services: [{ name: 'SQLite', requirement: '内置', description: '无需外部服务' }] }, readme: '<script>alert(1)</script>' } : { projects: [project], errors: [], log: '' } }) });
  vm.runInContext(readFileSync(join(cli, 'public/dashboard.js'), 'utf8'), context);
  await delay(0);
  vm.runInContext("selectSection('skills')", context);
  assert.equal(element('skill-section').hidden, false);
  assert.equal(context.window.location.hash, '#skills');
  vm.runInContext("selectSection(window.location.hash.slice(1), false)", context);
  assert.equal(element('skill-section').hidden, false, 'restoring address must preserve Skill center');
  assert.equal(element('future-section').hidden, true);
  for (const section of ['harness', 'tools', 'evaluations', 'cicd', 'observability']) {
    vm.runInContext(`selectSection('${section}')`, context);
    assert.equal(element('project-section').hidden, true);
    assert.equal(element('future-section').hidden, false);
    assert.ok(element('future-title').textContent.length > 0);
    assert.ok(element('future-items').innerHTML.includes('<li>'));
  }
  await vm.runInContext('refresh()', context);
  assert.equal(element('future-section').hidden, false, 'status polling must not leave planning view');
  vm.runInContext("selectSection('projects')", context);
  assert.equal(element('project-section').hidden, false);
  assert.equal(element('future-section').hidden, true);
  assert.ok(element('grid').innerHTML.includes('启动中'));
  assert.ok(element('grid').innerHTML.includes('data-readme'));
  assert.ok(!element('grid').innerHTML.includes('class="project-link"'));
  project.state = 'running';
  await vm.runInContext('refresh()', context);
  assert.ok(element('grid').innerHTML.includes('已启动'));
  assert.ok(element('grid').innerHTML.includes('class="project-link"'));
  assert.ok(element('grid').innerHTML.includes('target="_blank"'));
  for (const [status, label] of [['working', '开发中'], ['completed', '开发完成'], ['stable', '开发完成'], ['prototype', '原型验证'], ['idea', '规划中'], ['archived', '已归档'], [undefined, '未标注'], ['unexpected', '未标注']]) {
    project.status = status;
    await vm.runInContext('refresh()', context);
    assert.ok(element('grid').innerHTML.includes(`aria-label="开发状态：${label}"`));
    assert.ok(element('grid').innerHTML.includes('已启动'), 'development label must not replace runtime state');
  }
  project.status = 'stable';
  vm.runInContext("category = 'completed'; render()", context);
  assert.ok(element('grid').innerHTML.includes('Demo'), 'completion filter must include stable alias');
  vm.runInContext("category = 'all'", context);
  assert.ok(!readFileSync(join(cli, 'public/index.html'), 'utf8').includes('项目分类'));
  assert.ok(!readFileSync(join(cli, 'public/index.html'), 'utf8').includes('id="nav"'));
  vm.runInContext("connectEvents('projects/ai/demo')", context);
  sources[0].handlers.ready({ data: JSON.stringify({ url: project.url }) });
  assert.equal(context.window.location.href, 'dashboard');
  await vm.runInContext("openReadme('projects/ai/demo')", context);
  assert.equal(element('readme-dialog').open, true);
  for (const text of ['技术栈', '主要功能', '启动需要的服务', 'SQLite', '无需外部服务']) assert.ok(element('readme-content').innerHTML.includes(text));
  assert.ok(element('readme-content').innerHTML.includes('&lt;script&gt;'));
  assert.ok(!element('readme-content').innerHTML.includes('<script>'));
  project.state = 'stopped';
  await vm.runInContext('refresh()', context);
  assert.ok(!element('grid').innerHTML.includes('class="project-link"'));

});
test('HTTP health checks, duplicate starts, Readme API and process cleanup', async () => {
  const port = await freePort(), appPort = await freePort();
  const name = `dashboard-test-${process.pid}`, id = `projects/.dashboard-tests/${name}`;
  const fixture = join(root, id);
  mkdirSync(fixture, { recursive: true });
  writeFileSync(join(fixture, 'README.md'), '# Test project\nTech stack and services.\n');
  writeFileSync(join(fixture, 'server.mjs'), `import {createServer} from 'node:http';import {existsSync} from 'node:fs';createServer((req,res)=>{res.statusCode=req.url==='/health'&&!existsSync('ready')?503:200;res.end('OK')}).listen(${appPort},'127.0.0.1',()=>console.log('Local: http://127.0.0.1:${appPort}/'));`);
  writeFileSync(join(fixture, 'project.yaml'), JSON.stringify({ name, healthChecks: [`http://127.0.0.1:${appPort}/health`], commands: { start: [process.execPath, 'server.mjs'] }, overview: { techStack: ['Node.js'], features: ['Test server'] } }));
  const child = spawn(process.execPath, ['--import', 'tsx', 'src/dashboard.ts'], { cwd: cli, env: { ...process.env, HOTLINE_PORT: String(port), HOTLINE_SKILL_DB: join(fixture, 'skills.db'), NODE_OPTIONS: '' }, windowsHide: true, stdio: 'pipe' });
  let logs = '', token, started = false;
  child.stdout.on('data', value => logs += value);
  child.stderr.on('data', value => logs += value);
  const origin = `http://127.0.0.1:${port}`;
  const call = (path, method = 'GET') => fetch(origin + path, { method, headers: { 'X-Hotline-Token': token || '' } });
  const status = async () => (await (await call('/api/projects')).json()).projects.find(p => p.path === id);
  try {
    token = await until(async () => { try { return (await (await fetch(origin)).text()).match(/HOTLINE_TOKEN='([^']+)'/)[1]; } catch { if (child.exitCode !== null) throw Error(logs); return false; } });
    assert.equal((await call('/dashboard.js')).status, 200);
    const skillCall = args => fetch(origin + '/api/skills', { method: 'POST', headers: { 'X-Hotline-Token': token }, body: JSON.stringify(args) });
    const savedResponse = await skillCall({ action: 'save', args: { content: '---\nname: integration-demo\ndescription: Integration test\n---\nSummarize facts.' } });
    assert.equal(savedResponse.status, 200);
    const saved = await savedResponse.json();
    assert.equal((await skillCall({ action: 'bind', args: { ...saved, project: id } })).status, 200);
    const runtime = await (await call('/api/skills?project=' + encodeURIComponent(id))).json();
    assert.equal(runtime.skills[0].version, saved.version);
    assert.equal((await fetch(origin + '/api/skills', { method: 'POST', body: '{}' })).status, 403);
    const info = await (await call('/api/readme?id=' + id)).json();
    assert.deepEqual(info.overview.techStack, ['Node.js']);
    assert.ok(info.readme.includes('# Test project'));
    assert.equal((await call('/api/readme?id=../../package.json')).status, 404);
    assert.equal((await call('/api/start?id=' + id, 'POST')).status, 200);
    started = true;
    assert.equal((await call('/api/start?id=' + id, 'POST')).status, 409);
    await until(async () => (await status()).url);
    await delay(2300);
    assert.equal((await status()).state, 'starting', 'HTTP 503 must prevent premature success');
    writeFileSync(join(fixture, 'ready'), 'ready');
    await until(async () => (await status()).state === 'running');
    assert.equal((await status()).url, `http://127.0.0.1:${appPort}/`);
    assert.equal((await call('/api/stop?id=' + id, 'POST')).status, 200);
    await until(async () => (await status()).state === 'stopped');
    started = false;
    assert.equal((await call('/api/start?id=' + id, 'POST')).status, 200);
    started = true;
    assert.equal((await call('/api/stop?id=' + id, 'POST')).status, 200);
    await until(async () => (await status()).state === 'stopped');
    started = false;
  } finally {
    if (started && token) await call('/api/stop?id=' + id, 'POST');
    child.kill();
    assert.equal(resolve(fixture), resolve(root, 'projects/.dashboard-tests', name));
    rmSync(fixture, { recursive: true, force: true });
  }
});
