const TOKEN = window.HOTLINE_TOKEN;
let projects = [], category = 'all', selected = '', eventSource = null;
let readmeRequest = 0;
const $ = id => document.getElementById(id);
const developmentStages = {
  idea: '规划中', prototype: '原型验证', working: '开发中',
  completed: '开发完成', archived: '已归档', unknown: '未标注',
};
const categoryLabel = { all: '全部', ...developmentStages };
function developmentStage(status) {
  const key = status === 'stable' ? 'completed' : Object.hasOwn(developmentStages, status) ? status : 'unknown';
  return { key, label: developmentStages[key] };
}
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[c]));
const isWebUrl = value => /^https?:\/\//i.test(value || '');
const strings = value => Array.isArray(value) ? value.filter(item => typeof item === 'string') : [];
const plannedModules = {
  harness: { title: 'Harness 工作台', description: '为 Agent 提供可控、可查看、可恢复的执行环境。', items: ['配置模型、工具、上下文、步数、超时与重试策略', '记录执行步骤、工具调用、产物和失败原因', '支持取消与重试，后续逐步建设检查点和状态恢复'] },
  skills: { title: 'Skill 中心', description: '管理技能版本、项目绑定与验证结果。', items: ['上传、编辑和校验 SKILL.md 与技能资源', '版本管理、依赖检查、启停与项目绑定', '使用固定任务验证修改效果，再决定是否启用'] },
  tools: { title: '工具与 MCP 中心', description: '统一管理 Agent 使用的外部工具和权限。', items: ['注册工具服务并检查连接与能力', '按项目配置权限和使用范围', '查看工具调用记录、错误与耗时'] },
  evaluations: { title: '评测中心', description: '验证模型、Prompt、Skill 和 Agent 改动的实际效果。', items: ['管理固定测试集、预期结果和评分规则', '比较正确性、引用质量、耗时和 Token 成本', '提供小规模回归与发布前完整评测'] },
  cicd: { title: 'CI/CD 中心', description: '把代码检查、Agent 评测和应用发布串联起来。', items: ['接入现有流水线，展示阶段状态、日志和历史', '代码提交执行检查、测试、构建与密钥检查', '发布前评测与确认，发布后健康检查和失败回滚'] },
  observability: { title: '运行观测', description: '查看任务稳定性、执行轨迹和资源成本。', items: ['统计成功率、耗时、错误、重试和工具调用', '按项目、模型与版本统计 Token 和估算成本', '关联执行记录与产物，逐步增加日志脱敏和诊断导出'] },
};

function selectSection(section) {
  const plan = plannedModules[section];
  $('project-section').hidden = !!plan;
  $('future-section').hidden = !plan;
  if (plan) {
    $('future-title').textContent = plan.title;
    $('future-description').textContent = plan.description;
    $('future-items').innerHTML = plan.items.map(item => `<li>${esc(item)}</li>`).join('');
  }
  $('platform-nav').querySelectorAll('[data-section]').forEach(button => {
    const active = button.dataset.section === (plan ? section : 'projects');
    button.classList.toggle('active', active);
    if (active) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
}

async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { 'X-Hotline-Token': TOKEN, ...options.headers } });
  const data = await response.json();
  if (!response.ok) throw Error(data.error || '请求失败，请重试');
  return data;
}
function statusLabel(state) {
  return ({ idle: '待启动', starting: '启动中', running: '已启动', stopping: '停止中', stopped: '已停止', exited: '已退出', failed: '启动失败' })[state] || state;
}
function renderFilters() {
  const counts = { all: projects.length };
  projects.forEach(p => { const key = developmentStage(p.status).key; counts[key] = (counts[key] || 0) + 1; });
  $('filters').innerHTML = ['all', 'working', 'completed', 'prototype', 'idea', 'archived', 'unknown'].filter(c => c === 'all' || counts[c]).map(c => `<button class="${category === c ? 'active' : ''}" data-filter="${c}">${categoryLabel[c]} ${counts[c] || 0}</button>`).join('');
  $('filters').querySelectorAll('button').forEach(button => button.onclick = () => { category = button.dataset.filter; render(); });
}
function render() {
  const query = $('search').value.toLowerCase();
  const filtered = projects.filter(p => (category === 'all' || developmentStage(p.status).key === category) && JSON.stringify(p).toLowerCase().includes(query));
  $('grid').innerHTML = filtered.length ? filtered.map(p => {
    const active = ['starting', 'running', 'stopping'].includes(p.state);
    const stage = developmentStage(p.status);
    const link = p.state === 'running' && isWebUrl(p.url)
      ? `<a class="project-link" href="${esc(p.url)}" target="_blank" rel="noopener noreferrer" aria-label="打开 ${esc(p.name)} 页面">${esc(p.url)} <span aria-hidden="true">↗</span></a>` : '';
    return `<article class="card"><div class="card-top"><div style="min-width:0"><h2 title="${esc(p.name)}">${esc(p.name)}</h2><div class="path">${esc(p.path)}</div></div><span class="development-badge ${stage.key}" aria-label="开发状态：${stage.label}">${stage.label}</span></div>
      <p class="desc">${esc(p.description || '暂无描述')}</p><div class="meta"><span class="tag">${esc(categoryLabel[p.category] || p.category)}</span><span class="tag">${esc(p.mode || '未声明模式')}</span>${(p.language || []).map(l => `<span class="tag">${esc(l)}</span>`).join('')}</div>
      <div class="card-runtime"><span>运行状态</span><span class="status ${esc(p.state)}">${statusLabel(p.state)}</span></div>${link}<div class="actions"><button class="action readme-button" data-readme="${esc(p.path)}" aria-label="查看 ${esc(p.name)} 的 Readme">Readme</button>
      ${active ? `<button class="action stop" data-stop="${esc(p.path)}" ${p.state === 'stopping' ? 'disabled' : ''}>${p.state === 'stopping' ? '停止中…' : '停止'}</button>` : `<button class="action" data-start="${esc(p.path)}" ${p.runCommand ? '' : 'disabled'}>${p.runCommand ? '启动项目' : '未配置启动命令'}</button>`}</div></article>`;
  }).join('') : '<div class="empty">没有匹配的项目<br><small>添加 project.yaml 后刷新控制台</small></div>';
  $('grid').querySelectorAll('[data-start]').forEach(button => button.onclick = () => start(button.dataset.start));
  $('grid').querySelectorAll('[data-stop]').forEach(button => button.onclick = () => stop(button.dataset.stop));
  $('grid').querySelectorAll('[data-readme]').forEach(button => button.onclick = () => openReadme(button.dataset.readme));
  renderFilters();
}
function connectEvents(id) {
  eventSource?.close();
  eventSource = new EventSource('/api/events?id=' + encodeURIComponent(id));
  eventSource.addEventListener('snapshot', event => { $('log').textContent = JSON.parse(event.data).log || '该项目暂无输出。'; });
  eventSource.addEventListener('output', event => {
    $('log').textContent += JSON.parse(event.data).value;
    $('log').scrollTop = $('log').scrollHeight;
  });
  eventSource.addEventListener('ready', () => { show('项目已启动，点击卡片上的页面链接即可访问。'); refresh(); });
  eventSource.addEventListener('state', () => refresh());
  eventSource.onerror = () => { $('updated').textContent = '实时连接已断开，正在重连'; };
}
async function start(id) {
  const project = projects.find(p => p.path === id);
  if (project && ['starting', 'running', 'stopping'].includes(project.state)) return;
  if (project) { project.state = 'starting'; render(); }
  try {
    selected = id; connectEvents(id);
    await api('/api/start?id=' + encodeURIComponent(id), { method: 'POST' });
    show('项目正在启动，服务就绪后卡片会显示页面链接。');
  } catch (error) { show(error.message); }
  await refresh();
}
async function stop(id) {
  try {
    selected = id; connectEvents(id);
    await api('/api/stop?id=' + encodeURIComponent(id), { method: 'POST' });
    await refresh();
  } catch (error) { show(error.message); }
}
function show(message) {
  $('notice').innerHTML = `<div class="notice" role="status">${esc(message)}</div>`;
  clearTimeout(show.timer);
  show.timer = setTimeout(() => { $('notice').innerHTML = ''; }, 5000);
}
async function refresh() {
  try {
    const data = await api('/api/projects');
    projects = data.projects; render();
    $('updated').textContent = `${projects.length} 个项目 · ${new Date().toLocaleTimeString()}`;
    if (data.errors.length) show(data.errors.join('；'));
    if (selected) {
      const logs = await api('/api/logs?id=' + encodeURIComponent(selected));
      $('log').textContent = logs.log || '该项目暂无输出。';
    }
  } catch (error) { show(error.message); $('updated').textContent = '连接失败'; }
}
async function openReadme(id) {
  const request = ++readmeRequest;
  const project = projects.find(p => p.path === id);
  $('readme-title').textContent = `${project?.name || '项目'} · Readme`;
  $('readme-content').innerHTML = '<p role="status">正在读取项目说明…</p>';
  if (!$('readme-dialog').open) $('readme-dialog').showModal();
  try {
    const data = await api('/api/readme?id=' + encodeURIComponent(id));
    if (request !== readmeRequest || !$('readme-dialog').open) return;
    const overview = data.overview || {};
    const stack = strings(overview.techStack).length ? strings(overview.techStack) : strings(data.language);
    const features = strings(overview.features);
    const services = Array.isArray(overview.services) ? overview.services.filter(s => s && typeof s === 'object') : [];
    const list = items => `<ul>${items.map(item => `<li>${esc(item)}</li>`).join('')}</ul>`;
    $('readme-content').innerHTML = `<p class="readme-description">${esc(data.description || '项目说明')}</p>
      <section><h3>技术栈</h3>${stack.length ? list(stack) : '<p>暂未整理，请查看下方 README。</p>'}</section>
      <section><h3>主要功能</h3>${features.length ? list(features) : '<p>请查看下方 README 中的功能介绍。</p>'}</section>
      <section><h3>启动需要的服务</h3>${services.length ? `<div class="service-list">${services.map(s => `<article><div class="service-heading"><strong>${esc(s.name)}</strong><span class="tag">${esc(s.requirement)}</span></div><p>${esc(s.description)}</p></article>`).join('')}</div>` : '<p>暂未整理服务依赖，请参考项目 README。</p>'}</section>
      ${strings(overview.startup).length ? `<section><h3>启动步骤</h3><ol>${strings(overview.startup).map(step => `<li>${esc(step)}</li>`).join('')}</ol></section>` : ''}
      ${data.readme ? `<details ${!features.length ? 'open' : ''}><summary>查看完整 README.md</summary><pre class="readme-source">${esc(data.readme)}</pre></details>` : '<p class="readme-description">项目暂无 README.md，可在项目目录添加说明。</p>'}`;
  } catch (error) {
    if (request === readmeRequest) {
      $('readme-content').innerHTML = `<p role="alert">读取失败：${esc(error.message)}</p><button class="action" id="retry-readme">重新加载</button>`;
      $('retry-readme').onclick = () => openReadme(id);
    }
  }
}
$('close-readme').onclick = () => $('readme-dialog').close();
$('readme-dialog').addEventListener('close', () => { readmeRequest++; });
$('readme-dialog').addEventListener('click', event => { if (event.target === $('readme-dialog')) { const rect = event.target.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) event.target.close(); } });
$('search').oninput = render;
$('clear').onclick = () => { $('log').textContent = ''; };
$('platform-nav').querySelectorAll('[data-section]').forEach(button => button.onclick = () => selectSection(button.dataset.section));
$('back-to-projects').onclick = () => selectSection('projects');
refresh();
setInterval(refresh, 1800);
