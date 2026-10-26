let projectId = 'hotline-agent';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[c]));

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw Error(data.error || data.message || '请求失败，请重试');
  return data.data !== undefined ? data.data : data;
}

function selectSection(section, updateAddress = true) {
  if (section !== 'skills' && section !== 'evolution') section = 'skills';
  const hash = `#${section}`;
  if (updateAddress && window.location.hash !== hash) window.history.pushState(null, '', hash);
  $('skill-section').hidden = section !== 'skills';
  $('evolution-section').hidden = section !== 'evolution';
  $('platform-nav').querySelectorAll('[data-section]').forEach(button => {
    const active = button.dataset.section === section;
    button.classList.toggle('active', active);
    if (active) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
  if (section === 'skills') void loadSkills();
  else void loadEvolutionView();
}

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
  const boundNames = new Set(skillCatalog.bindings.filter(b => b.project === projectId).map(b => b.name));
  $('skill-count').textContent = `${groups.length} 个技能 · ${boundNames.size} 个已启用`;
  const query = $('skill-search').value.trim().toLowerCase();
  const visible = groups.filter(versions => {
    const s = versions[0], note = skillNotes[s.name];
    return (skillFilter !== 'enabled' || boundNames.has(s.name)) &&
      `${s.name} ${s.description} ${note?.label || ''} ${note?.intro || ''}`.toLowerCase().includes(query);
  });
  $('skill-list').innerHTML = visible.map(versions => {
    const name = versions[0].name;
    const binding = skillCatalog.bindings.find(b => b.name === name && b.project === projectId);
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
    const bound = skillCatalog.bindings.some(x => x.project === projectId && x.name === s.name && x.version === s.version);
    b.disabled = true;
    b.setAttribute('aria-busy', 'true');
    b.querySelector('.skill-switch-label').textContent = '处理中…';
    try {
      await api('/console/api/skills', { method: 'POST', body: JSON.stringify({ action: 'bind', args: { project: projectId, name: s.name, version: bound ? null : s.version } }) });
      skillCatalog.bindings = skillCatalog.bindings.filter(x => !(x.project === projectId && x.name === s.name));
      if (!bound) skillCatalog.bindings.push({ project: projectId, name: s.name, version: s.version });
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
    skillCatalog = await api('/console/api/skills');
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
    const result = await api('/console/api/skills', { method: 'POST', body: JSON.stringify({ action: 'save', args: {
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

$('evolution-run').onclick = async () => {
  const button = $('evolution-run');
  try {
    button.disabled = true;
    const result = await api('/console/api/skills', { method: 'POST', body: JSON.stringify({ action: 'evolve', args: { name: $('evolution-name').value.trim(), baseVersion: $('evolution-base').value.trim(), patches: JSON.parse($('evolution-patches').value) } }) });
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
  try {
    const data = await api('/console/api/skill-evolution?view=all');
    const merged = { cases: data.cases?.cases || [], runs: data.runs?.runs || [], rollouts: data.rollouts?.rollouts || [], metrics: data.metrics?.metrics || [] };
    renderEvolution(evolutionView, merged);
  } catch (error) { $('evolution-panel').innerHTML = `<p class="evolution-empty">读取失败：${esc(error.message)}</p>`; }
}
$('evolution-tabs').querySelectorAll('[data-evolution-view]').forEach(button => button.onclick = () => { evolutionView = button.dataset.evolutionView; $('evolution-tabs').querySelectorAll('button').forEach(item => item.classList.toggle('active', item === button)); loadEvolutionView(); });
$('evolution-refresh').onclick = loadEvolutionView;

$('platform-nav').querySelectorAll('[data-section]').forEach(button => button.onclick = () => selectSection(button.dataset.section));
window.addEventListener('hashchange', () => selectSection(window.location.hash.slice(1), false));
(async () => {
  try { projectId = (await api('/console/api/config')).project || projectId; } catch { /* keep default */ }
  selectSection(window.location.hash.slice(1) || 'skills', false);
})();

