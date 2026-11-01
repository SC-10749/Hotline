<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { Activity, Archive, ArrowDownToLine, ArrowRight, Bot, Boxes, Brain, Check, ChevronLeft, ChevronRight, CircleHelp, Clock3, Command, Cpu, Database, FileText, Filter, FlaskConical, HardDrive, Home, Layers3, ListChecks, LockKeyhole, Menu, Network, Pause, Play, Plus, Repeat2, Search, Shield, ShieldCheck, Sparkles, Square, Terminal, Workflow, Wrench, X } from 'lucide-vue-next'
import ObservatoryPage from './components/ObservatoryPage.vue'
import TaskOrchestrationPage from './components/TaskOrchestrationPage.vue'
import AgentInstancesPage from './components/AgentInstancesPage.vue'
import WorkspaceBoundaryPage from './components/WorkspaceBoundaryPage.vue'
import ToolsMcpPage from './components/ToolsMcpPage.vue'
import ContextEngineeringPage from './components/ContextEngineeringPage.vue'
import MemoryStatePage from './components/MemoryStatePage.vue'
import SkillsRegistryPage from './components/SkillsRegistryPage.vue'
import ModelRoutingPage from './components/ModelRoutingPage.vue'
import ExecutionIsolationPage from './components/ExecutionIsolationPage.vue'
import HarnessGovernancePages from './components/HarnessGovernancePages.vue'

const sections = [
  { label: '控制平面', items: [{ id: 'overview', label: '运行总览', icon: Activity }, { id: 'runs', label: '运行状态', icon: ListChecks, count: '12' }, { id: 'agents', label: '智能体实例', icon: Bot, count: '7' }, { id: 'workspaces', label: '工作空间', icon: Layers3, count: '6' }] },
  { label: '能力注册表', items: [{ id: 'tools', label: '工具与 MCP', icon: Wrench, count: '18' }, { id: 'context', label: '上下文工程', icon: Brain, count: '9' }, { id: 'memory', label: '记忆与状态', icon: Database, count: '3' }, { id: 'skills', label: '技能', icon: Sparkles, count: '23' }, { id: 'models', label: '模型路由', icon: Network, count: '5' }] },
  { label: '运行治理', items: [{ id: 'execution', label: '执行隔离', icon: LockKeyhole, count: '3' }, { id: 'machines', label: '机器与运行时', icon: Cpu, count: '3' }, { id: 'approvals', label: '待审批', icon: ShieldCheck, count: '2' }, { id: 'governance', label: '治理策略', icon: Shield }, { id: 'verification', label: '验证与评估', icon: FlaskConical }, { id: 'lifecycle', label: '生命周期', icon: Repeat2 }, { id: 'artifacts', label: '产物与存储', icon: Archive }, { id: 'observability', label: '追踪与日志', icon: Terminal }] },
]
const themeOptions = [
  { key: 'coral', label: '珊瑚', swatch: '#c96345', accent: '#c96345', accentStrong: '#a64d33', accentHover: '#ad5438', accentLine: '#e5b5a5', accentSoft: '#fbede8', activeSoft: '#f8e8e2', obsAccent: '#f27f5f', obsAccentSoft: 'rgba(242,127,95,.14)', obsAccentLine: 'rgba(242,127,95,.3)' },
  { key: 'blue', label: '海蓝', swatch: '#5269d9', accent: '#5269d9', accentStrong: '#4051b5', accentHover: '#475bc7', accentLine: '#b8c1f1', accentSoft: '#eef0ff', activeSoft: '#e9ecff', obsAccent: '#6d8cff', obsAccentSoft: 'rgba(109,140,255,.14)', obsAccentLine: 'rgba(109,140,255,.3)' },
  { key: 'violet', label: '紫晶', swatch: '#8b5cf6', accent: '#8b5cf6', accentStrong: '#6d3ed6', accentHover: '#7b48e8', accentLine: '#d4c2fb', accentSoft: '#f1ebff', activeSoft: '#eee7ff', obsAccent: '#a78bfa', obsAccentSoft: 'rgba(167,139,250,.14)', obsAccentLine: 'rgba(167,139,250,.3)' },
  { key: 'teal', label: '青绿', swatch: '#0d9488', accent: '#0d9488', accentStrong: '#0f766e', accentHover: '#0b8278', accentLine: '#a6ded8', accentSoft: '#e4f7f5', activeSoft: '#ddf3f0', obsAccent: '#2dd4a7', obsAccentSoft: 'rgba(45,212,167,.14)', obsAccentLine: 'rgba(45,212,167,.3)' },
  { key: 'amber', label: '琥珀', swatch: '#c27a18', accent: '#c27a18', accentStrong: '#9a5e0e', accentHover: '#aa670f', accentLine: '#efd09b', accentSoft: '#fff2d8', activeSoft: '#ffefd0', obsAccent: '#f5b945', obsAccentSoft: 'rgba(245,185,69,.14)', obsAccentLine: 'rgba(245,185,69,.3)' },
]
const emit = defineEmits(['exit'])
const governanceSections = ['machines', 'approvals', 'governance', 'verification', 'lifecycle', 'artifacts', 'observability']
const runs = ref([
  { id: 'RUN-2048', title: '梳理客服工单中的退款异常', workspace: '客服运营 / 主分支', agent: '客服分析助手', model: 'Claude Sonnet 4', status: 'running', elapsed: '02:41', tokens: '18.4k', cost: '$0.042', progress: 68, phase: '正在归纳 24 条关联工单' },
  { id: 'RUN-2047', title: '为知识库补充接口错误码说明', workspace: '产品文档 / 接口说明分支', agent: '文档编写助手', model: 'GPT-5', status: 'running', elapsed: '01:18', tokens: '9.2k', cost: '$0.019', progress: 42, phase: '等待浏览器页面验证' },
  { id: 'RUN-2046', title: '检查本周自动化任务失败原因', workspace: '智能体平台 / 主分支', agent: '平台运维助手', model: 'DeepSeek V3.2', status: 'queued', elapsed: '等待中', tokens: '—', cost: '—', progress: 0, phase: '排队中 · 预计 00:34' },
  { id: 'RUN-2045', title: '生成工单分类规则回归测试', workspace: '客服运营 / 规则第二版', agent: '质量测试助手', model: 'Claude Sonnet 4', status: 'running', elapsed: '04:06', tokens: '31.7k', cost: '$0.071', progress: 86, phase: '正在执行 12 项回归检查' },
])
const persistedSection = window.localStorage.getItem('hotline-harness-section')
const requestedSection = new URLSearchParams(window.location.search).get('section')
const legacyInstanceRoute = ['/instances', '/bot'].includes(window.location.pathname)
const initialSection = sections.some(group => group.items.some(item => item.id === requestedSection)) ? requestedSection : legacyInstanceRoute ? 'agents' : persistedSection
const activeSection = ref(sections.some(group => group.items.some(item => item.id === initialSection)) ? initialSection : 'overview')
const activeView = ref('control')
const filter = ref('全部任务')
const search = ref('')
const moduleTab = ref('catalog')
const moduleStateFilter = ref('全部状态')
const selectedModuleRecord = ref(null)
const selectedRunId = ref('RUN-2048')
const toast = ref('')
const mobileNavOpen = ref(false)
const sidebarCollapsed = ref(false)
const themeMenuOpen = ref(false)
const themeKey = ref('coral')
const pageScroll = ref(null)
const running = ref(true)
const activeTheme = computed(() => themeOptions.find(theme => theme.key === themeKey.value) || themeOptions[0])
const themeStyle = computed(() => ({
  '--h-accent': activeTheme.value.accent,
  '--h-accent-strong': activeTheme.value.accentStrong,
  '--h-accent-hover': activeTheme.value.accentHover,
  '--h-accent-line': activeTheme.value.accentLine,
  '--h-accent-soft': activeTheme.value.accentSoft,
  '--h-active-soft': activeTheme.value.activeSoft,
}))
const sectionMode = computed(() => ['overview', 'runs', 'agents', 'workspaces', 'tools', 'context', 'memory', 'skills', 'models', 'execution'].includes(activeSection.value) ? 'demo' : 'planned')
const sourceLabel = computed(() => activeSection.value === 'agents' ? '本地演示实例' : activeSection.value === 'workspaces' ? '本地演示工作区' : activeSection.value === 'tools' ? '本地演示工具目录' : activeSection.value === 'context' ? '本地演示上下文' : activeSection.value === 'memory' ? '本地演示记忆与状态' : activeSection.value === 'skills' ? '本地演示技能目录' : activeSection.value === 'models' ? '本地演示模型路由' : activeSection.value === 'execution' ? '本地演示隔离状态' : ['overview', 'runs'].includes(activeSection.value) ? '演示运行数据' : '规划数据 · 尚未接入运行接口')
const selectedRun = computed(() => runs.value.find(run => run.id === selectedRunId.value) || runs.value[0])
const visibleRuns = computed(() => runs.value.filter(run => {
  const filterMatch = filter.value === '全部任务' || (filter.value === '运行中' ? run.status === 'running' : filter.value === '排队中' ? run.status === 'queued' : run.status === 'failed')
  return filterMatch && `${run.id} ${run.title} ${run.agent}`.toLowerCase().includes(search.value.toLowerCase())
}))
const navTitle = computed(() => sections.flatMap(group => group.items).find(item => item.id === activeSection.value)?.label || '运行总览')
const pageHeading = computed(() => activeSection.value === 'overview' ? '运行控制台' : navTitle.value)

onMounted(() => {
  themeKey.value = window.localStorage.getItem('hotline-harness-theme') || 'coral'
})
watch(themeKey, value => {
  window.localStorage.setItem('hotline-harness-theme', value)
})
watch(activeSection, value => {
  window.localStorage.setItem('hotline-harness-section', value)
  nextTick(() => {
    if (pageScroll.value) pageScroll.value.scrollTop = 0
  })
})

function notify(message) {
  toast.value = message
  window.clearTimeout(notify.timer)
  notify.timer = window.setTimeout(() => { toast.value = '' }, 2600)
}
function createRun() {
  const id = `RUN-${2049 + runs.value.length - 4}`
  runs.value.unshift({ id, title: '新建智能体执行任务', workspace: '客服运营 / 主分支', agent: '通用执行助手', model: '自动选择', status: 'queued', elapsed: '等待中', tokens: '—', cost: '—', progress: 0, phase: '排队中 · 等待运行资源' })
  selectedRunId.value = id
  activeSection.value = 'runs'
  activeView.value = 'control'
  notify(`${id} 已加入执行队列`)
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
    runs: ['运行状态', '集中查看正在执行、排队等待和最近完成的运行任务。每次运行都保留智能体、模型、工作空间和执行轨迹。', ['RUN-2048 · 梳理客服工单中的退款异常 · 执行中', 'RUN-2047 · 为知识库补充 API 错误码说明 · 执行中', 'RUN-2046 · 检查本周自动化任务失败原因 · 排队中', 'RUN-2045 · 生成工单分类规则回归测试 · 执行中']],
    agents: ['智能体实例', '4 个智能体配置正在工作空间中执行。每个实例绑定独立的模型路由、工具权限和运行策略。', ['客服分析助手 · 版本 1.8 · 运行中', '文档编写助手 · 版本 2.1 · 运行中', '平台运维助手 · 版本 1.3 · 空闲', '质量测试助手 · 版本 1.4 · 运行中']],
    workspaces: ['工作空间', '每次运行使用独立工作目录与会话快照。代码分支、文件变更和运行历史均可追溯。', ['客服运营 · 主分支 · 运行 2 项', '产品文档 · 接口说明分支 · 运行 1 项', '智能体平台 · 主分支 · 空闲', '客服运营 · 规则第二版 · 运行 1 项']],
    tools: ['工具与 MCP', '统一管理 MCP、内置工具与工具发现策略。工具按需开放，接口结构会在注册和调用前校验，避免把整套工具清单塞进每次上下文。', ['工具检索 · 按任务查找', '知识查询 · 只读 · 接口已校验', '更新客服工单 · 需要审批 · 按需加载', '浏览器操作 · 内置工具 · 限于隔离环境']],
    context: ['上下文工程', '管理上下文预算、压缩策略、缓存和技能注入。长任务接近窗口上限时会显式压缩，避免质量悄然下降。', ['默认压缩策略 · 使用量达到 72% 时触发', '结构化笔记 · 每 8 轮整理一次', '前缀缓存 · 系统指令与策略 · 命中率 84%', '技能注入 · 按任务检索 · 4 个片段']],
    memory: ['记忆与状态', '区分会话工作记忆、文件记忆和跨会话长期记忆。每条记忆都标注来源、适用范围、更新时间与删除边界。', ['会话状态 · 运行 RUN-2048 · 18 个字段', '文件记忆 · 工作空间笔记 · 当前空间可见', '长期记忆 · 客服运营 · 已整理 126 条']],
    skills: ['技能目录', '可组合的任务能力包。技能版本随每次运行记录，变更后可比较行为和调用轨迹。', ['客服问题分流 · 版本 1.8 · 已启用', '接口文档编写 · 版本 2.1 · 已启用', '发布前检查 · 版本 1.3 · 草稿', '退款分析 · 版本 1.2 · 已启用']],
    models: ['模型路由', '按任务类型、成本上限和可用性选择模型。每次路由决策都会记录原因和实际用量。', ['Claude Sonnet 4 · 默认 · 可用', 'GPT-5 · 文档任务 · 可用', 'DeepSeek V3.2 · 低成本队列 · 可用', '本地模型 · 私有任务 · 未连接']],
    execution: ['执行隔离', '把沙箱、凭据、网络出口和文件系统边界设为运行策略。高风险能力会在启动前按最小权限原则计算。', ['隔离环境 7f2a · 容器运行 · 已隔离', '网络出口策略 · 仅允许访问 MCP 代理 · 3 条规则', '凭据通道 · 通过标准输入注入 · 禁止转储', '工作空间挂载 · 禁止访问 Git 元数据 · 只读基线']],
    machines: ['机器与运行时', '管理本地与远端执行节点，查看容量、隔离方式、版本和心跳。以下为演示数据。', ['本地开发机 · 容器 · 空闲 2 / 4', '图形处理节点 01 · 远程机器 · 空闲 1 / 2', '持续集成节点 · 容器 · 空闲 0 / 8']],
    approvals: ['待审批', '高影响工具调用会在执行前暂停，审批决定、操作者与执行结果都会写入审计记录。', ['RUN-2048 · 更新客服工单 · 影响 3 条记录', 'RUN-2043 · 修改文件 · 涉及 2 个文件']],
    governance: ['治理策略', '将逐次审批沉淀为可审计的 standing rules，并用 guardrails 约束输入、输出和工具调用。规则按工具风险、工作空间和操作者作用域匹配。', ['read-only.auto-approve · 只读工具 · 自动批准', 'crm.write.review · 外部写入 · 每次审批', 'support-ops.standing-rule · 维护者可批准 · 30 天', 'output.guardrail · PII 检测 · 阻断并记录']],
    verification: ['验证与评估', '把 Agent 行为当作软件做回归：黄金数据集、录制回放、轨迹评分和 CI 门禁共享同一套运行证据。', ['refund-triage-golden · 48 cases · 96.4%', 'RUN-2045 replay · 12 steps · 可重放', 'trajectory-judge · policy + evidence · 通过', 'ci-gate / main · 3 checks · 待接入']],
    lifecycle: ['生命周期', '从规划、排队、执行到终止和恢复统一管理。后台运行、终止条件、断点恢复与 handoff 都留下可追踪的状态转换。', ['RUN-2048 · 执行中 · 终止条件 2 / 3', 'background-agent · nightly-triage · 已排程', 'checkpoint-2048-17 · 可恢复 · 14:33:08', 'handoff · analyst → verifier · 待触发']],
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
  if (id === 'context') return rows.map((row, index) => ({ ...row, type: ['压缩策略', '结构化笔记', '上下文缓存', '技能注入'][index], owner: ['Context Engine', 'Memory bridge', 'Prompt cache', 'Skills registry'][index], activity: ['最近触发于 RUN-2048 · 72%', '最近巩固 14:28:16', '命中率 84% · 今日 126 次', '最近注入 4 个片段'][index], state: index === 2 ? '已启用' : index === 3 ? '按需' : '已配置' }))
  if (id === 'memory') return rows.map((row, index) => ({ ...row, type: ['会话状态', '文件记忆', '长期记忆'][index], owner: ['RUN-2048', 'support-ops / main', 'support-ops'][index], activity: ['18 个字段 · 2 分钟前', 'notes.md · 14:28:16', '巩固 126 条 · 昨日'][index], state: index === 2 ? '已巩固' : '可用' }))
  if (id === 'skills') return rows.map((row, index) => ({ ...row, type: '任务技能', owner: ['Support Ops', 'Docs Platform', 'Platform QA', 'Support Ops'][index], activity: ['最近用于 RUN-2048', '最近用于 RUN-2047', '尚未发布', '最近用于 RUN-2048'][index], state: index === 2 ? '草稿' : '已启用' }))
  if (id === 'models') return rows.map((row, index) => ({ ...row, type: ['默认路由', '任务路由', '成本路由', '私有路由'][index], owner: ['通用任务', '文档任务', '低成本队列', '私有任务'][index], activity: ['延迟 1.84s · 今日 18 次', '延迟 2.12s · 今日 9 次', '延迟 1.31s · 今日 6 次', '等待连接配置'][index], state: index === 3 ? '未连接' : '可用' }))
  if (id === 'execution') return rows.map((row, index) => ({ ...row, type: ['容器沙箱', '网络出口策略', '凭据通道', '文件系统挂载'][index], owner: ['runtime-7f2a', 'egress proxy', 'secret broker', 'workspace mount'][index], activity: ['运行中 · 2.1 / 4 GB', '3 条 allowlist · 0 次越界', 'stdin 注入 · 0 个环境变量', '只读基线 · .git 已屏蔽'][index], state: index === 1 ? '受限' : '已隔离' }))
  if (id === 'machines') return rows.map((row, index) => ({ ...row, type: ['Docker · Windows', 'Remote · Linux', 'Container · Linux'][index], owner: ['本地开发机', 'GPU 执行池', 'CI 执行池'][index], activity: ['心跳刚刚 · 2 / 4 槽位', '心跳 8 秒前 · 1 / 2 槽位', '心跳 6 分钟前 · 0 / 8 槽位'][index], state: index === 2 ? '离线' : '在线' }))
  if (id === 'approvals') return rows.map((row, index) => ({ ...row, type: index ? '文件变更' : '外部写入', owner: index ? 'filesystem.patch' : 'crm.ticket.update', activity: index ? '修改 2 个文件 · RUN-2043' : '影响 3 条记录 · RUN-2048', state: '待审批' }))
  if (id === 'governance') return rows.map((row, index) => ({ ...row, type: ['自动批准规则', '工具策略', 'Standing rule', '输出护栏'][index], owner: ['read-only tools', 'CRM MCP', 'support-ops', 'PII detector'][index], activity: ['命中 24 次 · 最近 14:32', '阻断 1 次 · 最近 14:33', '有效期至 11-30', '扫描 18 次 · 0 漏放'][index], state: index === 1 ? '需审批' : index === 2 ? '已启用' : '已配置' }))
  if (id === 'verification') return rows.map((row, index) => ({ ...row, type: ['黄金数据集', '录制回放', '轨迹评分', 'CI 门禁'][index], owner: ['refund-triage', 'RUN-2045', 'policy judge', 'main branch'][index], activity: ['48 cases · 96.4%', '12 steps · 3 个断言', '证据完整度 0.91', '等待接入 runner'][index], state: index === 3 ? '未连接' : index === 1 ? '可重放' : '通过' }))
  if (id === 'lifecycle') return rows.map((row, index) => ({ ...row, type: ['运行状态机', '后台 Agent', '断点检查点', 'Handoff'][index], owner: ['RUN-2048', 'nightly-triage', 'RUN-2048', 'analyst / verifier'][index], activity: ['执行中 · 终止条件 2 / 3', '每晚 02:00 · 下次 6 小时后', 'step 17 · 14:33:08', '等待验证器空闲'][index], state: index === 3 ? '待处理' : index === 1 ? '已排程' : '可恢复' }))
  if (id === 'artifacts') return rows.map((row, index) => ({ ...row, type: ['结构化结果', '代码补丁', '测试报告'][index], owner: ['4.2 KB · JSON', '2.1 KB · PATCH', '86 KB · HTML'][index], activity: ['生成于 14:33:09', '生成于 14:27:31', '生成于 14:12:04'][index], state: '已生成' }))
  if (id === 'observability') return rows.map((row, index) => ({ ...row, type: ['模型调用', 'MCP 调用', '治理事件', '产物事件'][index], owner: ['RUN-2048 · Claude Sonnet 4', 'RUN-2048 · knowledge.search', 'RUN-2048 · approval.wait', 'RUN-2048 · artifact.write'][index], activity: ['14:32:44 · 1.84 秒', '14:32:44 · 0.32 秒', '14:33:06 · 等待 48 秒', '14:33:09 · 0.08 秒'][index], state: index === 2 ? '待处理' : '已记录' }))
  return rows.map(row => ({ ...row, type: '运行策略', owner: '本地演示配置', activity: '修改后仅影响后续新建运行', state: '草案' }))
}
function moduleScope(id) {
  const scopes = {
    tools: ['工具目录与来源', '按需发现与渐进披露', 'Schema 校验与风险等级'],
    context: ['上下文预算与压缩', '结构化笔记与缓存', '技能注入与版本快照'],
    memory: ['会话工作记忆', '文件记忆与作用域', '跨会话长期记忆'],
    execution: ['沙箱与工作区隔离', '凭据与网络出口', '终止、清理与资源回收'],
    governance: ['审批与 standing rules', '输入 / 输出 / 工具护栏', '审计、策略版本与生效范围'],
    verification: ['黄金数据集与断言', '录制回放与轨迹评分', 'CI 门禁与回归趋势'],
    lifecycle: ['规划、待办与运行模式', '后台 Agent 与终止条件', 'checkpoint、恢复与 handoff'],
  }
  return scopes[id] || ['资源与版本登记', '运行关联和最近活动', '状态、风险与可用性摘要']
}
</script>

<template>
  <div class="harness-shell" :class="{ 'sidebar-collapsed': sidebarCollapsed, 'governance-console': governanceSections.includes(activeSection) }" :style="themeStyle" @click="themeMenuOpen = false">
    <div v-if="mobileNavOpen" class="mobile-scrim" @click="mobileNavOpen = false"></div>
    <aside class="harness-sidebar" :class="{ 'is-open': mobileNavOpen }">
      <div class="brand-lockup"><button class="harness-brand-home" type="button" aria-label="返回 Hotline" title="返回 Hotline" @click="emit('exit')"><div class="brand-symbol"><Workflow :size="18" :stroke-width="2" /></div><div class="brand-copy"><strong>HOTLINE</strong><span>智能体控制台</span></div></button><button class="close-mobile" aria-label="关闭导航" @click="mobileNavOpen = false"><X :size="17" /></button></div>
      <button class="sidebar-collapse" aria-label="收缩工具栏" title="收缩工具栏" @click="sidebarCollapsed = true"><ChevronLeft :size="15" /></button>
      <nav class="side-navigation" aria-label="Harness 导航"><div v-for="group in sections" :key="group.label" class="nav-group"><div class="nav-group-label">{{ group.label }}</div><button v-for="item in group.items" :key="item.id" class="nav-link" :class="{ active: activeSection === item.id }" @click="selectSection(item.id)"><component :is="item.icon" :size="16" :stroke-width="1.8" /><span>{{ item.label }}</span><small v-if="item.count">{{ item.count }}</small></button></div></nav>
      <div class="sidebar-bottom"><div class="user-row"><button class="user-avatar-button" type="button" aria-label="打开 Codex 主题设置" :aria-expanded="themeMenuOpen" @click.stop="themeMenuOpen = !themeMenuOpen"><span class="user-avatar">SC</span></button><div class="user-copy"><strong>Song Chen</strong><small>管理员</small></div><CircleHelp :size="16" /><div v-if="themeMenuOpen" class="theme-popover" @click.stop><div class="theme-popover-head"><span class="codex-mark">⌘</span><div><strong>Codex</strong><small>主题颜色</small></div></div><div class="theme-options"><button v-for="theme in themeOptions" :key="theme.key" type="button" class="theme-option" :class="{ active: themeKey === theme.key }" @click="themeKey = theme.key"><span class="theme-swatch" :style="{ background: theme.swatch }"></span><span>{{ theme.label }}</span><i v-if="themeKey === theme.key">✓</i></button></div></div></div></div>
    </aside>

    <main class="main-surface">
      <button v-if="sidebarCollapsed" class="sidebar-expand" aria-label="展开工具栏" title="展开工具栏" @click="sidebarCollapsed = false"><ChevronRight :size="15" /></button>
      <header class="topbar"><button class="mobile-menu" aria-label="打开导航" @click="mobileNavOpen = true"><Menu :size="19" /></button><div class="breadcrumbs"><button class="harness-back" type="button" @click="emit('exit')"><Home :size="15" /> Hotline</button><span class="crumb-slash">/</span><strong>{{ navTitle }}</strong></div><div class="topbar-actions"><span class="demo-label" :class="{ planned: sectionMode === 'planned' }"><span></span>{{ sourceLabel }}</span><button class="top-icon" aria-label="搜索" title="搜索" @click="$refs.searchField?.focus()"><Search :size="16" /></button><button class="command-shortcut" @click="$refs.searchField?.focus()"><Command :size="13" />快速查找<kbd>Ctrl K</kbd></button><button class="avatar-small" aria-label="个人账户">SC</button></div></header>
      <div ref="pageScroll" class="page-scroll"><div class="page-content">
      <div v-if="!['overview', 'runs', 'agents', 'workspaces', 'tools', 'context', 'memory', 'skills', 'models', 'execution', ...governanceSections].includes(activeSection)" class="page-heading-row"><div><h1>{{ pageHeading }}</h1><p>{{ sectionSummary(activeSection)[1] }}</p></div><div class="heading-actions"><button class="button button-subtle refresh-button" title="刷新状态" aria-label="刷新状态" @click="notify('已刷新本地演示状态')"><Activity :size="15" /><span>刷新状态</span></button><button class="button button-primary" @click="createRun"><Plus :size="16" />新建运行</button></div></div>

        <div v-if="sectionMode === 'planned' && !governanceSections.includes(activeSection)" class="planned-notice"><div class="planned-mark"><ShieldCheck :size="18" /></div><div><strong>{{ navTitle }}尚未接入运行控制 API</strong><span>当前展示规划范围和待接入状态。接入后此处会显示来自后端的实时资源、版本与审计数据。</span></div><span class="planned-badge">目标模块 · {{ activeSection }}</span></div>
        <ObservatoryPage v-if="activeSection === 'overview'" :theme-accent="activeTheme.obsAccent" :theme-accent-soft="activeTheme.obsAccentSoft" :theme-accent-line="activeTheme.obsAccentLine" />
        <TaskOrchestrationPage v-else-if="activeSection === 'runs'" />
        <AgentInstancesPage v-else-if="activeSection === 'agents'" />
        <WorkspaceBoundaryPage v-else-if="activeSection === 'workspaces'" />
        <ToolsMcpPage v-else-if="activeSection === 'tools'" />
        <ContextEngineeringPage v-else-if="activeSection === 'context'" />
        <MemoryStatePage v-else-if="activeSection === 'memory'" />
        <SkillsRegistryPage v-else-if="activeSection === 'skills'" @help="notify('Skills 注册表展示包结构、选择、加载与治理信息')" />
        <ModelRoutingPage v-else-if="activeSection === 'models'" @notify="notify" />
        <ExecutionIsolationPage v-else-if="activeSection === 'execution'" @notify="notify" />
        <HarnessGovernancePages v-else-if="['machines', 'approvals', 'governance', 'verification', 'lifecycle', 'artifacts', 'observability'].includes(activeSection)" :page="activeSection" @notify="notify" />
        <section v-else class="module-page">
          <div class="module-toolbar"><div class="module-tabs"><button class="module-tab" :class="{ active: moduleTab === 'catalog' }" @click="selectModuleTab('catalog')">资源目录</button><button class="module-tab" :class="{ active: moduleTab === 'runs' }" @click="selectModuleTab('runs')">运行关联</button><button class="module-tab" :class="{ active: moduleTab === 'changes' }" @click="selectModuleTab('changes')">变更记录</button></div><label class="module-search"><Search :size="14" /><input v-model="search" :placeholder="`搜索${navTitle}`" /></label><select v-model="moduleStateFilter" class="module-filter" aria-label="按状态筛选"><option>全部状态</option><option v-for="state in [...new Set(sectionRecords(activeSection).map(row => row.state))]" :key="state">{{ state }}</option></select><button class="button button-primary" @click="notify(`${navTitle}创建流程：当前为演示界面`)"><Plus :size="14" />新建{{ navTitle.replace('实例', '') }}</button></div>
          <div class="module-kpis"><div><span>资源总数</span><strong>{{ sectionRecords(activeSection).length }}</strong><small>当前演示目录</small></div><div><span>可用 / 已启用</span><strong>{{ sectionRecords(activeSection).filter(row => ['可用', '已启用', '在线', '已配置', '已生成'].includes(row.state)).length }}</strong><small>状态正常</small></div><div><span>需要关注</span><strong class="module-kpi-warn">{{ sectionRecords(activeSection).filter(row => ['待审批', '草稿', '未连接', '离线', '待处理'].includes(row.state)).length }}</strong><small>待处理或未连接</small></div><div><span>最近更新</span><strong class="module-kpi-time">14:33</strong><small>示例时间</small></div></div>
          <div class="module-content-grid"><section class="module-table-panel"><div class="module-table-heading"><div><h2>{{ sectionSummary(activeSection)[0] }}{{ moduleTab === 'catalog' ? '目录' : moduleTab === 'runs' ? '运行关联' : '变更记录' }}</h2><span>{{ filteredModuleRows.length }} 条演示记录 · {{ moduleTab === 'catalog' ? '展示资源结构' : moduleTab === 'runs' ? '按运行、调用和活动筛选' : '按配置变更和异常状态筛选' }}</span></div><button class="icon-action" title="导出当前记录" @click="notify('当前筛选记录已准备导出')"><ArrowDownToLine :size="15" /></button></div><div class="module-table"><div class="module-table-head"><span>名称 / 标识</span><span>类型 / 来源</span><span>最近活动</span><span>状态</span><span></span></div><button v-for="row in filteredModuleRows" :key="row.name" class="module-table-row" @click="openModuleRecord(row)"><span class="module-primary-cell"><i class="module-item-icon"><component :is="sections.flatMap(group => group.items).find(item => item.id === activeSection)?.icon || Boxes" :size="16" /></i><span><strong>{{ row.name }}</strong><small>{{ row.detail || row.name }}</small></span></span><span class="module-cell"><strong>{{ row.type }}</strong><small>{{ row.owner }}</small></span><span class="module-cell activity-cell">{{ row.activity }}</span><span class="module-state" :class="{ warning: ['待审批', '需审批', '草稿', '未连接', '待处理'].includes(row.state), offline: row.state === '离线' }"><i></i>{{ row.state }}</span><ArrowRight :size="14" class="module-row-arrow" /></button><div v-if="!filteredModuleRows.length" class="module-empty"><Search :size="18" /><strong>当前视图没有匹配记录</strong><button @click="search = ''; moduleStateFilter = '全部状态'; moduleTab = 'catalog'">重置视图和筛选</button></div></div><div class="module-table-footer"><span>数据来源：Harness 规划演示集</span><span>变更与运行时状态尚未持久化</span></div></section>
            <aside class="module-side-panel"><template v-if="selectedModuleRecord"><div class="module-side-heading"><button class="module-back" @click="selectedModuleRecord = null">← {{ navTitle }}</button><span class="module-detail-state">{{ selectedModuleRecord.state }}</span></div><h2 class="module-detail-title">{{ selectedModuleRecord.name }}</h2><p>{{ selectedModuleRecord.detail }}</p><div class="module-side-section"><strong>资源属性</strong><div class="module-detail-field"><span>类型</span><b>{{ selectedModuleRecord.type }}</b></div><div class="module-detail-field"><span>来源 / 负责人</span><b>{{ selectedModuleRecord.owner }}</b></div><div class="module-detail-field"><span>最近活动</span><b>{{ selectedModuleRecord.activity }}</b></div><div class="module-detail-field"><span>数据状态</span><b>本地演示数据</b></div></div><div class="module-side-section"><strong>关联操作</strong><button class="module-related-link" @click="selectModuleTab('runs')">查看运行关联 <ArrowRight :size="13" /></button><button class="module-related-link" @click="selectModuleTab('changes')">查看变更记录 <ArrowRight :size="13" /></button></div><div class="module-side-note"><ShieldCheck :size="15" /><span>详情只读，修改操作需要接入后端 API。</span></div></template><template v-else><div class="module-side-heading"><h2>{{ navTitle }}概览</h2><span>演示</span></div><p>{{ sectionSummary(activeSection)[1] }}</p><div class="module-side-section"><strong>当前关注</strong><button v-for="row in sectionRecords(activeSection).filter(item => ['待审批', '需审批', '草稿', '未连接', '离线', '待处理'].includes(item.state))" :key="row.name" class="module-attention" @click="openModuleRecord(row)"><span class="attention-led"></span><span><b>{{ row.name }}</b><small>{{ row.state }} · {{ row.activity }}</small></span></button><div v-if="!sectionRecords(activeSection).some(item => ['待审批', '需审批', '草稿', '未连接', '离线', '待处理'].includes(item.state))" class="module-no-attention"><Check :size="14" />当前没有待处理项</div></div><div class="module-side-section"><strong>此模块包含</strong><ul><li v-for="item in moduleScope(activeSection)" :key="item">{{ item }}</li></ul></div><div class="module-side-note"><ShieldCheck :size="15" /><span>页面内容为本地演示数据。执行控制 API 接入后，资源状态将由后端提供。</span></div></template></aside></div>
          <footer class="page-footer"><span>Harness 控制面 · {{ navTitle }}规划视图</span><span><i class="footer-health demo-health"></i>演示数据 · 未连接运行 API</span><span>更新时间 14:33</span></footer>
        </section>
      </div></div>
      <div v-if="toast" class="toast-message"><Check :size="15" />{{ toast }}</div>
    </main>
  </div>
</template>
