<script setup>
import { computed, ref } from 'vue'
import { Activity, Archive, ArrowDownToLine, ArrowRight, Bot, Boxes, Check, ChevronDown, CircleHelp, Clock3, Command, Cpu, FileText, Filter, HardDrive, Layers3, ListChecks, Menu, MoreHorizontal, Network, Pause, Play, Plus, Search, Settings2, ShieldCheck, Sparkles, Square, Terminal, Workflow, Wrench, X } from 'lucide-vue-next'

const sections = [
  { label: '控制平面', items: [{ id: 'overview', label: '运行总览', icon: Activity }, { id: 'runs', label: '执行任务', icon: ListChecks, count: '12' }, { id: 'agents', label: 'Agent 实例', icon: Bot, count: '4' }, { id: 'workspaces', label: '工作空间', icon: Layers3, count: '6' }] },
  { label: '能力注册表', items: [{ id: 'tools', label: '工具与 MCP', icon: Wrench, count: '18' }, { id: 'skills', label: 'Skills', icon: Sparkles, count: '23' }, { id: 'models', label: '模型路由', icon: Network, count: '5' }] },
  { label: '运行治理', items: [{ id: 'machines', label: '机器与运行时', icon: Cpu, count: '3' }, { id: 'approvals', label: '待审批', icon: ShieldCheck, count: '2' }, { id: 'artifacts', label: '产物与存储', icon: Archive }, { id: 'observability', label: '追踪与日志', icon: Terminal }] },
]
const props = defineProps({ embedded: { type: Boolean, default: false } })
const runs = ref([
  { id: 'RUN-2048', title: '梳理客服工单中的退款异常', workspace: 'support-ops / main', agent: 'Support analyst', model: 'Claude Sonnet 4', status: 'running', elapsed: '02:41', tokens: '18.4k', cost: '$0.042', progress: 68, phase: '正在归纳 24 条关联工单' },
  { id: 'RUN-2047', title: '为知识库补充 API 错误码说明', workspace: 'docs-platform / feature/api-errors', agent: 'Docs engineer', model: 'GPT-5', status: 'running', elapsed: '01:18', tokens: '9.2k', cost: '$0.019', progress: 42, phase: '等待 Playwright 页面验证' },
  { id: 'RUN-2046', title: '检查本周自动化任务失败原因', workspace: 'agent-platform / main', agent: 'Platform operator', model: 'DeepSeek V3.2', status: 'queued', elapsed: '等待中', tokens: '—', cost: '—', progress: 0, phase: '排队 · 预计 00:34' },
  { id: 'RUN-2045', title: '生成工单分类规则回归测试', workspace: 'support-ops / rules-v2', agent: 'QA engineer', model: 'Claude Sonnet 4', status: 'running', elapsed: '04:06', tokens: '31.7k', cost: '$0.071', progress: 86, phase: '执行 12 项回归断言' },
])
const events = ref([
  { time: '14:32:41.208', type: 'success', title: '运行初始化完成', detail: '工作空间已挂载 · 沙箱 runtime-7f2a 就绪' },
  { time: '14:32:42.011', type: 'info', title: '载入 Agent 配置', detail: 'support-analyst@v1.8 · 12 个工具可用' },
  { time: '14:32:44.390', type: 'success', title: '检索到 24 条相关工单', detail: 'knowledge.search · 4 个知识分片命中' },
  { time: '14:33:06.174', type: 'warning', title: '等待人工确认外部查询', detail: 'crm.ticket.update · 写入操作 · 影响 3 条记录' },
  { time: '14:33:08.942', type: 'info', title: '生成退款异常聚类草稿', detail: '输出 4 个候选类别 · 置信度 0.91' },
])
const activeSection = ref('overview')
const activeView = ref('control')
const filter = ref('全部任务')
const search = ref('')
const moduleTab = ref('catalog')
const moduleStateFilter = ref('全部状态')
const selectedModuleRecord = ref(null)
const selectedRunId = ref('RUN-2048')
const toast = ref('')
const mobileNavOpen = ref(false)
const running = ref(true)
const sectionMode = computed(() => ['overview', 'runs'].includes(activeSection.value) ? 'demo' : 'planned')
const sourceLabel = computed(() => ['overview', 'runs'].includes(activeSection.value) ? '演示运行数据' : '规划数据 · 未接入运行 API')
const selectedRun = computed(() => runs.value.find(run => run.id === selectedRunId.value) || runs.value[0])
const visibleRuns = computed(() => runs.value.filter(run => {
  const filterMatch = filter.value === '全部任务' || (filter.value === '运行中' ? run.status === 'running' : run.status === 'queued')
  return filterMatch && `${run.id} ${run.title} ${run.agent}`.toLowerCase().includes(search.value.toLowerCase())
}))
const navTitle = computed(() => sections.flatMap(group => group.items).find(item => item.id === activeSection.value)?.label || '运行总览')
const pageHeading = computed(() => activeSection.value === 'overview' ? 'Harness 控制台' : navTitle.value)

function notify(message) {
  toast.value = message
  window.clearTimeout(notify.timer)
  notify.timer = window.setTimeout(() => { toast.value = '' }, 2600)
}
function createRun() {
  const id = `RUN-${2049 + runs.value.length - 4}`
  runs.value.unshift({ id, title: '新建 Agent 执行任务', workspace: 'support-ops / main', agent: '通用执行 Agent', model: '自动路由', status: 'queued', elapsed: '等待中', tokens: '—', cost: '—', progress: 0, phase: '排队 · 等待运行时资源' })
  selectedRunId.value = id
  activeSection.value = 'runs'
  activeView.value = 'control'
  notify(`${id} 已加入执行队列`)
}
function approveRun(decision = '批准') {
  const index = events.value.findIndex(event => event.type === 'warning')
  if (index >= 0) events.value[index] = { time: '14:34:12.506', type: decision === '批准' ? 'success' : 'warning', title: decision === '批准' ? '人工审批已通过' : '人工审批已拒绝', detail: `操作者：你 · crm.ticket.update ${decision === '批准' ? '写入权限已授予' : '调用已阻止'}` }
  notify(decision === '批准' ? '审批已通过，运行将继续执行' : '审批已拒绝，工具调用已阻止')
}
function selectSection(id) {
  activeSection.value = id
  mobileNavOpen.value = false
  activeView.value = 'control'
  moduleTab.value = 'catalog'
  moduleStateFilter.value = '全部状态'
  selectedModuleRecord.value = null
}
function openModuleRecord(record) {
  selectedModuleRecord.value = record
}
function selectModuleTab(tab) {
  moduleTab.value = tab
  moduleStateFilter.value = '全部状态'
  selectedModuleRecord.value = null
}
const moduleRows = computed(() => {
  const records = sectionRecords(activeSection.value)
  if (moduleTab.value === 'runs') return records.filter(row => /RUN-|执行|运行|调用|心跳|审批/.test(`${row.activity} ${row.owner}`))
  if (moduleTab.value === 'changes') return records.filter(row => /草稿|变更|修改|未连接|离线|需审批|待审批|待处理/.test(`${row.state} ${row.detail} ${row.activity}`))
  return records
})
const filteredModuleRows = computed(() => moduleRows.value.filter(row => {
  const query = `${row.name} ${row.detail} ${row.owner} ${row.activity}`.toLowerCase()
  const matchesSearch = query.includes(search.value.toLowerCase())
  const matchesState = moduleStateFilter.value === '全部状态' || row.state === moduleStateFilter.value
  return matchesSearch && matchesState
}))
function sectionSummary(id) {
  const content = {
    agents: ['Agent 实例', '4 个 Agent 配置正在工作空间中执行。每个实例绑定独立的模型路由、工具权限和运行策略。', ['support-analyst · v1.8 · 运行中', 'docs-engineer · v2.1 · 运行中', 'platform-operator · v1.3 · 空闲', 'qa-engineer · v1.4 · 运行中']],
    workspaces: ['工作空间', '每次运行使用独立工作目录与会话快照。Git 分支、文件变更和运行历史均可追溯。', ['support-ops · main · 2 个运行', 'docs-platform · feature/api-errors · 1 个运行', 'agent-platform · main · 空闲', 'support-ops · rules-v2 · 1 个运行']],
    tools: ['工具与 MCP', '统一查看工具来源、访问范围、调用策略和最近使用情况。敏感写入操作可配置人工审批。', ['knowledge.search · MCP · 只读', 'crm.ticket.update · MCP · 需审批', 'playwright.browser · 内置 · 沙箱', 'filesystem.patch · 内置 · 工作区范围']],
    skills: ['Skills', '可组合的任务能力包。Skill 版本随每次运行记录，变更后可比较行为和调用轨迹。', ['support-triage · v1.8 · 已启用', 'api-docs · v2.1 · 已启用', 'release-check · v1.3 · 草稿', 'refund-analysis · v1.2 · 已启用']],
    models: ['模型路由', '按任务类型、成本上限和可用性选择模型。每次路由决策都会记录原因和实际用量。', ['Claude Sonnet 4 · 默认 · 可用', 'GPT-5 · 文档任务 · 可用', 'DeepSeek V3.2 · 低成本队列 · 可用', '本地模型 · 私有任务 · 未连接']],
    machines: ['机器与运行时', '管理本地与远端执行节点，观察容量、隔离方式、版本和心跳。运行环境为演示数据。', ['local-dev · Docker · 2 / 4 slots', 'gpu-worker-01 · Remote · 1 / 2 slots', 'ci-runner · Container · 0 / 8 slots']],
    approvals: ['待审批', '高影响工具调用在执行前暂停，审批决定、操作者与执行结果一并进入审计事件。', ['RUN-2048 · crm.ticket.update · 影响 3 条记录', 'RUN-2043 · filesystem.patch · 修改 2 个文件']],
    artifacts: ['产物与存储', '按运行查看补丁、日志、截图、结构化结果和会话快照；产物继承对应工作空间权限。', ['RUN-2048 · refund-clusters.json · 4.2 KB', 'RUN-2047 · api-errors.patch · 2.1 KB', 'RUN-2045 · regression-report.html · 86 KB']],
    observability: ['追踪与日志', '将 Agent 推理阶段、模型请求、工具调用和运行时事件放进同一条可筛选时间线。', ['agent.turn · 1.84s · Claude Sonnet 4', 'knowledge.search · 0.32s · 4 chunks', 'approval.wait · 00:48 · pending', 'artifact.write · 0.08s · 1 file']],
    settings: ['Harness 设置', '运行时默认值、审计保留周期与策略模板的集中配置入口。', ['默认隔离：容器', '审计保留：30 天', '审批策略：按工具风险等级']],
  }
  return content[id] || content.agents
}
function sectionRecords(id) {
  const rows = sectionSummary(id)[2].map((label, index) => {
    const parts = label.split(' · ')
    return { name: parts[0], detail: parts.slice(1).join(' · '), index }
  })
  if (id === 'agents') return rows.map((row, index) => ({ ...row, type: ['分析 Agent', '文档 Agent', '平台 Agent', '测试 Agent'][index], owner: ['客服运营', '文档平台', '平台工程', '质量工程'][index], activity: ['RUN-2048 · 正在执行', 'RUN-2047 · 正在执行', '最近活跃 8 分钟前', 'RUN-2045 · 正在执行'][index], state: index === 2 ? '空闲' : '运行中' }))
  if (id === 'workspaces') return rows.map((row, index) => ({ ...row, type: 'Git 工作区', owner: ['客服运营', '文档平台', 'Agent 平台', '客服运营'][index], activity: ['2 个运行 · 1 个变更', '1 个运行 · 3 个变更', '空闲 · 工作树干净', '1 个运行 · 2 个变更'][index], state: index === 2 ? '空闲' : '使用中' }))
  if (id === 'tools') return rows.map((row, index) => ({ ...row, type: ['MCP 工具', 'MCP 工具', '浏览器工具', '文件工具'][index], owner: ['Knowledge MCP', 'CRM MCP', '内置运行时', '内置运行时'][index], activity: ['最近调用 14:32:44', '等待 RUN-2048 审批', '最近调用 14:29:12', '工作区范围受限'][index], state: index === 1 ? '需审批' : '已配置' }))
  if (id === 'skills') return rows.map((row, index) => ({ ...row, type: '任务技能', owner: ['Support Ops', 'Docs Platform', 'Platform QA', 'Support Ops'][index], activity: ['最近用于 RUN-2048', '最近用于 RUN-2047', '尚未发布', '最近用于 RUN-2048'][index], state: index === 2 ? '草稿' : '已启用' }))
  if (id === 'models') return rows.map((row, index) => ({ ...row, type: ['默认路由', '任务路由', '成本路由', '私有路由'][index], owner: ['通用任务', '文档任务', '低成本队列', '私有任务'][index], activity: ['延迟 1.84s · 今日 18 次', '延迟 2.12s · 今日 9 次', '延迟 1.31s · 今日 6 次', '等待连接配置'][index], state: index === 3 ? '未连接' : '可用' }))
  if (id === 'machines') return rows.map((row, index) => ({ ...row, type: ['Docker · Windows', 'Remote · Linux', 'Container · Linux'][index], owner: ['本地开发机', 'GPU 执行池', 'CI 执行池'][index], activity: ['心跳刚刚 · 2 / 4 槽位', '心跳 8 秒前 · 1 / 2 槽位', '心跳 6 分钟前 · 0 / 8 槽位'][index], state: index === 2 ? '离线' : '在线' }))
  if (id === 'approvals') return rows.map((row, index) => ({ ...row, type: index ? '文件变更' : '外部写入', owner: index ? 'filesystem.patch' : 'crm.ticket.update', activity: index ? '修改 2 个文件 · RUN-2043' : '影响 3 条记录 · RUN-2048', state: '待审批' }))
  if (id === 'artifacts') return rows.map((row, index) => ({ ...row, type: ['结构化结果', '代码补丁', '测试报告'][index], owner: ['4.2 KB · JSON', '2.1 KB · PATCH', '86 KB · HTML'][index], activity: ['生成于 14:33:09', '生成于 14:27:31', '生成于 14:12:04'][index], state: '已生成' }))
  if (id === 'observability') return rows.map((row, index) => ({ ...row, type: ['模型调用', 'MCP 调用', '治理事件', '产物事件'][index], owner: ['RUN-2048 · Claude Sonnet 4', 'RUN-2048 · knowledge.search', 'RUN-2048 · approval.wait', 'RUN-2048 · artifact.write'][index], activity: ['14:32:44 · 1.84 秒', '14:32:44 · 0.32 秒', '14:33:06 · 等待 48 秒', '14:33:09 · 0.08 秒'][index], state: index === 2 ? '待处理' : '已记录' }))
  return rows.map(row => ({ ...row, type: '运行策略', owner: '本地演示配置', activity: '修改后仅影响后续新建运行', state: '草案' }))
}
</script>

<template>
  <div class="harness-shell" :class="{ 'is-embedded': props.embedded }">
    <div v-if="mobileNavOpen" class="mobile-scrim" @click="mobileNavOpen = false"></div>
    <aside v-if="!props.embedded" class="harness-sidebar" :class="{ 'is-open': mobileNavOpen }">
      <div class="brand-lockup"><div class="brand-symbol"><Workflow :size="18" :stroke-width="2" /></div><div class="brand-copy"><strong>HOTLINE</strong><span>AGENT HARNESS</span></div><button class="close-mobile" aria-label="关闭导航" @click="mobileNavOpen = false"><X :size="17" /></button></div>
      <button class="workspace-switch" @click="notify('工作空间切换器暂为演示状态')"><span class="workspace-mark">H</span><span class="workspace-copy"><strong>Hotline Agent</strong><small>个人工作区</small></span><ChevronDown :size="15" /></button>
      <nav class="side-navigation" aria-label="Harness 导航"><div v-for="group in sections" :key="group.label" class="nav-group"><div class="nav-group-label">{{ group.label }}</div><button v-for="item in group.items" :key="item.id" class="nav-link" :class="{ active: activeSection === item.id }" @click="selectSection(item.id)"><component :is="item.icon" :size="16" :stroke-width="1.8" /><span>{{ item.label }}</span><small v-if="item.count">{{ item.count }}</small></button></div></nav>
      <div class="sidebar-bottom"><div class="runtime-health"><span class="health-led"></span><span>本地控制面</span><strong>健康</strong></div><button class="nav-link" @click="selectSection('settings')"><Settings2 :size="16" /><span>Harness 设置</span><MoreHorizontal :size="15" /></button><div class="user-row"><div class="user-avatar">SC</div><div class="user-copy"><strong>Song Chen</strong><small>管理员</small></div><CircleHelp :size="16" /></div></div>
    </aside>

    <main class="main-surface">
      <header v-if="!props.embedded" class="topbar"><button class="mobile-menu" aria-label="打开导航" @click="mobileNavOpen = true"><Menu :size="19" /></button><div class="breadcrumbs"><span>Harness</span><span class="crumb-slash">/</span><strong>{{ navTitle }}</strong></div><div class="topbar-actions"><span class="demo-label" :class="{ planned: sectionMode === 'planned' }"><span></span>{{ sourceLabel }}</span><button class="top-icon" aria-label="搜索" title="搜索" @click="$refs.searchField?.focus()"><Search :size="16" /></button><button class="command-shortcut" @click="$refs.searchField?.focus()"><Command :size="13" />快速查找<kbd>Ctrl K</kbd></button><button class="avatar-small" aria-label="个人账户">SC</button></div></header>
      <div class="page-scroll"><div class="page-content">
      <div class="page-heading-row"><div><h1>{{ pageHeading }}</h1><p v-if="activeSection === 'overview'">统一查看 Agent 执行、工具治理与运行环境。</p><p v-else>{{ sectionSummary(activeSection)[1] }}</p></div><div class="heading-actions"><span v-if="props.embedded" class="embedded-source-label">{{ sourceLabel }}</span><button class="button button-subtle refresh-button" title="刷新状态" aria-label="刷新状态" @click="notify('已刷新本地演示状态')"><Activity :size="15" /><span>刷新状态</span></button><button class="button button-primary" @click="createRun"><Plus :size="16" />新建运行</button></div></div>

        <div v-if="sectionMode === 'planned'" class="planned-notice"><div class="planned-mark"><ShieldCheck :size="18" /></div><div><strong>{{ navTitle }}尚未接入运行控制 API</strong><span>当前展示规划范围和待接入状态。接入后此处会显示来自后端的实时资源、版本与审计数据。</span></div><span class="planned-badge">目标模块 · {{ activeSection }}</span></div>
        <template v-if="activeSection === 'overview' || activeSection === 'runs'">
          <section class="overview-strip" aria-label="运行指标"><div class="overview-stat"><span>活动运行</span><strong>03</strong><small><i class="status-inline"></i>2 执行中 · 1 排队</small></div><div class="overview-stat"><span>今日完成</span><strong>28</strong><small class="positive"><Check :size="12" />成功率 96.4%</small></div><div class="overview-stat"><span>待人工审批</span><strong class="stat-warn">02</strong><small>最高风险：写入操作</small></div><div class="overview-stat"><span>今日模型用量</span><strong>1.82M</strong><small>Tokens · 估算 $4.82</small></div><div class="overview-stat stat-runtime"><span>运行时节点</span><strong>02 <em>/ 03</em></strong><small>8 / 14 并发槽位可用</small></div></section>

          <section class="run-workbench" :class="{ 'runs-view': activeSection === 'runs' }">
            <div class="run-list-panel"><div class="panel-heading run-list-heading"><div><h2>执行队列</h2><span>任务、Agent 与工作空间</span></div><button class="icon-action" title="筛选任务" @click="filter = filter === '全部任务' ? '运行中' : '全部任务'"><Filter :size="15" /></button></div><div class="run-list-tools"><div class="run-filters"><button v-for="option in ['全部任务', '运行中', '排队中']" :key="option" :class="{ selected: filter === option }" @click="filter = option">{{ option }}<span v-if="option === '全部任务'">12</span></button></div><label class="run-search"><Search :size="14" /><input ref="searchField" v-model="search" placeholder="搜索任务" /></label></div><div class="run-list"><button v-for="run in visibleRuns" :key="run.id" class="run-row" :class="{ selected: selectedRunId === run.id }" @click="selectedRunId = run.id; activeView = 'control'"><div class="run-row-top"><span class="run-status-dot" :class="run.status"></span><strong>{{ run.title }}</strong><span class="run-row-menu" @click.stop="notify(`${run.id} 操作菜单`)"><MoreHorizontal :size="16" /></span></div><div class="run-row-meta"><span>{{ run.id }}</span><span class="meta-sep">·</span><span>{{ run.agent }}</span></div><div class="run-row-bottom"><span>{{ run.workspace }}</span><span v-if="run.status === 'running'" class="run-elapsed">{{ run.elapsed }}</span><span v-else class="queued-tag">排队中</span></div><div v-if="run.status === 'running'" class="run-progress"><i :style="{ width: `${run.progress}%` }"></i></div></button><div v-if="!visibleRuns.length" class="empty-runs"><Search :size="18" /><span>没有匹配的运行</span><button @click="search = ''; filter = '全部任务'">清除筛选</button></div></div><button class="queue-footer" @click="activeSection = 'runs'"><span>查看全部执行记录</span><ArrowRight :size="14" /></button></div>

            <div class="run-detail-panel"><div class="run-detail-top"><div class="detail-title-group"><div class="detail-run-id"><span class="run-status-dot" :class="selectedRun.status"></span>{{ selectedRun.id }}<span class="status-pill" :class="selectedRun.status">{{ selectedRun.status === 'running' ? '运行中' : '排队中' }}</span></div><h2>{{ selectedRun.title }}</h2><div class="detail-subtitle"><span>{{ selectedRun.workspace }}</span><span>·</span><span>{{ selectedRun.agent }}</span></div></div><div class="detail-toolbar"><button class="icon-action" title="下载运行记录" @click="notify('运行记录导出已准备')"><ArrowDownToLine :size="15" /></button><button class="icon-action" title="更多操作" @click="notify('运行操作菜单')"><MoreHorizontal :size="16" /></button><button v-if="running && selectedRun.status === 'running'" class="button button-stop" @click="running = false; notify(`${selectedRun.id} 已请求安全停止`)"><Square :size="12" />停止运行</button><button v-else class="button button-subtle" @click="running = true; notify('运行已恢复')"><Play :size="14" />恢复</button></div></div>
              <div class="detail-tabs"><button :class="{ active: activeView === 'control' }" @click="activeView = 'control'">执行轨迹</button><button :class="{ active: activeView === 'trace' }" @click="activeView = 'trace'">Trace <span>8</span></button><button :class="{ active: activeView === 'context' }" @click="activeView = 'context'">上下文</button><button :class="{ active: activeView === 'artifacts' }" @click="activeView = 'artifacts'">产物 <span>1</span></button><button :class="{ active: activeView === 'registry' }" @click="activeView = 'registry'">配置快照</button></div>
              <div v-if="activeView === 'control'" class="detail-scroll"><div class="execution-summary"><div><span class="summary-label">当前阶段</span><strong>{{ running ? selectedRun.phase : '已请求安全停止' }}</strong></div><div class="summary-progress"><div class="summary-progress-top"><span>总体进度</span><strong>{{ running ? selectedRun.progress : 68 }}%</strong></div><div class="progress-track"><i :style="{ width: `${running ? selectedRun.progress : 68}%` }"></i></div></div><div class="summary-meta"><span><Clock3 :size="13" />{{ selectedRun.elapsed }}</span><span><FileText :size="13" />{{ selectedRun.tokens }} tokens</span><span>{{ selectedRun.cost }}</span></div></div>
                <div v-if="events.some(event => event.type === 'warning')" class="approval-banner"><div class="approval-icon"><ShieldCheck :size="17" /></div><div class="approval-copy"><strong>此运行需要人工审批</strong><span>crm.ticket.update 将修改 3 条工单记录</span></div><button class="button button-approve" @click="approveRun('批准')"><Check :size="14" /><span>批准并继续</span></button><button class="button button-reject" @click="approveRun('拒绝')">拒绝</button></div>
                <div class="timeline-header"><h3>运行事件</h3><button class="text-action" @click="activeView = 'trace'">查看完整 Trace <ArrowRight :size="13" /></button></div><div class="timeline"><div v-for="(event, index) in events" :key="event.time" class="timeline-event"><div class="timeline-rail"><span class="timeline-marker" :class="event.type"><Check v-if="event.type === 'success'" :size="10" /><Pause v-else-if="event.type === 'warning'" :size="10" /><i v-else></i></span><span v-if="index < events.length - 1" class="timeline-line"></span></div><div class="event-main"><div class="event-title-row"><strong>{{ event.title }}</strong><time>{{ event.time }}</time></div><p>{{ event.detail }}</p><button v-if="event.type === 'success' && event.title.includes('工单')" class="event-tool" @click="activeView = 'trace'"><Search :size="12" />knowledge.search<span>0.32s</span><ArrowRight :size="12" /></button></div></div></div>
              </div>
              <div v-else-if="activeView === 'trace'" class="trace-view"><div class="trace-toolbar"><div><strong>执行 Trace</strong><span> · {{ selectedRun.id }} · 按因果顺序记录</span></div><button class="button button-subtle" @click="notify('Trace JSON 已准备导出')"><ArrowDownToLine :size="14" />导出 JSON</button></div><div class="trace-table"><div class="trace-head"><span>阶段 / 调用</span><span>类型</span><span>耗时</span><span>Tokens</span><span>状态</span></div><div v-for="row in [{n:'agent.run',t:'Agent',d:'2m 41s',k:'18.4k',s:'运行中'},{n:'model.completion',t:'Claude Sonnet 4',d:'1.84s',k:'2.1k',s:'成功'},{n:'knowledge.search',t:'MCP Tool',d:'0.32s',k:'—',s:'成功'},{n:'approval.wait',t:'治理策略',d:'00:48',k:'—',s:'待审批'},{n:'artifact.write',t:'Artifact',d:'0.08s',k:'—',s:'成功'}]" :key="row.n" class="trace-row"><strong>{{ row.n }}</strong><span>{{ row.t }}</span><span>{{ row.d }}</span><span>{{ row.k }}</span><span class="trace-state" :class="{ pending: row.s === '待审批', live: row.s === '运行中' }">{{ row.s }}</span></div></div></div>
              <div v-else-if="activeView === 'context'" class="context-view"><div class="context-header"><div><h3>运行上下文快照</h3><p>此快照在 {{ selectedRun.id }} 启动时记录 · 只读</p></div><button class="button button-subtle" @click="notify('上下文快照已准备导出')"><ArrowDownToLine :size="14" />导出快照</button></div><div class="context-block"><div class="context-block-title"><FileText :size="14" />系统指令 <span>2,184 tokens</span></div><pre>Hotline 客服运营分析 Agent：先检索知识库，再关联工单；写入动作必须等待人工审批；输出可验证证据，不确定时明确标注。权限：knowledge.search (read) · crm.ticket.read (read) · crm.ticket.update (approval required)</pre></div><div class="context-block"><div class="context-block-title"><Boxes :size="14" />已装配能力 <span>4 项</span></div><div class="context-chip-list"><span>support-triage@1.8</span><span>refund-analysis@1.2</span><span>knowledge.search</span><span>crm.ticket.read</span></div></div><div class="context-block"><div class="context-block-title"><HardDrive :size="14" />工作空间 <span>support-ops / main</span></div><div class="context-file"><FileText :size="14" />workspace snapshot <span>commit 7bd2f13</span><Check :size="14" /></div></div></div>
              <div v-else-if="activeView === 'artifacts'" class="artifact-view"><div class="artifact-heading"><div><h3>运行产物</h3><p>产物归属于 {{ selectedRun.id }}，继承工作空间访问权限。</p></div><button class="button button-subtle" @click="notify('产物已准备下载')"><ArrowDownToLine :size="14" />下载全部</button></div><div class="artifact-row"><div class="artifact-file-icon"><FileText :size="17" /></div><div class="artifact-file-copy"><strong>refund-clusters.json</strong><span>结构化结果 · 4.2 KB · 14:33:09</span></div><button class="icon-action" title="下载文件" @click="notify('refund-clusters.json 已准备下载')"><ArrowDownToLine :size="15" /></button></div><pre class="artifact-preview">{ "clusters": [{"label":"重复扣款","tickets":8,"confidence":0.94},{"label":"退款延迟","tickets":11,"confidence":0.91},{"label":"金额不符","tickets":5,"confidence":0.88}], "source_count": 24 }</pre></div>
              <div v-else class="registry-view"><div class="registry-title"><h3>{{ sectionSummary(activeSection)[0] }}</h3><span>规划清单</span></div><p>{{ sectionSummary(activeSection)[1] }}</p><div class="registry-list"><div v-for="(item, index) in sectionSummary(activeSection)[2]" :key="item" class="registry-row planned-row"><span class="registry-row-icon"><Boxes :size="16" /></span><strong>{{ item.split(' · ')[0] }}</strong><span>{{ item.split(' · ').slice(1).join(' · ') }}</span><span class="registry-health"><i class="off"></i>{{ activeSection === 'machines' ? '规划节点' : '未连接' }}</span></div></div><div class="registry-footnote"><ShieldCheck :size="14" />以上为规划条目，不代表当前系统已安装或正在运行。</div></div>
            </div>

            <aside class="run-inspector"><div class="inspector-heading"><h2>运行检查</h2><button class="icon-action" title="运行检查设置" @click="notify('运行检查设置')"><Settings2 :size="15" /></button></div><div class="inspector-section"><div class="inspector-section-title">执行身份 <button class="text-action" @click="activeView = 'context'">查看快照</button></div><div class="identity-row"><div class="agent-avatar"><Bot :size="16" /></div><div><strong>{{ selectedRun.agent }}</strong><span>Agent · v1.8</span></div><span class="identity-healthy"></span></div><div class="identity-meta"><span>模型</span><strong>{{ selectedRun.model }}</strong></div><div class="identity-meta"><span>路由策略</span><strong>质量优先 · fallback 已启用</strong></div></div><div class="inspector-section"><div class="inspector-section-title">工具调用 <span>4 / 12</span></div><div class="tool-summary"><div class="tool-donut"><strong>4</strong><span>调用</span></div><div class="tool-breakdown"><span><i class="tool-dot success"></i>成功 <strong>3</strong></span><span><i class="tool-dot pending"></i>待审批 <strong>1</strong></span><span><i class="tool-dot error"></i>失败 <strong>0</strong></span></div></div><button class="inspector-link" @click="activeView = 'trace'">打开调用明细 <ArrowRight :size="13" /></button></div><div class="inspector-section"><div class="inspector-section-title">沙箱运行时 <span class="runtime-pill">隔离中</span></div><div class="runtime-card"><div class="runtime-card-top"><span class="runtime-terminal"><Terminal :size="14" /></span><strong>docker / runtime-7f2a</strong><MoreHorizontal :size="15" /></div><div class="runtime-card-detail"><span>CPU</span><strong>1.4 / 2 vCPU</strong><div><i style="width: 70%"></i></div></div><div class="runtime-card-detail"><span>内存</span><strong>2.1 / 4 GB</strong><div><i style="width: 52%"></i></div></div><div class="runtime-card-footer"><span>启动于 14:32:41</span><button @click="selectSection('machines')">节点详情</button></div></div></div><div class="inspector-section cost-section"><div class="inspector-section-title">用量与成本 <button class="text-action" @click="notify('打开本月用量报表')">今日报表</button></div><div class="cost-row"><span>Input tokens</span><strong>14,280</strong></div><div class="cost-row"><span>Output tokens</span><strong>4,120</strong></div><div class="cost-row"><span>模型费用估算</span><strong>$0.042</strong></div><div class="budget-line"><span>运行预算 <strong>$0.20</strong></span><span>21%</span></div><div class="budget-track"><i></i></div></div><div class="inspector-section policy-section"><div class="inspector-section-title">策略检查</div><div class="policy-line"><Check :size="14" /><span>工具权限在允许范围内</span></div><div class="policy-line"><Check :size="14" /><span>工作空间隔离已启用</span></div><div class="policy-line"><ShieldCheck :size="14" /><span>写入操作需要人工批准</span></div></div></aside>
          </section>

          <section class="machine-section"><div class="section-title-row"><div><h2>执行节点</h2><span>本地与远端 Agent Runtime 的容量和健康状态</span></div><button class="text-action" @click="selectSection('machines')">管理机器 <ArrowRight :size="13" /></button></div><div class="machine-table"><div class="machine-header"><span>节点</span><span>运行时</span><span>状态</span><span>并发槽位</span><span>最近心跳</span><span>版本</span></div><div class="machine-row"><strong><i class="machine-led"></i>local-dev</strong><span>Docker · Windows</span><span><i class="health-mini"></i>在线</span><span>2 <small>/ 4</small><i class="slot-track"><i style="width:50%"></i></i></span><span>刚刚</span><span>runtime 0.14.2</span></div><div class="machine-row"><strong><i class="machine-led"></i>gpu-worker-01</strong><span>Remote · Linux</span><span><i class="health-mini"></i>在线</span><span>1 <small>/ 2</small><i class="slot-track"><i style="width:50%"></i></i></span><span>8 秒前</span><span>runtime 0.14.1</span></div><div class="machine-row machine-muted"><strong><i class="machine-led offline"></i>ci-runner</strong><span>Container · Linux</span><span><i class="health-mini offline"></i>离线</span><span>0 <small>/ 8</small><i class="slot-track"><i style="width:0"></i></i></span><span>6 分钟前</span><span>runtime 0.13.8</span></div></div></section>
          <footer class="page-footer"><span>Harness 控制面 · 本地演示运行数据</span><span><i class="footer-health demo-health"></i>界面交互有效，未连接执行后端</span><span>示例时间戳</span></footer>
        </template>
        <section v-else class="module-page">
          <div class="module-toolbar"><div class="module-tabs"><button class="module-tab" :class="{ active: moduleTab === 'catalog' }" @click="selectModuleTab('catalog')">资源目录</button><button class="module-tab" :class="{ active: moduleTab === 'runs' }" @click="selectModuleTab('runs')">运行关联</button><button class="module-tab" :class="{ active: moduleTab === 'changes' }" @click="selectModuleTab('changes')">变更记录</button></div><label class="module-search"><Search :size="14" /><input v-model="search" :placeholder="`搜索${navTitle}`" /></label><select v-model="moduleStateFilter" class="module-filter" aria-label="按状态筛选"><option>全部状态</option><option v-for="state in [...new Set(sectionRecords(activeSection).map(row => row.state))]" :key="state">{{ state }}</option></select><button class="button button-primary" @click="notify(`${navTitle}创建流程：当前为演示界面`)"><Plus :size="14" />新建{{ navTitle.replace('实例', '') }}</button></div>
          <div class="module-kpis"><div><span>资源总数</span><strong>{{ sectionRecords(activeSection).length }}</strong><small>当前演示目录</small></div><div><span>可用 / 已启用</span><strong>{{ sectionRecords(activeSection).filter(row => ['可用', '已启用', '在线', '已配置', '已生成'].includes(row.state)).length }}</strong><small>状态正常</small></div><div><span>需要关注</span><strong class="module-kpi-warn">{{ sectionRecords(activeSection).filter(row => ['待审批', '草稿', '未连接', '离线', '待处理'].includes(row.state)).length }}</strong><small>待处理或未连接</small></div><div><span>最近更新</span><strong class="module-kpi-time">14:33</strong><small>示例时间</small></div></div>
          <div class="module-content-grid"><section class="module-table-panel"><div class="module-table-heading"><div><h2>{{ sectionSummary(activeSection)[0] }}{{ moduleTab === 'catalog' ? '目录' : moduleTab === 'runs' ? '运行关联' : '变更记录' }}</h2><span>{{ filteredModuleRows.length }} 条演示记录 · {{ moduleTab === 'catalog' ? '展示资源结构' : moduleTab === 'runs' ? '按运行、调用和活动筛选' : '按配置变更和异常状态筛选' }}</span></div><button class="icon-action" title="导出当前记录" @click="notify('当前筛选记录已准备导出')"><ArrowDownToLine :size="15" /></button></div><div class="module-table"><div class="module-table-head"><span>名称 / 标识</span><span>类型 / 来源</span><span>最近活动</span><span>状态</span><span></span></div><button v-for="row in filteredModuleRows" :key="row.name" class="module-table-row" @click="openModuleRecord(row)"><span class="module-primary-cell"><i class="module-item-icon"><component :is="sections.flatMap(group => group.items).find(item => item.id === activeSection)?.icon || Boxes" :size="16" /></i><span><strong>{{ row.name }}</strong><small>{{ row.detail || row.name }}</small></span></span><span class="module-cell"><strong>{{ row.type }}</strong><small>{{ row.owner }}</small></span><span class="module-cell activity-cell">{{ row.activity }}</span><span class="module-state" :class="{ warning: ['待审批', '需审批', '草稿', '未连接', '待处理'].includes(row.state), offline: row.state === '离线' }"><i></i>{{ row.state }}</span><ArrowRight :size="14" class="module-row-arrow" /></button><div v-if="!filteredModuleRows.length" class="module-empty"><Search :size="18" /><strong>当前视图没有匹配记录</strong><button @click="search = ''; moduleStateFilter = '全部状态'; moduleTab = 'catalog'">重置视图和筛选</button></div></div><div class="module-table-footer"><span>数据来源：Harness 规划演示集</span><span>变更与运行时状态尚未持久化</span></div></section>
            <aside class="module-side-panel"><template v-if="selectedModuleRecord"><div class="module-side-heading"><button class="module-back" @click="selectedModuleRecord = null">← {{ navTitle }}</button><span class="module-detail-state">{{ selectedModuleRecord.state }}</span></div><h2 class="module-detail-title">{{ selectedModuleRecord.name }}</h2><p>{{ selectedModuleRecord.detail }}</p><div class="module-side-section"><strong>资源属性</strong><div class="module-detail-field"><span>类型</span><b>{{ selectedModuleRecord.type }}</b></div><div class="module-detail-field"><span>来源 / 负责人</span><b>{{ selectedModuleRecord.owner }}</b></div><div class="module-detail-field"><span>最近活动</span><b>{{ selectedModuleRecord.activity }}</b></div><div class="module-detail-field"><span>数据状态</span><b>本地演示数据</b></div></div><div class="module-side-section"><strong>关联操作</strong><button class="module-related-link" @click="selectModuleTab('runs')">查看运行关联 <ArrowRight :size="13" /></button><button class="module-related-link" @click="selectModuleTab('changes')">查看变更记录 <ArrowRight :size="13" /></button></div><div class="module-side-note"><ShieldCheck :size="15" /><span>详情只读，修改操作需要接入后端 API。</span></div></template><template v-else><div class="module-side-heading"><h2>{{ navTitle }}概览</h2><span>演示</span></div><p>{{ sectionSummary(activeSection)[1] }}</p><div class="module-side-section"><strong>当前关注</strong><button v-for="row in sectionRecords(activeSection).filter(item => ['待审批', '需审批', '草稿', '未连接', '离线', '待处理'].includes(item.state))" :key="row.name" class="module-attention" @click="openModuleRecord(row)"><span class="attention-led"></span><span><b>{{ row.name }}</b><small>{{ row.state }} · {{ row.activity }}</small></span></button><div v-if="!sectionRecords(activeSection).some(item => ['待审批', '需审批', '草稿', '未连接', '离线', '待处理'].includes(item.state))" class="module-no-attention"><Check :size="14" />当前没有待处理项</div></div><div class="module-side-section"><strong>此模块包含</strong><ul><li>资源与版本登记</li><li>运行关联和最近活动</li><li>状态、风险与可用性摘要</li></ul></div><div class="module-side-note"><ShieldCheck :size="15" /><span>页面内容为本地演示数据。执行控制 API 接入后，资源状态将由后端提供。</span></div></template></aside></div>
          <footer class="page-footer"><span>Harness 控制面 · {{ navTitle }}规划视图</span><span><i class="footer-health demo-health"></i>演示数据 · 未连接运行 API</span><span>更新时间 14:33</span></footer>
        </section>
      </div></div>
      <div v-if="toast" class="toast-message"><Check :size="15" />{{ toast }}</div>
    </main>
  </div>
</template>
