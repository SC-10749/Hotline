<script setup>
import { computed, ref } from 'vue'
import {
  ArrowDownToLine, ArrowRight, BookOpen, Check, CheckCircle2, CircleAlert,
  Clock3, Code2, Database, FileCode2, FileText, Folder, GitBranch, HardDrive,
  History, Layers3, LockKeyhole, Plus, Search, Shield, ShieldCheck, Upload, X,
} from 'lucide-vue-next'

const workspaces = ref([
  { id: 'ws-core', name: 'hotline-core', kind: 'repo', policy: 'workspace', files: 482, size: '1.8 GB', path: './workspaces/hotline-core', changes: 7, branch: 'main', status: 'active', root: true, parent: null },
  { id: 'ws-python', name: 'python_backend', kind: 'local_dir', policy: 'readonly', files: 216, size: '640 MB', path: './workspaces/hotline-core/python_backend', changes: 0, branch: 'main', status: 'active', root: false, parent: 'ws-core' },
  { id: 'ws-frontend', name: 'frontend', kind: 'repo', policy: 'workspace', files: 318, size: '920 MB', path: './workspaces/hotline-core/frontend', changes: 3, branch: 'feature/ui', status: 'active', root: false, parent: 'ws-core' },
  { id: 'ws-eval', name: 'model-eval', kind: 'local_dir', policy: 'full', files: 96, size: '4.1 GB', path: './workspaces/model-eval', changes: 0, branch: '—', status: 'active', root: false, parent: null },
  { id: 'ws-docs', name: 'hotline-docs', kind: 'local_dir', policy: 'workspace', files: 188, size: '220 MB', path: './workspaces/hotline-docs', changes: 0, branch: 'main', status: 'active', root: false, parent: null },
  { id: 'ws-legacy', name: 'gw-legacy', kind: 'repo', policy: 'readonly', files: 4, size: '52 MB', path: './archive/gw-legacy', changes: 0, branch: 'main', status: 'archived', root: false, parent: null },
])

const tabOptions = [
  { id: 'boundary', label: '边界与沙箱', icon: ShieldCheck },
  { id: 'files', label: '文件', icon: FileText },
  { id: 'changes', label: '变更', icon: GitBranch },
  { id: 'snapshots', label: '快照', icon: History },
  { id: 'context', label: '上下文绑定', icon: Layers3 },
  { id: 'secrets', label: '密钥', icon: LockKeyhole },
]
const policies = [
  { id: 'readonly', label: '只读', code: 'RO', note: '仅读取工作区内容，写入拒绝' },
  { id: 'workspace', label: '工作区写', code: 'WRITE', note: '可写工作区内，.git 强制只读' },
  { id: 'full', label: '完全访问', code: 'FULL', note: '越界操作需审批并记录' },
]
const search = ref('')
const filter = ref('all')
const selectedId = ref('ws-core')
const activeTab = ref('boundary')
const toast = ref('')
const pathInput = ref('src/main.py')
const pathOperation = ref('read')
const pathResult = ref(null)
const selectedFile = ref('python_backend/modules/workspaces/guard.py')
const selectedBranch = ref('main')
const showDiff = ref('python_backend/modules/workspaces/guard.py')
const stagedChanges = ref(new Set())
const contextEnabled = ref({ 'code-review': true, 'test-gen': true, 'doc-write': true, 'migrate-check': false, filesystem: true, github: true, postgres: false })
const snapshots = ref([
  { id: 'snap_41d2', reason: '运行前自动', run: 'run_a83f', commit: 'a92d7e1', size: '1.82 GB', age: '12 分钟前', status: '可用' },
  { id: 'snap_7b90', reason: '失败前 checkpoint', run: 'run_19c2', commit: 'f30a6b4', size: '1.81 GB', age: '1 小时前', status: '可用' },
  { id: 'snap_c5e1', reason: '运行前自动', run: 'run_c610', commit: 'b7f8490', size: '1.80 GB', age: '3 小时前', status: '可用' },
  { id: 'snap_09af', reason: '手动 · 迁移前', run: '—', commit: '8da3102', size: '1.79 GB', age: '昨天', status: '可用' },
  { id: 'snap_52bc', reason: '运行后归档', run: 'run_501e', commit: 'd039aa6', size: '1.78 GB', age: '昨天', status: '已过期' },
])
const secretRefs = ref([
  { name: 'SCM_TOKEN', ref: 'ref://vault/demo/source-control', inject: '工具进程', scope: 'source-control only', rotation: '90 天', enabled: true },
  { name: 'MODEL_API_KEY', ref: 'ref://env/MODEL_API_KEY', inject: '运行时', scope: '模型调用', rotation: '按平台', enabled: true },
  { name: 'DATABASE_PASSWORD', ref: 'ref://vault/demo/database', inject: 'secret_file', scope: 'database connector', rotation: '30 天', enabled: false },
])
const fileTree = [
  { name: '.git', type: 'protected', depth: 0 },
  { name: 'AGENTS.md', type: 'md', depth: 0, size: '4.2 KB' },
  { name: 'python_backend', type: 'folder', depth: 0 },
  { name: 'modules', type: 'folder', depth: 1 },
  { name: 'workspaces', type: 'folder', depth: 2 },
  { name: 'guard.py', type: 'py', depth: 3, size: '6.1 KB' },
  { name: 'snapshots.py', type: 'py', depth: 3, size: '3.8 KB' },
  { name: 'frontend', type: 'folder', depth: 0 },
  { name: 'src', type: 'folder', depth: 1 },
  { name: 'artifacts', type: 'folder', depth: 0 },
  { name: 'workspace-notes.md', type: 'md', depth: 1, size: '2.4 KB' },
]
const changes = ref([
  { id: 'c1', status: 'M', path: 'python_backend/modules/workspaces/guard.py', delta: '+42 −8' },
  { id: 'c2', status: 'M', path: 'python_backend/modules/workspaces/service.py', delta: '+16 −3' },
  { id: 'c3', status: 'A', path: 'python_backend/modules/workspaces/test_guard.py', delta: '新增' },
  { id: 'c4', status: 'M', path: 'artifacts/summary.md', delta: '+9 −0' },
  { id: 'c5', status: 'D', path: 'docs/old-workspace-notes.md', delta: '删除' },
  { id: 'c6', status: '?', path: 'notes.local.tmp', delta: '未跟踪' },
])

const selected = computed(() => workspaces.value.find((item) => item.id === selectedId.value) || workspaces.value[0])
const visibleWorkspaces = computed(() => workspaces.value.filter((item) => (filter.value === 'all' || item.status === filter.value) && `${item.name} ${item.path}`.toLowerCase().includes(search.value.toLowerCase())))
const activeCount = computed(() => workspaces.value.filter((item) => item.status === 'active').length)
const activePolicy = computed(() => policies.find((item) => item.id === selected.value.policy) || policies[1])
const boundRuns = computed(() => selected.value.id === 'ws-core' ? ['run_a83f · 策略冻结 · 工作区写', 'run_19c2 · 策略冻结 · 工作区写', 'run_c610 · 策略冻结 · 工作区写'] : selected.value.status === 'archived' ? [] : ['run_87b1 · 策略冻结 · 只读'])
const stagedCount = computed(() => stagedChanges.value.size)
const usedContext = computed(() => Object.values(contextEnabled.value).filter(Boolean).length)

function notify(message) {
  toast.value = message
  window.clearTimeout(notify.timer)
  notify.timer = window.setTimeout(() => { toast.value = '' }, 2400)
}

function createWorkspace() {
  const number = workspaces.value.length + 1
  const id = `ws-demo-${number}`
  workspaces.value.unshift({ id, name: `workspace-${number}`, kind: 'local_dir', policy: 'workspace', files: 0, size: '0 B', path: `./workspaces/workspace-${number}`, changes: 0, branch: '—', status: 'active', root: false, parent: null })
  selectedId.value = id
  filter.value = 'all'
  activeTab.value = 'boundary'
  notify('已添加本地演示工作区，未创建磁盘目录')
}

function setPolicy(policy) {
  if (selected.value.root && policy === 'full') {
    notify('根工作区不在演示中开放完全访问')
    return
  }
  selected.value.policy = policy
  notify(`策略已切换为${policies.find((item) => item.id === policy)?.label}（仅当前演示）`)
}

function testPath() {
  const rawPath = pathInput.value.trim().replaceAll('\\', '/')
  const parts = []
  let escapes = false
  const absolute = rawPath.startsWith('/') || /^[a-z]:/i.test(rawPath)
  for (const part of rawPath.split('/')) {
    if (!part || part === '.') continue
    if (part === '..') {
      if (!parts.length) escapes = true
      else parts.pop()
    } else parts.push(part)
  }
  const protectedPath = parts.includes('.git')
  const dependencies = parts.includes('node_modules')
  let code = '200'
  let title = '允许 · 位于工作区内'
  let detail = `${selected.value.path}/${parts.join('/') || '.'}`
  if (!rawPath) {
    code = '400'; title = '路径为空'; detail = '请输入工作区相对路径。'
  } else if ((absolute || escapes) && selected.value.policy !== 'full') {
    code = '400'; title = '拒绝 · 路径越界'; detail = '路径必须归属所选工作区。'
  } else if (absolute || escapes) {
    code = 'approval'; title = '需要审批 · 工作区外访问'; detail = '完全访问模式下，越界路径仍需审批。'
  } else if (pathOperation.value !== 'read' && selected.value.policy === 'readonly') {
    code = '403'; title = '拒绝 · 工作区只读'; detail = '当前工作区策略不允许写入或删除。'
  } else if (pathOperation.value !== 'read' && protectedPath) {
    code = '403'; title = '拒绝 · 受保护路径'; detail = '.git 内容在工作区写策略下强制只读。'
  } else if (pathOperation.value !== 'read' && dependencies && selected.value.policy !== 'full') {
    code = '403'; title = '拒绝 · 依赖目录受保护'; detail = 'node_modules 写入需要完全访问策略。'
  } else if (pathOperation.value !== 'read' && parts.some((part) => part.startsWith('.env'))) {
    code = 'approval'; title = '需要审批 · 配置文件'; detail = '演示规则要求对环境配置文件写入进行审批。'
  }
  pathResult.value = { code, title, detail, allowed: code === '200' }
}

function toggleStage(change) {
  const next = new Set(stagedChanges.value)
  if (next.has(change.id)) next.delete(change.id)
  else next.add(change.id)
  stagedChanges.value = next
}

function addSnapshot() {
  snapshots.value.unshift({ id: `snap_${Math.random().toString(16).slice(2, 6)}`, reason: '手动 · 本地演示', run: '—', commit: '未关联', size: selected.value.size, age: '刚刚', status: '演示' })
  notify('已添加演示快照记录，未写入磁盘')
}

function iconForFile(type) {
  if (type === 'folder') return Folder
  if (type === 'protected') return LockKeyhole
  if (type === 'py') return FileCode2
  return FileText
}
</script>

<template>
  <section class="workspace-boundary-page" aria-label="工作空间边界管理">
    <header class="ws-header">
      <div class="ws-title-lockup"><span class="ws-mark">W</span><div><h1>工作空间</h1><p>Workspace · 归属与边界</p></div></div>
      <div class="ws-root-pill"><small>ROOT</small><code>{{ selected.root ? selected.path : './workspaces/hotline-core' }}</code><span class="ws-root-unique"><Check :size="12" />唯一</span></div>
      <div class="ws-header-actions"><label class="ws-policy-select"><span>沙箱策略</span><select :value="selected.policy" aria-label="当前工作区沙箱策略" @change="setPolicy($event.target.value)"><option v-for="policy in policies" :key="policy.id" :value="policy.id">{{ policy.label }}</option></select></label><button class="ws-primary" type="button" @click="createWorkspace"><Plus :size="16" />新建工作空间</button></div>
    </header>

    <div class="ws-metrics">
      <div class="ws-metric"><span><i class="mint"></i>工作空间</span><strong>{{ activeCount }} <small>/ {{ workspaces.length }}</small></strong><em>{{ activeCount }} 活跃 · {{ workspaces.length - activeCount }} 已归档</em></div>
      <div class="ws-metric"><span><i class="blue"></i>文件与容量</span><strong>1,304 <small>文件</small></strong><em>7.7 GB · 配额 10 GB</em></div>
      <div class="ws-metric"><span><i class="coral"></i>越界拦截 · 今日</span><strong>7 <small>次</small></strong><em>400 / 403 双码 · 0 逃逸</em></div>
      <div class="ws-metric"><span><i class="violet"></i>绑定运行</span><strong>5 <small>个 run</small></strong><em>策略随 run 冻结 · 不支持热改</em></div>
    </div>

    <div class="ws-workbench">
      <aside class="ws-list-panel">
        <div class="ws-panel-heading"><h2>工作空间 <small>{{ activeCount }}</small></h2><span>repo {{ workspaces.filter(item => item.kind === 'repo').length }} · dir {{ workspaces.filter(item => item.kind === 'local_dir').length }}</span></div>
        <label class="ws-search"><Search :size="14" /><input v-model="search" placeholder="搜索名称 / 路径 / 父级" /></label>
        <div class="ws-filters"><button v-for="item in [['all','全部',workspaces.length],['active','活跃',activeCount],['archived','已归档',workspaces.length-activeCount]]" :key="item[0]" type="button" :class="{ active: filter === item[0] }" @click="filter = item[0]"><span>{{ item[1] }}</span><b>{{ item[2] }}</b></button></div>
        <div class="ws-list">
          <button v-for="item in visibleWorkspaces" :key="item.id" class="ws-item" :class="{ selected: item.id === selectedId, archived: item.status === 'archived', child: item.parent }" type="button" @click="selectedId = item.id; activeTab = 'boundary'; selectedFile = 'python_backend/modules/workspaces/guard.py'">
            <span class="ws-item-title"><i :class="item.status"></i><strong>{{ item.name }}</strong><em v-if="item.status === 'archived'">已归档</em><em v-else>{{ item.kind === 'repo' ? 'repo' : 'local_dir' }}</em><b class="policy-code" :class="item.policy">{{ policies.find(policy => policy.id === item.policy)?.code }}</b></span>
            <span class="ws-item-meta">{{ item.files }} 文件 · {{ item.size }}</span><span class="ws-item-path">{{ item.path }}</span><span v-if="item.changes" class="ws-item-changes">{{ item.changes }} 变更</span>
          </button>
          <p v-if="!visibleWorkspaces.length" class="ws-empty">没有匹配的工作空间</p>
        </div>
        <div class="ws-quota"><span>容量占用 · 全工作空间</span><strong>7.7 <small>/ 10 GB</small></strong><div class="ws-quota-track"><i></i></div></div>
      </aside>

      <main class="ws-detail-panel">
        <header class="ws-detail-heading"><div><h2>{{ selected.name }} <span class="kind-tag">{{ selected.kind }}</span><span class="policy-code" :class="selected.policy">{{ activePolicy.code }}</span></h2><p>{{ selected.files }} 文件 · {{ selected.size }} · {{ selected.branch }}</p></div><span class="ws-updated"><Clock3 :size="12" />更新 2 分钟前</span></header>
        <nav class="ws-tabs" aria-label="工作空间详情视图"><button v-for="tab in tabOptions" :key="tab.id" type="button" :class="{ active: activeTab === tab.id }" @click="activeTab = tab.id"><component :is="tab.icon" :size="14" />{{ tab.label }}<b v-if="tab.id === 'boundary'">P0</b></button></nav>

        <div v-if="activeTab === 'boundary'" class="ws-tab-body">
          <section class="ws-path-test">
            <div class="ws-section-head"><div><h3><Code2 :size="15" />路径边界试跑</h3><p>本地演示校验 · 不执行真实文件读写</p></div><span class="ws-engine-tag">resolve within root</span></div>
            <div class="ws-path-controls"><label><span>相对路径</span><input v-model="pathInput" @keydown.enter="testPath" /></label><div class="ws-op-control" aria-label="文件操作"><button v-for="op in [['read','读'],['write','写'],['delete','删']]" :key="op[0]" type="button" :class="{ active: pathOperation === op[0] }" @click="pathOperation = op[0]">{{ op[1] }}</button></div><button class="ws-test-button" type="button" @click="testPath">试跑</button></div>
            <div class="ws-path-examples"><button v-for="example in ['src/main.py','../outside/file','.git/config','node_modules/.bin/tool']" :key="example" type="button" @click="pathInput = example; testPath()">{{ example }}</button></div>
            <div v-if="pathResult" class="ws-path-result" :class="{ denied: !pathResult.allowed, approval: pathResult.code === 'approval' }"><component :is="pathResult.allowed ? CheckCircle2 : pathResult.code === 'approval' ? CircleAlert : X" :size="16" /><div><strong>{{ pathResult.code }} · {{ pathResult.title }}</strong><span>{{ pathResult.detail }}</span></div><small>仅演示</small></div>
            <div v-else class="ws-path-result idle"><ShieldCheck :size="16" /><div><strong>选择路径并试跑边界规则</strong><span>读写操作按所选工作区策略进行本地判断。</span></div></div>
          </section>

          <section class="ws-subsection"><div class="ws-section-head"><div><h3>沙箱策略矩阵</h3><p>当前：{{ activePolicy.label }}</p></div><span class="ws-priority">运行创建时冻结</span></div><div class="ws-matrix"><div class="ws-matrix-row ws-matrix-head"><span>路径区域</span><span>只读</span><span>工作区写</span><span>完全访问</span></div><div class="ws-matrix-row"><span><code>.git/**</code></span><span>读</span><b>强制只读</b><em>需审批</em></div><div class="ws-matrix-row"><span><code>node_modules/**</code></span><span>读</span><em>拒绝</em><b>允许</b></div><div class="ws-matrix-row"><span>工作区内源码 / 产物</span><span>读</span><b>读写</b><b>读写</b></div><div class="ws-matrix-row"><span>工作区外路径</span><em>400</em><em>400</em><b>审批后处理</b></div></div></section>

          <section class="ws-subsection"><div class="ws-section-head"><div><h3>写入闸门顺序</h3><p>每一步都在文件写入前完成</p></div></div><div class="ws-gate-steps"><div><b>01</b><strong>路径归一化</strong><span>解析 .. 与符号链接</span></div><ArrowRight :size="14" /><div><b>02</b><strong>归属校验</strong><span>目标必须位于 root 内</span></div><ArrowRight :size="14" /><div><b>03</b><strong>保护规则</strong><span>.git 与 denylist</span></div><ArrowRight :size="14" /><div><b>04</b><strong>内容扫描</strong><span>命中规则时阻断</span></div></div></section>
        </div>

        <div v-else-if="activeTab === 'files'" class="ws-tab-body">
          <div class="ws-file-toolbar"><div><h3>工作区文件</h3><p>文件视图为演示目录，不读取本机文件</p></div><div><button type="button" @click="notify('文件上传接口尚未接入')"><Upload :size="14" />上传</button><button type="button" @click="notify('演示文件已准备下载')"><ArrowDownToLine :size="14" />下载</button></div></div>
          <div class="ws-file-browser"><nav class="ws-file-tree" aria-label="文件树"><button v-for="file in fileTree" :key="file.name" type="button" :class="{ active: selectedFile.endsWith(file.name), protected: file.type === 'protected' }" :style="{ '--depth': file.depth }" @click="selectedFile = file.name"><component :is="iconForFile(file.type)" :size="14" /><span>{{ file.name }}</span><small v-if="file.size">{{ file.size }}</small><small v-else-if="file.type === 'protected'">RO</small></button></nav><div class="ws-file-preview"><header><FileCode2 :size="14" />{{ selectedFile }}<button type="button" title="下载当前文件" aria-label="下载当前文件" @click="notify('演示文件已准备下载')"><ArrowDownToLine :size="14" /></button></header><pre><code><span>01</span>  <b># Workspace boundary · demo preview</b>
<span>02</span>
<span>03</span>  <i>POLICY_READONLY</i> = <em>"readonly"</em>
<span>04</span>  <i>POLICY_WORKSPACE</i> = <em>"workspace"</em>
<span>05</span>  <i>POLICY_FULL</i> = <em>"full"</em>
<span>06</span>
<span>07</span>  <strong>def</strong> <b>resolve_within_root</b>(root, relative_path):
<span>08</span>      target = (root / relative_path).resolve()
<span>09</span>      <strong>if not</strong> target.is_relative_to(root):
<span>10</span>          <strong>raise</strong> PathOutsideWorkspace()
<span>11</span>      <strong>return</strong> target</code></pre></div></div>
          <section class="ws-subsection"><div class="ws-section-head"><div><h3>最近写入</h3><p>来源与路径一并保留</p></div><span class="ws-engine-tag">演示事件</span></div><div class="ws-table"><div class="ws-table-row ws-table-head"><span>时间</span><span>写入方</span><span>路径</span><span>大小</span><span>事件</span></div><div v-for="row in [['14:23','codegen-agent','python_backend/modules/workspaces/test_guard.py','5.8 KB','编辑器'],['14:21','codegen-agent','python_backend/modules/workspaces/guard.py','6.1 KB','编辑器'],['14:18','research-agent','artifacts/summary.md','2.4 KB','Agent 工具']]" :key="row.join('-')" class="ws-table-row"><span>{{ row[0] }}</span><span>{{ row[1] }}</span><span>{{ row[2] }}</span><span>{{ row[3] }}</span><span>{{ row[4] }}</span></div></div></section>
        </div>

        <div v-else-if="activeTab === 'changes'" class="ws-tab-body">
          <div class="ws-branch-bar"><div><GitBranch :size="15" /><span>当前分支</span><select v-model="selectedBranch" aria-label="当前分支"><option>main</option><option>feature/workspace-boundary</option><option>release/v1.8</option></select><em>领先 origin 2 个提交</em></div><button type="button" @click="notify('分支操作为本地演示，尚未连接 Git')"><Plus :size="14" />切换 / 新建分支</button></div>
          <div class="ws-change-layout"><section class="ws-change-list"><div class="ws-section-head"><div><h3>工作区变更 <small>{{ changes.length }}</small></h3><p>暂存状态仅保存在本地演示界面</p></div><button type="button" @click="stagedChanges = new Set(changes.map(change => change.id))">全部暂存</button></div><div v-for="change in changes" :key="change.id" class="ws-change-row"><button type="button" class="ws-stage" :class="{ staged: stagedChanges.has(change.id) }" :aria-label="stagedChanges.has(change.id) ? '取消暂存' : '暂存变更'" @click="toggleStage(change)"><Check v-if="stagedChanges.has(change.id)" :size="12" /><Plus v-else :size="12" /></button><span class="ws-change-status" :class="change.status.toLowerCase()">{{ change.status }}</span><button type="button" class="ws-change-file" @click="showDiff = change.path"><strong>{{ change.path }}</strong><small>{{ change.delta }}</small></button></div><div class="ws-change-actions"><button type="button" @click="notify('提交功能尚未接入 Git')"><GitBranch :size="14" />提交 {{ stagedCount }} 项</button><button type="button" @click="notify('补丁操作尚未接入执行服务')">查看补丁</button></div></section><section class="ws-diff-panel"><div class="ws-section-head"><div><h3>变更预览</h3><p>{{ showDiff }}</p></div><span class="ws-engine-tag">只读预览</span></div><pre><code><span>@@ -112,7 +112,11 @@</span>
  <del>- target = root / relative_path</del>
  <ins>+ target = resolve_within_root(root, relative_path)</ins>
  <span>  # 所有文件操作使用归一化后的目标路径</span>
<span></span>
<del>- return write_file(target, content)</del>
<ins>+ validate_policy(target, operation)</ins>
<ins>+ scan_content_before_write(content)</ins></code></pre></section></div>
          <section class="ws-subsection"><div class="ws-section-head"><div><h3>最近提交</h3><p>本地演示记录</p></div></div><div class="ws-commit-list"><div v-for="row in [['a92d7e1','feat(workspaces): add boundary preview','agent/ops','12 分钟前'],['f30a6b4','feat(execution): freeze sandbox policy','agent/ops','1 小时前'],['b7f8490','test: reject paths outside workspace','qa-agent','3 小时前']]" :key="row[0]"><code>{{ row[0] }}</code><strong>{{ row[1] }}</strong><span>{{ row[2] }}</span><small>{{ row[3] }}</small></div></div></section>
        </div>

        <div v-else-if="activeTab === 'snapshots'" class="ws-tab-body">
          <div class="ws-snapshot-heading"><div><h3>工作区快照</h3><p>run 启动前的状态记录 · 不实际恢复文件</p></div><button class="ws-primary" type="button" @click="addSnapshot"><Plus :size="14" />创建演示快照</button></div>
          <div class="ws-table ws-snapshots"><div class="ws-table-row ws-table-head"><span>快照</span><span>触发原因</span><span>运行</span><span>Commit</span><span>大小</span><span>时间</span><span>状态</span><span></span></div><div v-for="snapshot in snapshots" :key="snapshot.id" class="ws-table-row"><strong>{{ snapshot.id }}</strong><span>{{ snapshot.reason }}</span><span>{{ snapshot.run }}</span><code>{{ snapshot.commit }}</code><span>{{ snapshot.size }}</span><span>{{ snapshot.age }}</span><em :class="{ expired: snapshot.status === '已过期' }">{{ snapshot.status }}</em><button type="button" :disabled="snapshot.status === '已过期'" @click="notify('快照恢复尚未接入，未修改工作区文件')">恢复</button></div></div>
          <div class="ws-snapshot-policy"><div><strong>自动快照策略</strong><span>运行前自动 · 每次 run 启动前</span></div><div><strong>失败 checkpoint</strong><span>失败运行保留恢复点</span></div><div><strong>保留策略</strong><span>最近 10 个 · 超期标记</span></div><div><strong>快照占用</strong><span>5.4 GB · 配额 20 GB</span></div></div>
          <div class="ws-info-note"><ShieldCheck :size="16" /><span>快照恢复会覆盖整个工作区状态。后端接入前，恢复按钮仅展示操作路径，不执行写入。</span></div>
        </div>

        <div v-else-if="activeTab === 'context'" class="ws-tab-body">
          <div class="ws-context-intro"><BookOpen :size="16" /><div><strong>上下文绑定</strong><p>绑定变更只影响新建 run；运行中的上下文快照保持不变。</p></div><span>{{ usedContext }} 项已启用</span></div>
          <section class="ws-subsection"><div class="ws-section-head"><div><h3>AGENTS.md 继承链</h3><p>工作空间规则优先，父级规则补充</p></div><span class="ws-engine-tag">3 层</span></div><div class="ws-inherit-list"><div><span>工作空间</span><code>./workspaces/hotline-core/AGENTS.md</code><b>优先</b></div><div><span>父级目录</span><code>./workspaces/AGENTS.md</code><b>补充</b></div><div><span>全局</span><code>./AGENTS.md</code><b>补充</b></div></div></section>
          <div class="ws-binding-grid"><section class="ws-binding-group"><div class="ws-section-head"><div><h3>Skills</h3><p>3 / 4 启用</p></div></div><label v-for="name in ['code-review','test-gen','doc-write','migrate-check']" :key="name" class="ws-toggle-row"><span><Sparkles :size="14" /><strong>{{ name }}</strong></span><input v-model="contextEnabled[name]" type="checkbox" /><i></i></label></section><section class="ws-binding-group"><div class="ws-section-head"><div><h3>MCP 与检索</h3><p>2 / 3 启用</p></div></div><label v-for="row in [['filesystem','工作区只读'],['github','仓库范围'],['postgres','只读视图']]" :key="row[0]" class="ws-toggle-row"><span><Database :size="14" /><strong>{{ row[0] }}</strong><small>{{ row[1] }}</small></span><input v-model="contextEnabled[row[0]]" type="checkbox" /><i></i></label></section></div>
          <section class="ws-subsection"><div class="ws-section-head"><div><h3>环境变量白名单</h3><p>仅允许显式列出的变量进入运行环境</p></div><span class="ws-engine-tag">4 项</span></div><div class="ws-env-list"><code>LOG_LEVEL</code><code>PYTHONPATH</code><code>TZ</code><code>NODE_ENV</code><button type="button" @click="notify('白名单编辑暂未接入配置 API')"><Plus :size="13" />添加变量</button></div><div class="ws-budget"><div><span>上下文预算</span><strong>24.7k / 32k token</strong></div><div class="ws-budget-track"><i></i></div><small>AGENTS.md 1.2k · Skills 3.4k · MCP Schema 8.1k · 检索 12k</small></div></section>
          <div class="ws-info-note"><Shield :size="16" /><span>未解析的绑定冲突会在 run 创建前提示；演示数据不会启动或修改真实运行。</span></div>
        </div>

        <div v-else class="ws-tab-body">
          <div class="ws-secret-intro"><LockKeyhole :size="18" /><div><strong>只存引用，不存密钥值</strong><p>演示目录只显示 secret 引用与注入范围。真实凭据不得保存在工作空间或可提交文件中。</p></div></div>
          <div class="ws-table ws-secret-table"><div class="ws-table-row ws-table-head"><span>名称</span><span>引用</span><span>注入</span><span>作用域</span><span>轮换</span><span>状态</span></div><div v-for="secret in secretRefs" :key="secret.name" class="ws-table-row"><strong>{{ secret.name }}</strong><code>{{ secret.ref }}</code><span>{{ secret.inject }}</span><span>{{ secret.scope }}</span><span>{{ secret.rotation }}</span><label class="ws-secret-toggle"><input v-model="secret.enabled" type="checkbox" /><i></i></label></div></div>
          <section class="ws-secret-rules"><h3>注入约束</h3><div><CheckCircle2 :size="15" /><span>仅存储引用<small>明文值不进入演示配置或 prompt</small></span></div><div><CheckCircle2 :size="15" /><span>最小权限作用域<small>按工具或运行需求声明</small></span></div><div><CheckCircle2 :size="15" /><span>写入前扫描<small>密钥泄露检测需由后端实现</small></span></div><button type="button" @click="notify('仅支持添加引用，密钥库接口尚未接入')"><Plus :size="14" />添加密钥引用</button></section>
          <div class="ws-info-note"><ShieldCheck :size="16" /><span>当前页面没有读取、存储或展示任何真实密钥。</span></div>
        </div>
      </main>

      <aside class="ws-boundary-panel">
        <header class="ws-boundary-head"><h2>边界控制</h2><span>P0</span></header>
        <div class="ws-boundary-body">
          <section class="ws-control-section"><div class="ws-side-title"><h3>沙箱策略</h3><span>与新建 run 绑定</span></div><label v-for="policy in policies" :key="policy.id" class="ws-policy-option" :class="{ active: selected.policy === policy.id, disabled: selected.root && policy.id === 'full' }"><input type="radio" name="workspace-policy" :value="policy.id" :checked="selected.policy === policy.id" :disabled="selected.root && policy.id === 'full'" @change="setPolicy(policy.id)" /><span><strong>{{ policy.label }}</strong><b class="policy-code" :class="policy.id">{{ policy.code }}</b><small>{{ policy.note }}</small></span></label><p class="ws-side-note">策略在 run 创建时冻结；运行中的任务沿用已保存快照。</p></section>
          <section class="ws-control-section"><div class="ws-side-title"><h3>路径归属校验</h3><span>root_path</span></div><div class="ws-validation-list"><div><CheckCircle2 :size="14" /><span>目录可访问<small>演示状态 · 待接后端校验</small></span></div><div><CheckCircle2 :size="14" /><span>root 唯一<small>6 / 6 通过</small></span></div><div><CheckCircle2 :size="14" /><span>路径不重叠<small>子工作区需显式声明父级</small></span></div></div></section>
          <section class="ws-control-section"><div class="ws-side-title"><h3>绑定运行</h3><span>{{ boundRuns.length }} 个</span></div><div v-for="run in boundRuns" :key="run" class="ws-run-binding"><span class="ws-run-dot"></span><span>{{ run }}</span></div><div v-if="!boundRuns.length" class="ws-no-runs">暂无绑定中的运行</div><div class="ws-storage-foot"><span>本工作空间</span><strong>{{ selected.size }}</strong><small>占全局用量示例 · 7.7 / 10 GB</small></div></section>
          <section class="ws-control-section ws-gate-status"><div class="ws-side-title"><h3>写入闸门</h3><span class="ws-live"><i></i>演示策略</span></div><div><CheckCircle2 :size="14" /><span>路径归一化<small>resolve before IO</small></span><b>ON</b></div><div><CheckCircle2 :size="14" /><span>.git 强制只读<small>写入返回 403</small></span><b>ON</b></div><div><CheckCircle2 :size="14" /><span>密钥值扫描<small>后端能力待接入</small></span><b class="pending">待接入</b></div><div class="ws-deny-summary"><strong>今日拦截 · 7 次</strong><span>越界 3 · 受保护路径 2 · 只读策略 1 · denylist 1</span></div></section>
        </div>
      </aside>
    </div>

    <footer class="ws-footer"><div><ShieldCheck :size="15" /><span><strong>工作空间只管理路径归属与策略声明</strong><small>运行隔离由 execution 模块负责 · 多人协同、在线 IDE 与 Git 托管不属于此模块</small></span></div><span><HardDrive :size="14" /> 本地演示数据 · 未执行真实文件操作</span></footer>
    <Transition name="toast"><div v-if="toast" class="ws-toast" role="status"><CheckCircle2 :size="15" />{{ toast }}</div></Transition>
  </section>
</template>

<style scoped>
.workspace-boundary-page { --ws-text: #29372f; --ws-secondary: #617068; --ws-muted: #859189; --ws-line: #dfe6df; --ws-line-soft: #edf1ed; --ws-surface: #fff; --ws-subtle: #f7f9f7; --ws-canvas: #f5f7f4; --ws-accent: #bd6047; --ws-accent-soft: #fff3ee; --ws-green: #40885b; min-width: 0; color: var(--ws-text); }
.ws-header { display: flex; min-height: 54px; align-items: center; gap: 16px; margin-bottom: 13px; }
.ws-title-lockup { display: flex; min-width: 180px; align-items: center; gap: 10px; }.ws-mark { display: grid; width: 34px; height: 34px; place-items: center; border-radius: 8px; color: #fff; background: var(--ws-accent); font-size: 15px; font-weight: 700; }.ws-title-lockup h1 { margin: 0; font-size: 18px; font-weight: 700; }.ws-title-lockup p { margin: 2px 0 0; color: var(--ws-muted); font-size: 10px; }
.ws-root-pill { display: flex; min-width: 0; align-items: center; gap: 8px; padding: 7px 9px; border: 1px solid var(--ws-line); border-radius: 6px; background: var(--ws-surface); }.ws-root-pill > small { color: var(--ws-muted); font-size: 8px; font-weight: 700; }.ws-root-pill code { overflow: hidden; color: var(--ws-secondary); font: 10px Consolas, monospace; text-overflow: ellipsis; white-space: nowrap; }.ws-root-unique { display: inline-flex; align-items: center; gap: 3px; color: var(--ws-green); font-size: 9px; white-space: nowrap; }
.ws-header-actions { display: flex; align-items: center; gap: 8px; margin-left: auto; }.ws-policy-select { display: flex; align-items: center; gap: 6px; color: var(--ws-muted); font-size: 10px; }.ws-policy-select select { height: 31px; padding: 0 8px; border: 1px solid var(--ws-line); border-radius: 5px; color: var(--ws-text); background: #fff; font-size: 10px; }.ws-primary { display: inline-flex; min-height: 34px; align-items: center; justify-content: center; gap: 6px; padding: 0 11px; border: 1px solid var(--ws-accent); border-radius: 5px; color: #fff; background: var(--ws-accent); cursor: pointer; font: inherit; font-size: 10px; font-weight: 650; white-space: nowrap; }.ws-primary:hover { background: #a9513b; }
.ws-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); margin-bottom: 12px; border: 1px solid var(--ws-line); border-radius: 7px; background: #fff; }.ws-metric { display: grid; min-height: 86px; align-content: center; gap: 4px; padding: 10px 14px; border-right: 1px solid var(--ws-line-soft); }.ws-metric:last-child { border-right: 0; }.ws-metric > span { display: flex; align-items: center; gap: 6px; color: var(--ws-muted); font-size: 10px; }.ws-metric > span i { width: 6px; height: 6px; border-radius: 50%; }.ws-metric > span i.mint { background: #50ae70; }.ws-metric > span i.blue { background: #5b7fd1; }.ws-metric > span i.coral { background: var(--ws-accent); }.ws-metric > span i.violet { background: #9275bd; }.ws-metric strong { font: 650 22px Consolas, monospace; }.ws-metric strong small { color: var(--ws-muted); font: 500 10px inherit; }.ws-metric em { color: #9aa49d; font-size: 9px; font-style: normal; }
.ws-workbench { display: grid; grid-template-columns: 230px minmax(0, 1fr) 250px; align-items: stretch; gap: 10px; }.ws-list-panel, .ws-detail-panel, .ws-boundary-panel { min-width: 0; border: 1px solid var(--ws-line); border-radius: 7px; background: var(--ws-surface); }.ws-list-panel { display: flex; min-height: 590px; flex-direction: column; }.ws-panel-heading { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 13px 12px 10px; }.ws-panel-heading h2 { margin: 0; font-size: 12px; }.ws-panel-heading h2 small { margin-left: 4px; color: var(--ws-muted); font-weight: 500; }.ws-panel-heading > span { color: #9aa49d; font-size: 8px; white-space: nowrap; }.ws-search { display: flex; align-items: center; gap: 6px; margin: 0 9px 7px; padding: 7px; border: 1px solid var(--ws-line-soft); border-radius: 5px; color: #98a29c; background: var(--ws-subtle); }.ws-search input { width: 100%; min-width: 0; border: 0; outline: none; color: var(--ws-text); background: transparent; font: inherit; font-size: 9px; }.ws-filters { display: flex; gap: 3px; padding: 0 9px 8px; border-bottom: 1px solid var(--ws-line-soft); }.ws-filters button { display: flex; min-height: 27px; align-items: center; gap: 5px; padding: 0 7px; border: 0; border-radius: 4px; color: var(--ws-muted); background: transparent; cursor: pointer; font-size: 9px; }.ws-filters button.active { color: var(--ws-accent); background: var(--ws-accent-soft); }.ws-filters b { font: 600 9px Consolas, monospace; }.ws-list { flex: 1; overflow: auto; padding: 5px 7px; }.ws-item { position: relative; display: grid; width: 100%; gap: 5px; margin: 2px 0; padding: 9px 8px; border: 1px solid transparent; border-radius: 5px; color: inherit; background: transparent; cursor: pointer; text-align: left; }.ws-item:hover { background: #f8faf8; }.ws-item.selected { border-color: #e8c5ba; background: #fff9f6; }.ws-item-title { display: flex; min-width: 0; align-items: center; gap: 5px; }.ws-item-title > i { width: 6px; height: 6px; flex: 0 0 auto; border-radius: 50%; background: #55a76e; }.ws-item-title > i.archived { background: #d29b44; }.ws-item-title strong { overflow: hidden; flex: 1; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }.ws-item-title em { color: #7a879f; font-size: 8px; font-style: normal; }.policy-code, .kind-tag { display: inline-flex; min-height: 17px; align-items: center; padding: 0 5px; border-radius: 3px; color: #718078; background: #eef2ef; font: 600 8px Consolas, monospace; white-space: nowrap; }.policy-code.workspace { color: #3d8a59; background: #eaf6ec; }.policy-code.readonly { color: #687c9e; background: #eef2f8; }.policy-code.full { color: #9a702c; background: #fff4df; }.ws-item-meta { color: #859189; font-size: 8px; }.ws-item-path { overflow: hidden; color: #9aa49d; font: 8px Consolas, monospace; text-overflow: ellipsis; white-space: nowrap; }.ws-item-changes { position: absolute; right: 8px; bottom: 8px; color: var(--ws-accent); font-size: 8px; }.ws-item.child { margin-left: 7px; width: calc(100% - 7px); }.ws-item.child::before { position: absolute; top: -6px; bottom: 50%; left: -6px; width: 5px; border-bottom: 1px solid var(--ws-line); border-left: 1px solid var(--ws-line); content: ''; }.ws-empty { padding: 18px 10px; color: var(--ws-muted); font-size: 9px; text-align: center; }.ws-quota { display: grid; gap: 5px; padding: 11px 12px; border-top: 1px solid var(--ws-line-soft); color: var(--ws-muted); font-size: 8px; }.ws-quota strong { color: var(--ws-text); font: 600 12px Consolas, monospace; }.ws-quota strong small { color: var(--ws-muted); font-size: 9px; }.ws-quota-track, .ws-budget-track { height: 4px; overflow: hidden; border-radius: 4px; background: #edf1ed; }.ws-quota-track i, .ws-budget-track i { display: block; width: 77%; height: 100%; border-radius: inherit; background: #70b27d; }
.ws-detail-panel { overflow: hidden; }.ws-detail-heading { display: flex; min-height: 59px; align-items: center; justify-content: space-between; gap: 10px; padding: 10px 13px; border-bottom: 1px solid var(--ws-line-soft); }.ws-detail-heading h2 { display: flex; align-items: center; gap: 6px; margin: 0; font-size: 12px; }.ws-detail-heading p { margin: 4px 0 0; color: var(--ws-muted); font: 9px Consolas, monospace; }.ws-updated { display: inline-flex; flex: 0 0 auto; align-items: center; gap: 4px; color: #97a19b; font-size: 8px; }.ws-tabs { display: flex; gap: 15px; padding: 0 12px; overflow-x: auto; border-bottom: 1px solid var(--ws-line-soft); }.ws-tabs button { position: relative; display: inline-flex; min-height: 37px; flex: 0 0 auto; align-items: center; gap: 5px; padding: 0 1px; border: 0; color: #829087; background: transparent; cursor: pointer; font-size: 9px; white-space: nowrap; }.ws-tabs button.active { color: var(--ws-accent); }.ws-tabs button.active::after { position: absolute; right: 0; bottom: -1px; left: 0; height: 2px; background: var(--ws-accent); content: ''; }.ws-tabs button b { padding: 1px 3px; border-radius: 3px; color: #8b6534; background: #fff3df; font-size: 7px; }.ws-tab-body { display: grid; max-height: 590px; gap: 15px; overflow: auto; padding: 13px; }.ws-path-test { padding: 11px; border: 1px solid #e5e9e4; border-radius: 6px; background: #fbfcfb; }.ws-section-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; margin-bottom: 9px; }.ws-section-head h3, .ws-file-toolbar h3, .ws-snapshot-heading h3 { display: flex; align-items: center; gap: 5px; margin: 0; color: #3b4941; font-size: 10px; }.ws-section-head p, .ws-file-toolbar p, .ws-snapshot-heading p { margin: 3px 0 0; color: #98a29b; font-size: 8px; }.ws-engine-tag, .ws-priority { color: #97a19b; font: 8px Consolas, monospace; }.ws-path-controls { display: flex; align-items: end; gap: 6px; }.ws-path-controls label { display: grid; min-width: 0; flex: 1; gap: 4px; color: #8b968e; font-size: 8px; }.ws-path-controls input { width: 100%; height: 29px; min-width: 0; padding: 0 8px; border: 1px solid var(--ws-line); border-radius: 4px; color: #3f4e45; background: #fff; font: 9px Consolas, monospace; }.ws-op-control { display: flex; height: 29px; padding: 2px; border: 1px solid var(--ws-line); border-radius: 4px; background: #fff; }.ws-op-control button { min-width: 28px; border: 0; border-radius: 3px; color: var(--ws-muted); background: transparent; cursor: pointer; font-size: 8px; }.ws-op-control button.active { color: #fff; background: #687a70; }.ws-test-button { min-height: 29px; padding: 0 9px; border: 1px solid #d9e5da; border-radius: 4px; color: #3f8155; background: #f1f8f1; cursor: pointer; font-size: 8px; }.ws-path-examples { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 7px; }.ws-path-examples button { padding: 3px 5px; border: 1px solid #e6ebe6; border-radius: 3px; color: #78847c; background: #fff; cursor: pointer; font: 8px Consolas, monospace; }.ws-path-result { display: flex; align-items: flex-start; gap: 7px; margin-top: 9px; padding: 8px; border: 1px solid #d7eadc; border-radius: 4px; color: #3f8859; background: #f2faf3; }.ws-path-result.denied { border-color: #f0d8d4; color: #b5514a; background: #fff7f5; }.ws-path-result.approval { border-color: #f0e2c7; color: #9a702c; background: #fffbf2; }.ws-path-result.idle { border-color: var(--ws-line-soft); color: #738177; background: #fff; }.ws-path-result > div { display: grid; min-width: 0; flex: 1; gap: 3px; }.ws-path-result strong { font-size: 8px; }.ws-path-result span { overflow-wrap: anywhere; color: #829087; font: 8px Consolas, monospace; }.ws-path-result > small { color: #9aa49d; font-size: 7px; }
.ws-subsection { min-width: 0; }.ws-matrix { border: 1px solid var(--ws-line-soft); border-radius: 4px; overflow: auto; }.ws-matrix-row { display: grid; min-width: 440px; grid-template-columns: minmax(130px, 1.2fr) repeat(3, minmax(70px, .8fr)); align-items: center; border-top: 1px solid var(--ws-line-soft); }.ws-matrix-row:first-child { border-top: 0; }.ws-matrix-row > * { padding: 7px 8px; color: #78847c; font-size: 8px; }.ws-matrix-row > :not(:first-child) { border-left: 1px solid var(--ws-line-soft); text-align: center; }.ws-matrix-row code { font: 8px Consolas, monospace; }.ws-matrix-head { background: #f8faf8; }.ws-matrix-head > * { color: #8c9790; font-weight: 600; }.ws-matrix-row b, .ws-matrix-row em { color: #40885b; font-size: 8px; font-style: normal; font-weight: 600; }.ws-matrix-row em { color: #a96918; }.ws-gate-steps { display: grid; grid-template-columns: 1fr 14px 1fr 14px 1fr 14px 1fr; align-items: center; gap: 4px; padding: 10px; border: 1px solid var(--ws-line-soft); border-radius: 5px; background: #fff; }.ws-gate-steps > div { display: grid; gap: 3px; }.ws-gate-steps > div > b { color: var(--ws-accent); font: 8px Consolas, monospace; }.ws-gate-steps strong { color: #59665e; font-size: 8px; }.ws-gate-steps span { color: #939d96; font-size: 7px; }.ws-gate-steps > svg { color: #aab3ad; }
.ws-file-toolbar, .ws-snapshot-heading { display: flex; align-items: center; justify-content: space-between; gap: 8px; }.ws-file-toolbar > div:last-child { display: flex; gap: 5px; }.ws-file-toolbar button, .ws-branch-bar button, .ws-change-list .ws-section-head > button, .ws-secret-rules > button { display: inline-flex; align-items: center; gap: 4px; min-height: 26px; padding: 0 7px; border: 1px solid var(--ws-line); border-radius: 4px; color: var(--ws-secondary); background: #fff; cursor: pointer; font-size: 8px; }.ws-file-browser { display: grid; min-height: 275px; grid-template-columns: minmax(145px, .75fr) minmax(0, 1.5fr); border: 1px solid var(--ws-line); border-radius: 5px; overflow: hidden; }.ws-file-tree { display: grid; align-content: start; padding: 5px; border-right: 1px solid var(--ws-line-soft); background: #fafcfa; }.ws-file-tree button { display: flex; min-width: 0; min-height: 25px; align-items: center; gap: 5px; padding: 0 4px 0 calc(5px + var(--depth) * 11px); border: 0; border-radius: 3px; color: #78847c; background: transparent; cursor: pointer; text-align: left; }.ws-file-tree button.active { color: var(--ws-accent); background: #fff0eb; }.ws-file-tree button.protected { color: #9b7949; }.ws-file-tree button span { overflow: hidden; flex: 1; font: 8px Consolas, monospace; text-overflow: ellipsis; white-space: nowrap; }.ws-file-tree button small { color: #a1aaa4; font-size: 7px; }.ws-file-preview { min-width: 0; }.ws-file-preview header { display: flex; min-height: 30px; align-items: center; gap: 5px; padding: 0 8px; border-bottom: 1px solid var(--ws-line-soft); color: #748078; font: 8px Consolas, monospace; }.ws-file-preview header button { display: grid; width: 24px; height: 24px; place-items: center; margin-left: auto; border: 0; color: #829087; background: transparent; cursor: pointer; }.ws-file-preview pre, .ws-diff-panel pre { margin: 0; padding: 10px; overflow: auto; color: #536158; background: #fff; font: 8px/1.9 Consolas, monospace; }.ws-file-preview pre code > span { color: #a7b0aa; }.ws-file-preview pre b { color: #497c58; }.ws-file-preview pre i { color: #926da6; font-style: normal; }.ws-file-preview pre em { color: #ae674c; font-style: normal; }.ws-file-preview pre strong { color: #417b8c; }.ws-table { min-width: 0; overflow: auto; border: 1px solid var(--ws-line-soft); border-radius: 4px; }.ws-table-row { display: grid; min-width: 530px; grid-template-columns: .55fr 1fr 2fr .65fr .8fr; gap: 8px; align-items: center; min-height: 31px; padding: 5px 8px; border-top: 1px solid #f0f3f0; color: #718078; font-size: 8px; }.ws-table-row:first-child { border-top: 0; }.ws-table-head { color: #929d95; background: #f9fbf9; font-weight: 600; }.ws-table-row > span:nth-child(3) { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.ws-branch-bar { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 8px; border: 1px solid var(--ws-line-soft); border-radius: 5px; background: #fafcfa; }.ws-branch-bar > div { display: flex; align-items: center; gap: 6px; color: #758178; font-size: 8px; }.ws-branch-bar select { height: 25px; padding: 0 5px; border: 1px solid var(--ws-line); border-radius: 4px; color: #46544b; background: #fff; font: 8px Consolas, monospace; }.ws-branch-bar em { color: #89958d; font: 8px Consolas, monospace; }.ws-change-layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 9px; }.ws-change-list, .ws-diff-panel, .ws-binding-group { min-width: 0; padding: 9px; border: 1px solid var(--ws-line-soft); border-radius: 5px; }.ws-change-list .ws-section-head h3 small { color: var(--ws-muted); font-weight: 500; }.ws-change-row { display: flex; min-width: 0; align-items: center; gap: 6px; padding: 6px 0; border-top: 1px solid #f0f3f0; }.ws-stage { display: grid; width: 19px; height: 19px; flex: 0 0 auto; place-items: center; border: 1px solid var(--ws-line); border-radius: 3px; color: #859189; background: #fff; cursor: pointer; }.ws-stage.staged { border-color: #a4d1ad; color: #36804c; background: #eff8f0; }.ws-change-status { width: 13px; flex: 0 0 auto; color: #6c7c97; font: 8px Consolas, monospace; }.ws-change-status.a { color: #438757; }.ws-change-status.d { color: #bb5751; }.ws-change-file { display: flex; min-width: 0; flex: 1; justify-content: space-between; gap: 5px; padding: 0; border: 0; background: transparent; cursor: pointer; text-align: left; }.ws-change-file strong { overflow: hidden; color: #68756d; font: 8px Consolas, monospace; text-overflow: ellipsis; white-space: nowrap; }.ws-change-file small { flex: 0 0 auto; color: #999f9a; font-size: 7px; }.ws-change-actions { display: flex; gap: 5px; margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--ws-line-soft); }.ws-change-actions button { display: inline-flex; align-items: center; gap: 4px; min-height: 26px; padding: 0 7px; border: 1px solid var(--ws-line); border-radius: 4px; color: #69766e; background: #fff; cursor: pointer; font-size: 8px; }.ws-change-actions button:first-child { border-color: #dcb6a8; color: var(--ws-accent); background: #fff8f4; }.ws-diff-panel pre { white-space: pre-wrap; }.ws-diff-panel pre code > span { color: #929d95; }.ws-diff-panel del { color: #a7564e; text-decoration: none; }.ws-diff-panel ins { color: #3f8755; text-decoration: none; }.ws-commit-list { display: grid; border-top: 1px solid var(--ws-line-soft); }.ws-commit-list > div { display: grid; grid-template-columns: 70px minmax(0, 1fr) 90px 70px; gap: 7px; align-items: center; padding: 8px; border-bottom: 1px solid var(--ws-line-soft); color: #728078; font-size: 8px; }.ws-commit-list code { color: #9a604c; font: 8px Consolas, monospace; }.ws-commit-list strong { overflow: hidden; color: #59665e; font-weight: 550; text-overflow: ellipsis; white-space: nowrap; }.ws-commit-list small { color: #9aa49d; text-align: right; }
.ws-snapshot-heading button { min-height: 29px; }.ws-snapshots .ws-table-row { min-width: 690px; grid-template-columns: .8fr 1.2fr .8fr .8fr .8fr .75fr .65fr .6fr; }.ws-snapshots strong, .ws-snapshots code { font: 8px Consolas, monospace; }.ws-snapshots strong { color: #59665e; }.ws-snapshots code { color: #9a604c; }.ws-snapshots em { color: var(--ws-green); font-size: 8px; font-style: normal; }.ws-snapshots em.expired { color: #9aa49d; }.ws-snapshots button { min-height: 22px; border: 1px solid var(--ws-line); border-radius: 3px; color: var(--ws-secondary); background: #fff; cursor: pointer; font-size: 8px; }.ws-snapshots button:disabled { color: #aab2ac; background: #f6f8f6; cursor: not-allowed; }.ws-snapshot-policy { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); border: 1px solid var(--ws-line-soft); border-radius: 5px; }.ws-snapshot-policy > div { display: grid; gap: 4px; padding: 10px; border-right: 1px solid var(--ws-line-soft); border-bottom: 1px solid var(--ws-line-soft); }.ws-snapshot-policy > div:nth-child(2n) { border-right: 0; }.ws-snapshot-policy > div:nth-child(n+3) { border-bottom: 0; }.ws-snapshot-policy strong { color: #56645b; font-size: 8px; }.ws-snapshot-policy span { color: #8a958e; font-size: 8px; }.ws-info-note { display: flex; align-items: flex-start; gap: 7px; padding: 9px; border: 1px solid #e5e9e4; border-radius: 4px; color: #7b877e; background: #f8faf8; font-size: 8px; line-height: 1.55; }.ws-info-note svg { flex: 0 0 auto; color: #64896b; }
.ws-context-intro, .ws-secret-intro { display: flex; align-items: flex-start; gap: 9px; padding: 11px; border: 1px solid #e8e3d5; border-radius: 5px; color: #8a6a34; background: #fffcf4; }.ws-context-intro > div, .ws-secret-intro > div { min-width: 0; flex: 1; }.ws-context-intro strong, .ws-secret-intro strong { color: #4c584e; font-size: 9px; }.ws-context-intro p, .ws-secret-intro p { margin: 4px 0 0; color: #8b958d; font-size: 8px; line-height: 1.5; }.ws-context-intro > span { color: #8a6a34; font-size: 8px; white-space: nowrap; }.ws-inherit-list { display: grid; gap: 5px; }.ws-inherit-list > div { display: grid; grid-template-columns: 85px minmax(0, 1fr) 42px; gap: 7px; align-items: center; padding: 8px; border: 1px solid var(--ws-line-soft); border-radius: 4px; color: #818d84; font-size: 8px; }.ws-inherit-list code { overflow: hidden; color: #59675e; font: 8px Consolas, monospace; text-overflow: ellipsis; white-space: nowrap; }.ws-inherit-list b { color: #4b885c; font-size: 8px; text-align: right; }.ws-binding-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }.ws-binding-group .ws-section-head { margin-bottom: 5px; }.ws-toggle-row { position: relative; display: flex; min-height: 29px; align-items: center; justify-content: space-between; gap: 5px; border-top: 1px solid #f0f3f0; cursor: pointer; }.ws-toggle-row > span { display: flex; min-width: 0; align-items: center; gap: 5px; color: #718078; }.ws-toggle-row strong { overflow: hidden; font: 8px Consolas, monospace; text-overflow: ellipsis; white-space: nowrap; }.ws-toggle-row small { color: #a0a9a3; font-size: 7px; }.ws-toggle-row input, .ws-secret-toggle input { position: absolute; width: 1px; height: 1px; opacity: 0; }.ws-toggle-row i, .ws-secret-toggle i { position: relative; width: 25px; height: 14px; flex: 0 0 auto; border-radius: 8px; background: #d5ddd6; transition: background-color 130ms ease-out; }.ws-toggle-row i::after, .ws-secret-toggle i::after { position: absolute; top: 2px; left: 2px; width: 10px; height: 10px; border-radius: 50%; background: white; content: ''; transition: transform 130ms ease-out; }.ws-toggle-row input:checked + i, .ws-secret-toggle input:checked + i { background: #68ad77; }.ws-toggle-row input:checked + i::after, .ws-secret-toggle input:checked + i::after { transform: translateX(11px); }.ws-toggle-row input:focus-visible + i, .ws-secret-toggle input:focus-visible + i { outline: 2px solid var(--ws-accent); outline-offset: 2px; }.ws-env-list { display: flex; flex-wrap: wrap; align-items: center; gap: 5px; }.ws-env-list code { padding: 4px 6px; border: 1px solid var(--ws-line-soft); border-radius: 3px; color: #69776e; background: #fafcfa; font: 8px Consolas, monospace; }.ws-env-list button { display: inline-flex; align-items: center; gap: 3px; min-height: 23px; padding: 0 5px; border: 1px dashed #d9e0d9; border-radius: 3px; color: #8a958d; background: transparent; cursor: pointer; font-size: 8px; }.ws-budget { display: grid; gap: 6px; margin-top: 10px; }.ws-budget > div:first-child { display: flex; justify-content: space-between; color: #859087; font-size: 8px; }.ws-budget strong { color: #536158; font: 8px Consolas, monospace; }.ws-budget-track i { width: 77%; background: var(--ws-accent); }.ws-budget > small { color: #969f99; font-size: 7px; }.ws-secret-intro { border-color: #eadfc7; color: #9a702c; background: #fffbf3; }.ws-secret-table .ws-table-row { min-width: 630px; grid-template-columns: .9fr 1.45fr .7fr 1.3fr .7fr .5fr; }.ws-secret-table strong { color: #59665e; font: 8px Consolas, monospace; }.ws-secret-table code { overflow: hidden; color: #718078; font: 8px Consolas, monospace; text-overflow: ellipsis; white-space: nowrap; }.ws-secret-toggle { position: relative; display: inline-flex; width: max-content; cursor: pointer; }.ws-secret-rules { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; padding: 10px; border: 1px solid var(--ws-line-soft); border-radius: 5px; }.ws-secret-rules h3 { grid-column: 1 / -1; margin: 0; color: #59665e; font-size: 9px; }.ws-secret-rules > div { display: flex; gap: 5px; color: #4a8c5e; }.ws-secret-rules > div span { display: grid; gap: 3px; color: #637168; font-size: 8px; }.ws-secret-rules small { color: #939d96; font-size: 7px; }.ws-secret-rules > button { grid-column: 1 / -1; justify-self: start; }
.ws-boundary-panel { overflow: hidden; }.ws-boundary-head { display: flex; min-height: 48px; align-items: center; justify-content: space-between; padding: 0 12px; border-bottom: 1px solid var(--ws-line-soft); }.ws-boundary-head h2 { margin: 0; font-size: 12px; }.ws-boundary-head > span { color: #99703b; font: 8px Consolas, monospace; }.ws-boundary-body { display: grid; align-content: start; }.ws-control-section { padding: 11px; border-bottom: 1px solid var(--ws-line-soft); }.ws-control-section:last-child { border-bottom: 0; }.ws-side-title { display: flex; align-items: center; justify-content: space-between; gap: 5px; margin-bottom: 8px; }.ws-side-title h3 { margin: 0; color: #58655d; font-size: 9px; }.ws-side-title > span { color: #9aa49d; font-size: 7px; }.ws-policy-option { display: flex; align-items: flex-start; gap: 7px; margin-top: 5px; padding: 8px; border: 1px solid var(--ws-line-soft); border-radius: 5px; cursor: pointer; }.ws-policy-option.active { border-color: #d8e5d9; background: #f7fbf7; }.ws-policy-option.disabled { opacity: .52; cursor: not-allowed; }.ws-policy-option input { width: 12px; height: 12px; flex: 0 0 auto; margin: 2px 0 0; accent-color: #4b9660; }.ws-policy-option > span { display: grid; min-width: 0; grid-template-columns: auto 1fr; align-items: center; gap: 4px; }.ws-policy-option strong { color: #5c6961; font-size: 8px; }.ws-policy-option small { grid-column: 1 / -1; color: #959f98; font-size: 7px; line-height: 1.4; }.ws-policy-option .policy-code { justify-self: start; }.ws-side-note { margin: 7px 0 0; color: #9aa49d; font-size: 7px; line-height: 1.5; }.ws-validation-list { display: grid; gap: 8px; }.ws-validation-list > div, .ws-gate-status > div:not(.ws-side-title):not(.ws-deny-summary) { display: flex; align-items: flex-start; gap: 6px; color: #4b9260; }.ws-validation-list span, .ws-gate-status > div > span { display: grid; gap: 3px; color: #758178; font-size: 8px; }.ws-validation-list small, .ws-gate-status small { color: #9ba49e; font-size: 7px; }.ws-run-binding { display: flex; align-items: center; gap: 6px; padding: 6px 0; border-top: 1px solid #f1f3f1; color: #718078; font: 7px Consolas, monospace; }.ws-run-dot { width: 5px; height: 5px; flex: 0 0 auto; border-radius: 50%; background: #51a96b; }.ws-no-runs { padding: 9px 0; color: #98a29b; font-size: 8px; }.ws-storage-foot { display: grid; grid-template-columns: 1fr auto; gap: 4px; margin-top: 7px; padding-top: 7px; border-top: 1px solid var(--ws-line-soft); color: #929d95; font-size: 7px; }.ws-storage-foot strong { grid-column: 2; grid-row: 1 / span 2; align-self: center; color: #57645c; font: 10px Consolas, monospace; }.ws-storage-foot small { color: #a0a9a3; font-size: 7px; }.ws-live { display: inline-flex; align-items: center; gap: 4px; color: #66876e !important; }.ws-live i { width: 5px; height: 5px; border-radius: 50%; background: #5bab70; }.ws-gate-status > div:not(.ws-side-title):not(.ws-deny-summary) { align-items: flex-start; padding: 5px 0; }.ws-gate-status > div > b { margin-left: auto; color: #4b9260; font: 7px Consolas, monospace; }.ws-gate-status > div > b.pending { color: #9b793f; }.ws-deny-summary { display: grid; gap: 4px; margin-top: 6px; padding: 8px; border-radius: 4px; background: #f8faf8; }.ws-deny-summary strong { color: #68756d; font-size: 8px; }.ws-deny-summary span { color: #8f9a92; font-size: 7px; line-height: 1.4; }
.ws-footer { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 10px; padding: 9px 11px; border: 1px solid var(--ws-line); border-radius: 5px; color: #77847b; background: #fff; }.ws-footer > div, .ws-footer > span { display: flex; align-items: center; gap: 7px; }.ws-footer > div > svg { color: #66896e; }.ws-footer span { font-size: 8px; }.ws-footer > div span { display: grid; gap: 2px; }.ws-footer strong { color: #5f6c63; font-size: 8px; }.ws-footer small { color: #99a39c; font-size: 7px; }.ws-toast { position: fixed; right: 20px; bottom: 18px; z-index: 30; display: flex; align-items: center; gap: 6px; padding: 9px 12px; border: 1px solid #e5c0b3; border-radius: 5px; color: #874936; background: #fff7f3; box-shadow: 0 8px 20px #34423b20; font-size: 9px; }
@media (max-width: 1450px) { .ws-workbench { grid-template-columns: 215px minmax(0, 1fr); }.ws-list-panel { grid-column: 1; grid-row: 1 / span 2; }.ws-detail-panel { grid-column: 2; grid-row: 1; }.ws-boundary-panel { grid-column: 2; grid-row: 2; }.ws-boundary-body { grid-template-columns: repeat(2, minmax(0, 1fr)); }.ws-control-section:nth-child(odd) { border-right: 1px solid var(--ws-line-soft); }.ws-control-section:last-child { grid-column: 1 / -1; border-top: 1px solid var(--ws-line-soft); }.ws-gate-status { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: 12px; }.ws-gate-status .ws-side-title, .ws-gate-status .ws-deny-summary { grid-column: 1 / -1; } }
@media (max-width: 780px) { .ws-header { flex-wrap: wrap; }.ws-title-lockup { flex: 1; }.ws-root-pill { order: 3; width: 100%; }.ws-root-pill code { flex: 1; }.ws-header-actions { margin-left: 0; }.ws-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }.ws-metric:nth-child(2) { border-right: 0; }.ws-metric:nth-child(-n+2) { border-bottom: 1px solid var(--ws-line-soft); }.ws-workbench { grid-template-columns: minmax(0, 1fr); }.ws-list-panel, .ws-detail-panel, .ws-boundary-panel { grid-column: auto; grid-row: auto; }.ws-list-panel { min-height: 330px; max-height: 390px; }.ws-tab-body { max-height: none; }.ws-footer { align-items: flex-start; flex-direction: column; }.ws-gate-steps { grid-template-columns: 1fr 12px 1fr; row-gap: 9px; }.ws-gate-steps > svg:nth-of-type(2) { display: none; } }
@media (max-width: 520px) { .ws-header-actions { width: 100%; justify-content: space-between; }.ws-policy-select { flex: 1; justify-content: space-between; }.ws-policy-select select { min-width: 115px; }.ws-metric { min-height: 74px; padding: 8px; }.ws-metric strong { font-size: 18px; }.ws-detail-heading { align-items: flex-start; }.ws-updated { display: none; }.ws-tabs { gap: 12px; }.ws-tab-body { padding: 9px; }.ws-path-controls { flex-wrap: wrap; }.ws-path-controls label { flex-basis: 100%; }.ws-op-control { margin-left: auto; }.ws-file-browser, .ws-change-layout, .ws-binding-grid { grid-template-columns: minmax(0, 1fr); }.ws-file-tree { max-height: 180px; overflow: auto; border-right: 0; border-bottom: 1px solid var(--ws-line-soft); }.ws-snapshot-policy { grid-template-columns: minmax(0, 1fr); }.ws-snapshot-policy > div { border-right: 0; border-bottom: 1px solid var(--ws-line-soft) !important; }.ws-snapshot-policy > div:last-child { border-bottom: 0 !important; }.ws-secret-rules { grid-template-columns: minmax(0, 1fr); }.ws-secret-rules h3, .ws-secret-rules > button { grid-column: auto; }.ws-commit-list > div { grid-template-columns: 56px minmax(0, 1fr) 60px; }.ws-commit-list > div small { display: none; }.ws-boundary-body { grid-template-columns: minmax(0, 1fr); }.ws-control-section:nth-child(odd) { border-right: 0; }.ws-gate-status { display: block; }.ws-gate-status .ws-side-title, .ws-gate-status .ws-deny-summary { grid-column: auto; } }
</style>
