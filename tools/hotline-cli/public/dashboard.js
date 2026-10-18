const TOKEN = window.HOTLINE_TOKEN;
let projects = [], category = 'all', selected = '', eventSource = null;
const projectLogs = new Map();
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

function selectSection(section, updateAddress = true) {
  if (section !== 'projects' && section !== 'skills' && section !== 'documents' && section !== 'evolution' && !Object.hasOwn(plannedModules, section)) section = 'projects';
  const hash = `#${section}`;
  if (updateAddress && window.location.hash !== hash) window.history.pushState(null, '', hash);
  $('skill-section').hidden = section !== 'skills';
  $('document-section').hidden = section !== 'documents';
  $('evolution-section').hidden = section !== 'evolution';
  if (section === 'evolution') {
    $('project-section').hidden = true;
    $('future-section').hidden = true;
    $('platform-nav').querySelectorAll('[data-section]').forEach(button => { const active = button.dataset.section === section; button.classList.toggle('active', active); if (active) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current'); });
    void loadEvolutionView();
    return;
  }
  if (section === 'documents') {
    $('project-section').hidden = true;
    $('future-section').hidden = true;
    $('platform-nav').querySelectorAll('[data-section]').forEach(button => {
      const active = button.dataset.section === section;
      button.classList.toggle('active', active);
      if (active) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');
    });
    void loadDocuments();
    return;
  }
  if (section === 'skills') {
    $('project-section').hidden = true;
    $('future-section').hidden = true;
    $('platform-nav').querySelectorAll('[data-section]').forEach(button => {
      button.classList.toggle('active', button.dataset.section === section);
      if (button.dataset.section === section) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');
    });
    void loadSkills();
    return;
  }
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

let documentCatalog = [];
function renderDocuments() {
  const query = $('document-search').value.trim().toLowerCase();
  const visible = documentCatalog.filter(doc => String(doc.fileName || doc.name || '').toLowerCase().includes(query));
  $('document-count').textContent = `${visible.length} 份文档`;
  $('document-list').innerHTML = visible.map(doc => { const id = doc.fileId || doc.id || ''; return `<article class="skill-card"><div class="skill-card-top"><span class="skill-icon tools" aria-hidden="true">DOC</span><span class="skill-binding is-bound">平台目录</span></div><div class="skill-heading"><span class="skill-category">${esc(doc.docType || '文档')}</span><h2>${esc(doc.fileName || doc.name || '未命名文档')}</h2></div><p class="skill-intro">状态：${esc(doc.status || '已登记')} · ${esc(doc.charCount || 0)} 字</p><div class="skill-version-row"><label>文档 ID <span>${esc(id)}</span></label></div><button class="action readme-button document-preview-button" type="button" data-document-preview="${esc(id)}">查看分块与图片描述</button></article>`; }).join('') || '<div class="empty">暂无文档</div>';
  $('document-list').querySelectorAll('[data-document-preview]').forEach(button => button.onclick = () => openDocumentPreview(button.dataset.documentPreview));
}
async function openDocumentPreview(id) {
  $('document-dialog-title').textContent = '文档预览';
  $('document-dialog-subtitle').textContent = '正在读取文档分块与图片描述…';
  $('document-content').innerHTML = '<p role="status">正在加载…</p>';
  if (!$('document-dialog').open) $('document-dialog').showModal();
  try {
    const data = await api('/api/documents/' + encodeURIComponent(id) + '/preview');
    const summary = data.summary || {};
    $('document-dialog-subtitle').textContent = `${summary.childCount ?? 0} 个子分段 · ${summary.sectionCount ?? 0} 个章节 · ${summary.imageCount ?? 0} 张图片`;
    const stats = `<div class="document-preview-stats"><span>子分段 <b>${esc(summary.childCount ?? 0)}</b></span><span>章节 <b>${esc(summary.sectionCount ?? 0)}</b></span><span>图片 <b>${esc(summary.imageCount ?? 0)}</b></span><span>图注 <b>${esc(summary.captionCount ?? 0)}</b></span></div>`;
    const sections = (data.sections || []).map(section => `<details class="document-preview-section" open><summary>${esc(section.heading || '未命名章节')} <span>${esc(section.chunkCount ?? 0)} 块 · ${esc(section.charCount ?? 0)} 字</span></summary><div>${(section.chunks || []).map(chunk => `<article class="document-chunk"><header>块 ${esc(chunk.index ?? '')}<code>${esc(chunk.charCount ?? 0)} 字</code></header><pre>${esc(chunk.content || '')}</pre></article>`).join('')}</div></details>`).join('');
    const images = (data.images || []).map(image => `<article class="document-image">${image.src ? `<img src="${esc(image.src)}" alt="${esc(image.alt || `文档图片 ${image.index ?? ''}`)}" loading="lazy">` : ''}<div><strong>图片 ${esc(image.index ?? '')}</strong><span>${esc(image.captionSource === 'generated' ? 'AI 图注' : '原文说明')}</span></div><p>${esc(image.caption || image.alt || '暂无图片描述')}</p></article>`).join('');
    $('document-content').innerHTML = stats + `<h3>父子分块</h3>${sections || '<p>暂无分块数据。</p>'}<h3>图片描述</h3>${images || '<p>这份文档没有图片或图注。</p>'}`;
  } catch (error) { $('document-dialog-subtitle').textContent = '读取失败'; $('document-content').innerHTML = `<p role="alert">${esc(error.message)}</p>`; }
}
async function loadDocuments() {
  $('document-refresh').disabled = true;
  try {
    const result = await api('/api/documents');
    documentCatalog = result.documents || [];
    renderDocuments();
  } catch (e) { $('document-message').textContent = `加载失败：${e.message}`; }
  finally { $('document-refresh').disabled = false; }
}
$('document-refresh').onclick = () => loadDocuments();
$('document-search').oninput = renderDocuments;
$('close-document').onclick = () => $('document-dialog').close();
$('evolution-run').onclick = async () => {
  const button = $('evolution-run');
  try {
    button.disabled = true;
    const result = await api('/api/skills', { method: 'POST', body: JSON.stringify({ action: 'evolve', args: { name: $('evolution-name').value.trim(), baseVersion: $('evolution-base').value.trim(), patches: JSON.parse($('evolution-patches').value) } }) });
    $('evolution-result').textContent = JSON.stringify(result, null, 2);
    $('evolution-message').textContent = result.status === 'staged' ? '候选已通过门禁并进入 staged。' : '候选未通过门禁，请查看结果。';
  } catch (error) { $('evolution-message').textContent = error.message; }
  finally { button.disabled = false; }
};
let evolutionView = 'cases';
function renderEvolution(view, data) {
  const panel = $('evolution-panel');
  if (view === 'cases') {
    const rows = data.cases || [];
    panel.innerHTML = `<h2>评测集 <small>${rows.length} 条</small></h2>` + (rows.length ? `<table class="evolution-table"><thead><tr><th>ID</th><th>分段</th><th>用例</th></tr></thead><tbody>${rows.map(row => `<tr><td>${esc(row.case_id)}</td><td>${esc(row.split)}</td><td><code>${esc(row.payload)}</code></td></tr>`).join('')}</tbody></table>` : '<p class="evolution-empty">还没有评测用例。</p>');
  } else if (view === 'runs' || view === 'rollback') {
    const rows = (data.runs || []).filter(row => view === 'runs' || row.status === 'rejected' || row.status === 'rolled_back');
    panel.innerHTML = `<h2>${view === 'runs' ? '执行轨迹' : '回滚记录'} <small>${rows.length} 条</small></h2>` + (rows.length ? `<table class="evolution-table"><thead><tr><th>时间</th><th>技能</th><th>基础版本</th><th>候选版本</th><th>状态</th><th>运行 ID</th></tr></thead><tbody>${rows.map(row => `<tr><td>${esc(row.created_at)}</td><td>${esc(row.name)}</td><td>${esc(row.base_version)}</td><td>${esc(row.candidate_version || '-')}</td><td><span class="evolution-status ${esc(row.status)}">${esc(row.status)}</span></td><td><code>${esc(row.run_id)}</code></td></tr>`).join('')}</tbody></table>` : '<p class="evolution-empty">暂无记录。</p>');
  } else if (view === 'rollouts') {
    const rows = data.rollouts || [];
    panel.innerHTML = `<h2>灰度状态 <small>${rows.length} 个</small></h2>` + (rows.length ? `<table class="evolution-table"><thead><tr><th>项目</th><th>技能</th><th>候选版本</th><th>旧版本</th><th>比例</th><th>状态</th></tr></thead><tbody>${rows.map(row => `<tr><td>${esc(row.project)}</td><td>${esc(row.name)}</td><td>${esc(row.candidate_version)}</td><td>${esc(row.previous_version || '-')}</td><td>${esc(row.percentage)}%</td><td>${row.active ? '运行中' : '已回滚'}</td></tr>`).join('')}</tbody></table>` : '<p class="evolution-empty">暂无灰度发布。</p>');
  } else {
    const rows = data.metrics || [];
    panel.innerHTML = `<h2>指标曲线 <small>${rows.length} 条</small></h2>` + (rows.length ? `<div class="metric-bars">${rows.slice(0, 30).reverse().map(row => `<div class="metric-bar"><span>${esc(row.metric)} ${esc(row.value)}</span><i style="height:${Math.min(100, Math.max(4, Number(row.value) * 100))}%"></i></div>`).join('')}</div>` : '<p class="evolution-empty">暂无线上指标。</p>');
  }
}
async function loadEvolutionView() {
  try { const data = await api('/api/skill-evolution?view=all'); const merged = { cases: data.cases?.cases || [], runs: data.runs?.runs || [], rollouts: data.rollouts?.rollouts || [], metrics: data.metrics?.metrics || [] }; renderEvolution(evolutionView, merged); }
  catch (error) { $('evolution-panel').innerHTML = `<p class="evolution-empty">读取失败：${esc(error.message)}</p>`; }
}
$('evolution-tabs').querySelectorAll('[data-evolution-view]').forEach(button => button.onclick = () => { evolutionView = button.dataset.evolutionView; $('evolution-tabs').querySelectorAll('button').forEach(item => item.classList.toggle('active', item === button)); loadEvolutionView(); });
$('evolution-refresh').onclick = loadEvolutionView;

let skillCatalog = { skills: [], bindings: [] };
let skillFilter = 'all';
const skillVersions = new Map();
const skillNotes = {
  'frontend-design': { label: '界面设计', type: 'design', icon: 'M4 4h16v16H4z M4 9h16 M9 9v11', intro: '将页面需求转化为有辨识度的前端界面，提供布局、字体、配色与组件细节的设计指导。' },
  'webapp-testing': { label: '应用测试', type: 'testing', icon: 'm8 12 3 3 5-6 M4 4h16v16H4z', intro: '使用 Playwright 验证本地 Web 应用，研究浏览器交互、页面截图和常见功能测试流程。' },
  'mcp-builder': { label: '工具开发', type: 'tools', icon: 'm8 7-5 5 5 5 m8-10 5 5-5 5 m-3-14-2 18', intro: '指导构建 MCP 服务，将外部 API 与工具能力接入智能体，涵盖接口设计、实现与验证。' },
  'skill-creator': { label: '技能迭代', type: 'research', icon: 'M12 3v6 m0 6v6 M3 12h6 m6 0h6 M6 6l3 3 m6 6 3 3 M6 18l3-3 m6-6 3-3', intro: '从实际任务出发编写和改进技能，研究测试用例、评估与迭代方法，为自进化实验提供参考。' },
};
function skillGroups() {
  const groups = new Map();
  skillCatalog.skills.forEach(s => {
    if (!groups.has(s.name)) groups.set(s.name, []);
    groups.get(s.name).push(s);
  });
  return [...groups.values()];
}
function renderSkills() {
  const groups = skillGroups();
  const boundNames = new Set(skillCatalog.bindings.filter(b => b.project === 'projects/ai/dodo-agent').map(b => b.name));
  $('skill-count').textContent = `${groups.length} 个技能 · ${boundNames.size} 个已启用`;
  const query = $('skill-search').value.trim().toLowerCase();
  const visible = groups.filter(versions => {
    const s = versions[0], note = skillNotes[s.name];
    return (skillFilter !== 'enabled' || boundNames.has(s.name)) &&
      `${s.name} ${s.description} ${note?.label || ''} ${note?.intro || ''}`.toLowerCase().includes(query);
  });
  $('skill-list').innerHTML = visible.map(versions => {
    const name = versions[0].name;
    const binding = skillCatalog.bindings.find(b => b.name === name && b.project === 'projects/ai/dodo-agent');
    const s = versions.find(v => v.version === skillVersions.get(name)) || versions.find(v => v.version === binding?.version) || versions[0];
    const index = skillCatalog.skills.indexOf(s);
    const bound = binding?.version === s.version;
    const note = skillNotes[name] || { label: '自定义技能', type: 'custom', icon: 'M8 3H5v18h14V7l-4-4H8 M9 11h6 M9 15h6' };
    return `<article class="skill-card ${bound ? 'is-bound' : ''}">
      <div class="skill-card-top"><span class="skill-icon ${note.type}" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="${note.icon}"/></svg></span><span class="skill-binding ${bound ? 'is-bound' : ''}">${bound ? '已启用' : binding ? '当前版本未启用' : '未启用'}</span></div>
      <div class="skill-heading"><span class="skill-category">${esc(note.label)}</span><h2>${esc(name)}</h2></div>
      <p class="skill-intro">${esc(note.intro || s.description || '暂无技能介绍，可在编辑中填写 description。')}</p>
      <div class="skill-version-row"><label for="skill-version-${index}">版本 <span>${versions.length}</span></label><select id="skill-version-${index}" data-skill-version="${esc(name)}" aria-label="${esc(name)} 的版本">${versions.map((v, i) => `<option value="${esc(v.version)}" ${v.version === s.version ? 'selected' : ''}>${esc(v.version)}${i === 0 ? ' · 最新' : ''}${v.version === binding?.version ? ' · 已启用' : ''}</option>`).join('')}</select></div>
      <div class="skill-card-actions"><button class="action readme-button" data-edit-skill="${index}" aria-label="查看和编辑 ${esc(name)}">查看 / 编辑</button><button type="button" class="skill-switch" role="switch" aria-checked="${bound}" aria-label="启用 ${esc(name)} ${esc(s.version)}" data-toggle-skill="${index}"><span class="skill-switch-label">${bound ? '已启用' : '启用'}</span><span class="skill-switch-track" aria-hidden="true"><span></span></span></button></div>
    </article>`;
  }).join('') || `<div class="empty">${groups.length ? '没有匹配的技能' : '从第一个技能开始'}<br><small>${groups.length ? '试试其他关键词，或切换到全部技能。' : '点击“新建技能”，把常用流程保存为可复用的能力。'}</small></div>`;
  $('skill-list').querySelectorAll('[data-skill-version]').forEach(select => select.onchange = () => {
    skillVersions.set(select.dataset.skillVersion, select.value);
    renderSkills();
  });
  $('skill-list').querySelectorAll('[data-edit-skill]').forEach(b => b.onclick = () => openSkillEditor(skillCatalog.skills[Number(b.dataset.editSkill)]));
  $('skill-list').querySelectorAll('[data-toggle-skill]').forEach(b => b.onclick = async () => {
    const s = skillCatalog.skills[Number(b.dataset.toggleSkill)];
    const bound = skillCatalog.bindings.some(x => x.project === 'projects/ai/dodo-agent' && x.name === s.name && x.version === s.version);
    b.disabled = true;
    b.setAttribute('aria-busy', 'true');
    b.querySelector('.skill-switch-label').textContent = '处理中…';
    try {
      await api('/api/skills', { method: 'POST', body: JSON.stringify({ action: 'bind', args: { project: 'projects/ai/dodo-agent', name: s.name, version: bound ? null : s.version } }) });
      skillCatalog.bindings = skillCatalog.bindings.filter(x => !(x.project === 'projects/ai/dodo-agent' && x.name === s.name));
      if (!bound) skillCatalog.bindings.push({ project: 'projects/ai/dodo-agent', name: s.name, version: s.version });
      $('skill-message').textContent = bound ? `已停用 ${s.name} ${s.version}。` : `已启用 ${s.name} ${s.version}，下次技能请求生效。`;
      renderSkills();
    } catch (e) {
      $('skill-message').textContent = e.message;
      b.disabled = false;
      b.removeAttribute('aria-busy');
      b.querySelector('.skill-switch-label').textContent = bound ? '已启用' : '启用';
    }
  });
}
async function loadSkills() {
  $('skill-refresh').disabled = true;
  $('skill-list').setAttribute('aria-busy', 'true');
  try {
    skillCatalog = await api('/api/skills');
    renderSkills();
  } catch (e) { $('skill-message').textContent = `加载失败：${e.message}。请点击刷新重试。`; }
  finally {
    $('skill-refresh').disabled = false;
    $('skill-list').setAttribute('aria-busy', 'false');
  }
}
function openSkillEditor(skill) {
  $('skill-editor-title').textContent = skill ? `编辑 ${skill.name}` : '新建技能';
  $('skill-content').value = skill?.content || '---\nname: my-skill\ndescription: 描述这个技能能做什么、适用于什么任务。\n---\n写下执行步骤、所需资料和输出要求。';
  $('skill-resources').value = skill?.resources || '{}';
  $('skill-editor-message').textContent = '';
  $('skill-editor').showModal();
}
$('skill-new').onclick = () => openSkillEditor();
$('skill-editor-close').onclick = () => $('skill-editor').close();
$('skill-refresh').onclick = () => loadSkills();
$('skill-search').oninput = renderSkills;
$('skill-filters').querySelectorAll('[data-skill-filter]').forEach(button => button.onclick = () => {
  skillFilter = button.dataset.skillFilter;
  $('skill-filters').querySelectorAll('button').forEach(b => {
    b.classList.toggle('active', b === button);
    b.setAttribute('aria-pressed', String(b === button));
  });
  renderSkills();
});
$('skill-save').onclick = async () => {
  $('skill-save').disabled = true;
  $('skill-save').textContent = '保存中…';
  try {
    const result = await api('/api/skills', { method: 'POST', body: JSON.stringify({ action: 'save', args: {
      content: $('skill-content').value, resources: JSON.parse($('skill-resources').value || '{}'),
    } }) });
    skillVersions.set(result.name, result.version);
    $('skill-message').textContent = `已保存 ${result.name} / ${result.version}，可在卡片上启用此版本。`;
    $('skill-editor').close();
    await loadSkills();
  } catch (e) { $('skill-editor-message').textContent = e.message; }
  finally {
    $('skill-save').disabled = false;
    $('skill-save').textContent = '保存新版本';
  }
};

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
    const log = projectLogs.get(p.path) || '';
    return `<article class="card"><div class="card-top"><div style="min-width:0"><h2 title="${esc(p.name)}">${esc(p.name)}</h2><div class="path">${esc(p.path)}</div></div><span class="development-badge ${stage.key}" aria-label="开发状态：${stage.label}">${stage.label}</span></div>
      <p class="desc">${esc(p.description || '暂无描述')}</p><div class="meta"><span class="tag">${esc(categoryLabel[p.category] || p.category)}</span><span class="tag">${esc(p.mode || '未声明模式')}</span>${(p.language || []).map(l => `<span class="tag">${esc(l)}</span>`).join('')}</div>
      <div class="card-runtime"><span>运行状态</span><span class="status ${esc(p.state)}">${statusLabel(p.state)}</span></div>${link}<details class="card-logs" ${log ? 'open' : ''}><summary>应用日志 <span>${log ? '有输出' : '暂无输出'}</span></summary><pre data-log-id="${esc(p.path)}">${esc(log || '启动应用后，这里显示该应用自己的日志。')}</pre></details><div class="actions"><button class="action readme-button" data-readme="${esc(p.path)}" aria-label="查看 ${esc(p.name)} 的 Readme">Readme</button>
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
  eventSource.addEventListener('snapshot', event => { setProjectLog(id, JSON.parse(event.data).log || ''); });
  eventSource.addEventListener('output', event => {
    setProjectLog(id, (projectLogs.get(id) || '') + JSON.parse(event.data).value);
  });
  eventSource.addEventListener('ready', () => { show('项目已启动，点击卡片上的页面链接即可访问。'); refresh(); });
  eventSource.addEventListener('state', () => refresh());
  eventSource.onerror = () => { $('updated').textContent = '实时连接已断开，正在重连'; };
}
function setProjectLog(id, value) {
  projectLogs.set(id, value);
  const element = [...document.querySelectorAll('[data-log-id]')].find(item => item.dataset.logId === id);
  if (element) {
    element.textContent = value || '该项目暂无输出。';
    element.scrollTop = element.scrollHeight;
    const details = element.closest('details');
    if (details && value) details.open = true;
  }
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
      setProjectLog(selected, logs.log || '');
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
$('platform-nav').querySelectorAll('[data-section]').forEach(button => button.onclick = () => selectSection(button.dataset.section));
$('back-to-projects').onclick = () => selectSection('projects');
window.addEventListener('hashchange', () => selectSection(window.location.hash.slice(1), false));
selectSection(window.location.hash.slice(1) || 'projects');
refresh();
setInterval(refresh, 1800);
