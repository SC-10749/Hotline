<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Activity, Archive, ArrowDownToLine, ArrowRight, Bot, Boxes, Check, Clock3, Command, Cpu, FileText, Filter, Gauge, GitBranch, HardDrive, Layers3, ListChecks, Menu, MoreHorizontal, Network, Pause, Play, Plus, Search, Settings2, ShieldCheck, Sparkles, Square, Terminal, Workflow, Wrench, X } from 'lucide-vue-next'
import { cancelExecutionRun, createEvaluationDataset, createEvaluationRun, getEvaluationConfig, getEvaluationDatasets, getEvaluationRuns, saveEvaluationConfig, createExecutionRun, getExecutionEvents, getExecutionRuns, getReleaseSummary, promoteRelease, evaluateReleaseGate, getReleaseGates, rollbackRelease, getHarnessAgents, createHarnessAgent, getHarnessWorkspaces, createHarnessWorkspace, getHarnessTools, getHarnessModels, getSkills, getHarnessMachines, getHarnessApprovals, decideHarnessApproval, getHarnessArtifacts, getHarnessObservabilityRuns, retryExecutionRun, getEvaluationDataset, addEvaluationCase, updateEvaluationCase } from './api'

const sections = [
  { label: '控制平面', items: [{ id: 'overview', label: '运行总览', icon: Activity }, { id: 'runs', label: '执行任务', icon: ListChecks, count: '12' }, { id: 'evaluations', label: '测评中心', icon: Gauge, count: '6' }, { id: 'agents', label: 'Agent 实例', icon: Bot, count: '4' }, { id: 'workspaces', label: '工作空间', icon: Layers3, count: '6' }] },
  { label: '能力注册表', items: [{ id: 'tools', label: '工具与 MCP', icon: Wrench, count: '18' }, { id: 'skills', label: 'Skills', icon: Sparkles, count: '23' }, { id: 'models', label: '模型路由', icon: Network, count: '5' }] },
  { label: '运行治理', items: [{ id: 'machines', label: '机器与运行时', icon: Cpu, count: '3' }, { id: 'approvals', label: '待审批', icon: ShieldCheck, count: '2' }, { id: 'artifacts', label: '产物与存储', icon: Archive }, { id: 'observability', label: '追踪与日志', icon: Terminal }, { id: 'releases', label: '发布治理', icon: GitBranch }] },
]
const props = defineProps({ embedded: { type: Boolean, default: false }, apiBase: { type: String, default: '' } })
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
const evaluationTab = ref('overview')
const selectedRunId = ref('RUN-2048')
const toast = ref('')
const mobileNavOpen = ref(false)
const running = ref(true)
const executionConnected = ref(false)
const executionLoading = ref(false)
const executionError = ref('')
const showRunDialog = ref(false)
const runDraft = ref({ conversationId: '', agent: 'chat', query: '', fileId: '' })
let executionRefreshTimer
const modulePolicies = {
  runs: { tabs: [{ id: 'catalog', label: '执行队列' }], scope: ['提交、排队、停止、重试与单次运行 Trace', 'Agent、工具、工作区和产物通过只读关联查看'] },
  agents: { tabs: [{ id: 'catalog', label: 'Agent 目录' }, { id: 'runs', label: '运行关联' }], scope: ['Agent 定义、版本、权限与运行策略', '通过 runId 只读查看实际执行'] },
  workspaces: { tabs: [{ id: 'catalog', label: '工作区目录' }, { id: 'runs', label: '运行关联' }, { id: 'changes', label: '文件变更' }], scope: ['仓库、分支、快照与文件变更', '运行只读引用工作区快照'] },
  tools: { tabs: [{ id: 'catalog', label: '工具目录' }, { id: 'runs', label: '调用关联' }, { id: 'changes', label: '策略变更' }], scope: ['工具 schema、来源、权限与审批策略', '调用结果回到运行 Trace 查看'] },
  skills: { tabs: [{ id: 'catalog', label: 'Skill 目录' }, { id: 'runs', label: '运行关联' }, { id: 'changes', label: '版本变更' }], scope: ['Skill 包、版本、启停与绑定', '质量结果只在测评中心查看'] },
  models: { tabs: [{ id: 'catalog', label: '路由目录' }, { id: 'changes', label: '路由变更' }], scope: ['提供商、路由、fallback 与成本策略', '实际用量只读关联运行记录'] },
  machines: { tabs: [{ id: 'catalog', label: '运行时节点' }], scope: ['节点注册、容量、健康与隔离', '任务状态只在执行任务查看'] },
  approvals: { tabs: [{ id: 'catalog', label: '审批队列' }], scope: ['高影响工具调用的审批决定与审计', '不编辑工具目录或运行配置'] },
  artifacts: { tabs: [{ id: 'catalog', label: '产物索引' }], scope: ['运行产物的索引、预览、下载与保留', '产物内容不修改运行配置'] },
  observability: { tabs: [{ id: 'catalog', label: 'Trace / 日志' }], scope: ['Trace、日志与指标的查询和导出', '只读观察，不负责启动或停止运行'] },
  releases: { tabs: [{ id: 'catalog', label: '发布治理' }], scope: ['Skill 版本灰度、发布、指标和回滚', '测评样本与执行任务通过只读关联查看'] },
}
const sectionMode = computed(() => ['overview', 'runs'].includes(activeSection.value) && executionConnected.value ? 'live' : activeSection.value === 'evaluations' && evaluationConnected.value ? 'live' : activeSection.value === 'releases' && releaseConnected.value ? 'live' : ['agents', 'workspaces'].includes(activeSection.value) && resourceConnected.value ? 'live' : ['overview', 'runs', 'evaluations', 'releases'].includes(activeSection.value) ? 'demo' : 'planned')
const sourceLabel = computed(() => ['overview', 'runs'].includes(activeSection.value) ? (executionConnected.value ? '实时运行数据' : '演示运行数据') : activeSection.value === 'evaluations' ? (evaluationConnected.value ? '实时测评目录 · 执行器未接入' : '演示测评数据') : activeSection.value === 'releases' ? (releaseConnected.value ? '实时发布数据' : '演示发布数据') : ['agents', 'workspaces'].includes(activeSection.value) ? (resourceConnected.value ? '实时资源目录' : '演示资源数据') : '规划数据 · 未接入运行 API')
const canCreateRun = computed(() => ['overview', 'runs'].includes(activeSection.value))
const canRefreshStatus = computed(() => ['overview', 'runs', 'evaluations', 'releases', 'agents', 'workspaces'].includes(activeSection.value))
const activeModulePolicy = computed(() => modulePolicies[activeSection.value] || { tabs: [{ id: 'catalog', label: '配置目录' }], scope: ['本模块的配置与状态', '跨模块内容通过只读关联查看'] })
const moduleScope = computed(() => activeModulePolicy.value.scope)
const moduleTabs = computed(() => activeModulePolicy.value.tabs)
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
function formatRunElapsed(run) {
  if (!run.started_at || !run.created_at) return run.status === 'queued' ? '等待中' : '—'
  const started = Date.parse(run.started_at)
  const end = run.finished_at ? Date.parse(run.finished_at) : Date.now()
  if (!Number.isFinite(started) || !Number.isFinite(end)) return '—'
  const seconds = Math.max(0, Math.round((end - started) / 1000))
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
}
function normalizeRun(run) {
  const status = run.status || 'queued'
  return {
    id: run.run_id,
    title: run.query || '未命名执行任务',
    workspace: run.file_id ? `file:${run.file_id}` : '未绑定工作空间',
    agent: run.agent || '通用执行 Agent',
    model: '由运行时路由',
    status,
    elapsed: formatRunElapsed(run),
    tokens: '—',
    cost: '—',
    progress: status === 'completed' ? 100 : status === 'running' ? 55 : 0,
    phase: status === 'queued' ? '排队 · 等待运行时资源' : status === 'running' ? '运行中 · 等待事件更新' : status === 'failed' ? `失败 · ${run.error || '请查看运行事件'}` : status === 'cancelled' ? '已取消' : '执行完成',
    raw: run,
  }
}
async function refreshExecutionRuns({ silent = false } = {}) {
  executionLoading.value = true
  try {
    const result = await getExecutionRuns(props.apiBase, { limit: 100 })
    const items = (result?.items || []).map(normalizeRun)
    runs.value = items
    executionConnected.value = true
    executionError.value = ''
    if (items.length && !items.some(run => run.id === selectedRunId.value)) selectedRunId.value = items[0].id
    if (selectedRun.value) running.value = ['queued', 'running'].includes(selectedRun.value.status)
    await refreshSelectedRunEvents()
  } catch (error) {
    executionConnected.value = false
    executionError.value = error.message || '运行服务暂不可用'
    if (!silent) notify(`运行状态刷新失败：${executionError.value}`)
  } finally {
    executionLoading.value = false
  }
}
async function refreshSelectedRunEvents() {
  if (!executionConnected.value || !selectedRun.value?.id) return
  try {
    const result = await getExecutionEvents(props.apiBase, selectedRun.value.id)
    const liveEvents = (result?.items || []).map(item => {
      const event = item.event || item
      return { time: item.created_at || new Date().toLocaleTimeString('zh-CN'), type: event.type === 'error' ? 'warning' : event.type === 'complete' ? 'success' : 'info', title: event.type === 'error' ? '运行失败' : event.type === 'complete' ? '运行完成' : '运行事件', detail: event.content || event.message || JSON.stringify(event) }
    })
    events.value = liveEvents
  } catch {
    // Keep the last visible event list when a run is between state transitions.
  }
}
function openCreateRun() {
  runDraft.value = { conversationId: `harness-${Date.now()}`, agent: 'chat', query: '', fileId: '' }
  showRunDialog.value = true
}
async function submitRun() {
  if (!runDraft.value.query.trim()) {
    notify('请输入执行任务')
    return
  }
  try {
    executionLoading.value = true
    const result = await createExecutionRun(props.apiBase, {
      conversationId: runDraft.value.conversationId.trim() || `harness-${Date.now()}`,
      agent: runDraft.value.agent,
      query: runDraft.value.query.trim(),
      fileId: runDraft.value.fileId.trim() || null,
    })
    const run = normalizeRun(result.run)
    executionConnected.value = true
    runs.value = [run, ...runs.value.filter(item => item.id !== run.id)]
    selectedRunId.value = run.id
    activeSection.value = 'runs'
    activeView.value = 'control'
    showRunDialog.value = false
    notify(`${run.id} 已加入执行队列`)
    await refreshSelectedRunEvents()
  } catch (error) {
    notify(`创建运行失败：${error.message || '运行服务不可用'}`)
  } finally {
    executionLoading.value = false
  }
}
async function stopSelectedRun() {
  if (!selectedRun.value?.id) return
  if (!executionConnected.value) {
    running.value = false
    notify(`${selectedRun.value.id} 已请求安全停止（演示状态）`)
    return
  }
  try {
    await cancelExecutionRun(props.apiBase, selectedRun.value.id)
    await refreshExecutionRuns()
    notify(`${selectedRun.value.id} 已请求安全停止`)
  } catch (error) {
    notify(`停止运行失败：${error.message || '运行服务不可用'}`)
  }
}
async function retrySelectedRun() {
  if (!selectedRun.value?.id) return
  if (!executionConnected.value) {
    openCreateRun()
    return
  }
  try {
    const result = await retryExecutionRun(props.apiBase, selectedRun.value.id)
    const run = normalizeRun(result.run)
    runs.value = [run, ...runs.value.filter(item => item.id !== run.id)]
    selectedRunId.value = run.id
    notify(`${run.id} 已重新加入执行队列`)
    await refreshSelectedRunEvents()
  } catch (error) {
    notify(`重试运行失败：${error.message || '运行服务不可用'}`)
  }
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
  if (!moduleTabs.value.some(tab => tab.id === moduleTab.value)) moduleTab.value = 'catalog'
}
function openModuleRecord(record) {
  selectedModuleRecord.value = record
}
function selectModuleTab(tab) {
  if (!moduleTabs.value.some(item => item.id === tab)) return
  moduleTab.value = tab
  moduleStateFilter.value = '全部状态'
  selectedModuleRecord.value = null
}
const demoEvalDatasets = [
  { name: '客服全链路回归集', type: '端到端', cases: '48', pass: '91.7%', delta: '+4.2%', state: '运行中', updated: '刚刚' },
  { name: '知识库问答基准集', type: 'RAG', cases: '120', pass: '88.3%', delta: '+2.8%', state: '已完成', updated: '12 分钟前' },
  { name: '工具调用正确性', type: 'Tool calling', cases: '36', pass: '94.4%', delta: '+1.6%', state: '已完成', updated: '今天 13:42' },
  { name: '多轮记忆回归集', type: 'Memory', cases: '24', pass: '83.3%', delta: '-0.9%', state: '需关注', updated: '昨天' },
]
const evalDatasets = ref(demoEvalDatasets)
const evalDimensions = [
  { label: '端到端任务完成', score: '91.7%', value: 92, color: 'green', note: '44 / 48 通过' },
  { label: 'RAG 事实一致性', score: '88.3%', value: 88, color: 'blue', note: 'Faithfulness · 0.91' },
  { label: '工具调用正确性', score: '94.4%', value: 94, color: 'orange', note: '参数准确率 · 0.97' },
  { label: '多轮记忆保持', score: '83.3%', value: 83, color: 'purple', note: '20 / 24 通过' },
]
const evalReports = ref([
  { version: 'v1.8.2', score: '89.6', date: '今天 14:33', state: '质量门禁通过' },
  { version: 'v1.8.1', score: '86.2', date: '昨天 18:10', state: '质量门禁通过' },
  { version: 'v1.8.0', score: '84.9', date: '10 月 28 日', state: '需关注' },
])
const evaluationConfig = ref({ dimensions: evalDimensions.map(item => ({ label: item.label, enabled: true })), gates: [] })
const evaluationConnected = ref(false)
const evaluationError = ref('')
const selectedEvaluationDatasetId = ref('')
const showDatasetDialog = ref(false)
const datasetDraft = ref({ name: '', datasetType: '通用', description: '' })
const selectedEvaluationDataset = ref(null)
const showCaseDialog = ref(false)
const caseDraft = ref({ caseId: '', input: '', expectedOutput: '', rubric: '{}' })
const releaseRollouts = ref([])
const releaseRuns = ref([])
const releaseMetrics = ref([])
const releaseConnected = ref(false)
const releaseError = ref('')
const releaseDraft = ref({ project: 'hotline-agent', name: '', version: '', percentage: 10 })
const releaseGateDraft = ref({ e2ePassRate: 0.917, ragFaithfulness: 0.91, highRiskErrors: 0, evalRunId: '' })
const releaseGateResult = ref(null)
const releaseGates = ref([])
const harnessAgents = ref([])
const harnessWorkspaces = ref([])
const resourceConnected = ref(false)
const resourceError = ref('')
const showAgentDialog = ref(false)
const showWorkspaceDialog = ref(false)
const agentDraft = ref({ name: '', description: '', version: 'v1', model: 'auto' })
const workspaceDraft = ref({ name: '', repository: '', branch: 'main' })
const harnessTools = ref([])
const harnessModels = ref([])
const harnessSkills = ref([])
const harnessMachines = ref([])
const harnessApprovals = ref([])
const harnessArtifacts = ref([])
const harnessTraceRuns = ref([])
const agentRows = computed(() => resourceConnected.value ? harnessAgents.value : sectionRecords('agents').map((row, index) => ({ agent_id: `demo-agent-${index}`, name: row.name, description: row.detail, version: `v${index + 1}`, model: row.owner, status: row.state })))
const workspaceRows = computed(() => resourceConnected.value ? harnessWorkspaces.value : sectionRecords('workspaces').map((row, index) => ({ workspace_id: `demo-workspace-${index}`, name: row.name, repository: row.detail, branch: 'main', status: row.state })))
const toolRows = computed(() => resourceConnected.value && harnessTools.value.length ? harnessTools.value : sectionRecords('tools').map((row, index) => ({ tool_id: `demo-tool-${index}`, name: row.name, source: row.owner, scope: row.detail, risk: row.state === '需审批' ? 'high' : 'low', status: row.state, description: row.activity })))
const modelRows = computed(() => resourceConnected.value && harnessModels.value.length ? harnessModels.value : sectionRecords('models').map((row, index) => ({ model_id: `demo-model-${index}`, name: row.name, provider: row.owner, route: row.detail, status: row.state, cost_policy: row.activity })))
const skillRows = computed(() => resourceConnected.value && harnessSkills.value.length ? harnessSkills.value : sectionRecords('skills').map((row, index) => ({ id: `demo-skill-${index}`, name: row.name, description: row.detail, sourceFile: row.owner, enabled: row.state === '已启用' })))
const machineRows = computed(() => resourceConnected.value && harnessMachines.value.length ? harnessMachines.value : sectionRecords('machines').map((row, index) => ({ worker_id: `demo-worker-${index}`, process_id: '—', last_seen: row.activity, current_run_id: index === 0 ? 'RUN-2048' : null })))
const approvalRows = computed(() => resourceConnected.value && harnessApprovals.value.length ? harnessApprovals.value : sectionRecords('approvals').map((row, index) => ({ request_id: `demo-approval-${index}`, run_id: row.name, tool: row.owner, risk: 'high', detail: row.activity, status: 'pending' })))
const artifactRows = computed(() => resourceConnected.value && harnessArtifacts.value.length ? harnessArtifacts.value : sectionRecords('artifacts').map((row, index) => ({ artifact_id: `demo-artifact-${index}`, name: row.name, path: row.detail, size: '—', updated_at: row.activity, run_id: row.name.split(' · ')[0] })))
const traceRunRows = computed(() => resourceConnected.value && harnessTraceRuns.value.length ? harnessTraceRuns.value : runs.value.map(run => ({ run_id: run.id, status: run.status, agent: run.agent, query: run.title, created_at: run.elapsed })))
async function refreshEvaluationData({ silent = false } = {}) {
  try {
    const [datasets, config, reports] = await Promise.all([
      getEvaluationDatasets(props.apiBase),
      getEvaluationConfig(props.apiBase),
      getEvaluationRuns(props.apiBase),
    ])
    const items = (datasets?.items || []).map(item => ({ name: item.name, type: item.dataset_type, cases: String(item.case_count || 0), pass: '—', delta: '', state: '未运行', updated: item.updated_at || '刚刚', datasetId: item.dataset_id }))
    evalDatasets.value = items
    if (items.length && !items.some(item => item.datasetId === selectedEvaluationDatasetId.value)) selectedEvaluationDatasetId.value = items[0].datasetId || ''
    evaluationConfig.value = config?.config || evaluationConfig.value
    const runItems = reports?.items || []
    if (runItems.length) evalReports.value = runItems.map(item => ({ version: item.eval_run_id, score: '—', date: item.created_at, state: item.status === 'blocked' ? '执行器未接入' : item.status }))
    evaluationConnected.value = true
    evaluationError.value = ''
  } catch (error) {
    evaluationConnected.value = false
    evaluationError.value = error.message || '测评服务暂不可用'
    if (!silent) notify(`测评数据刷新失败：${evaluationError.value}`)
  }
}
function openDatasetDialog() {
  datasetDraft.value = { name: '', datasetType: '通用', description: '' }
  showDatasetDialog.value = true
}
async function selectEvaluationDataset(dataset) {
  selectedEvaluationDatasetId.value = dataset.datasetId || ''
  if (!dataset.datasetId) {
    notify(`${dataset.name} 是演示测评集，连接后可打开样本详情`)
    return
  }
  try {
    const result = await getEvaluationDataset(props.apiBase, dataset.datasetId)
    selectedEvaluationDataset.value = result.dataset
  } catch (error) { notify(`读取测评集失败：${error.message || '测评服务不可用'}`) }
}
function openCaseDialog(caseItem = null) {
  caseDraft.value = { caseId: caseItem?.case_id || '', input: caseItem?.input_text || '', expectedOutput: caseItem?.expected_output || '', rubric: JSON.stringify(caseItem?.rubric || {}, null, 2) }
  showCaseDialog.value = true
}
async function saveCase() {
  if (!selectedEvaluationDataset.value?.dataset_id || !caseDraft.value.input.trim()) return notify('请输入测试输入')
  let rubric
  try { rubric = JSON.parse(caseDraft.value.rubric || '{}') } catch { notify('评分规则必须是合法 JSON'); return }
  try {
    const payload = { input: caseDraft.value.input.trim(), expectedOutput: caseDraft.value.expectedOutput, rubric }
    if (caseDraft.value.caseId) await updateEvaluationCase(props.apiBase, selectedEvaluationDataset.value.dataset_id, caseDraft.value.caseId, payload)
    else await addEvaluationCase(props.apiBase, selectedEvaluationDataset.value.dataset_id, payload)
    const result = await getEvaluationDataset(props.apiBase, selectedEvaluationDataset.value.dataset_id)
    selectedEvaluationDataset.value = result.dataset
    await refreshEvaluationData({ silent: true })
    showCaseDialog.value = false
    notify(caseDraft.value.caseId ? '测评样本已更新' : '测评样本已添加')
  } catch (error) { notify(`保存测评样本失败：${error.message || '测评服务不可用'}`) }
}
async function submitDataset() {
  if (!datasetDraft.value.name.trim()) {
    notify('请输入测评集名称')
    return
  }
  try {
    const result = await createEvaluationDataset(props.apiBase, { name: datasetDraft.value.name.trim(), datasetType: datasetDraft.value.datasetType, description: datasetDraft.value.description.trim() })
    evaluationConnected.value = true
    showDatasetDialog.value = false
    await refreshEvaluationData({ silent: true })
    notify(`${result.dataset.name} 已创建`)
  } catch (error) {
    notify(`创建测评集失败：${error.message || '测评服务不可用'}`)
  }
}
async function runEvaluation() {
  const datasetId = selectedEvaluationDatasetId.value || evalDatasets.value[0]?.datasetId
  if (!datasetId) {
    notify('请先创建测评集')
    return
  }
  try {
    const result = await createEvaluationRun(props.apiBase, { datasetId, agent: 'chat', version: 'current' })
    await refreshEvaluationData({ silent: true })
    notify(result.message || '测评任务已记录')
  } catch (error) {
    notify(`创建测评任务失败：${error.message || '测评服务不可用'}`)
  }
}
async function saveEvalConfig() {
  try {
    await saveEvaluationConfig(props.apiBase, evaluationConfig.value)
    evaluationConnected.value = true
    notify('评测配置已保存')
  } catch (error) {
    notify(`保存评测配置失败：${error.message || '测评服务不可用'}`)
  }
}
function isDimensionEnabled(label) {
  return evaluationConfig.value.dimensions.find(item => item.label === label)?.enabled !== false
}
function toggleDimension(label, enabled) {
  const existing = evaluationConfig.value.dimensions.find(item => item.label === label)
  if (existing) existing.enabled = enabled
  else evaluationConfig.value.dimensions.push({ label, enabled })
}
async function refreshReleaseData({ silent = false } = {}) {
  try {
    const [result, gates] = await Promise.all([getReleaseSummary(props.apiBase), getReleaseGates(props.apiBase)])
    releaseRollouts.value = result?.rollouts || []
    releaseRuns.value = result?.runs || []
    releaseMetrics.value = result?.metrics || []
    releaseGates.value = gates?.items || []
    releaseConnected.value = true
    releaseError.value = ''
  } catch (error) {
    releaseConnected.value = false
    releaseError.value = error.message || '发布治理服务暂不可用'
    if (!silent) notify(`发布数据刷新失败：${releaseError.value}`)
  }
}
async function promoteCurrentRelease() {
  if (!releaseDraft.value.name.trim() || !releaseDraft.value.version.trim()) {
    notify('请填写技能名称和版本')
    return
  }
  try {
    if (!releaseGateResult.value?.passed) {
      notify('请先通过发布前质量门禁')
      return
    }
    const result = await promoteRelease(props.apiBase, { ...releaseDraft.value, name: releaseDraft.value.name.trim(), version: releaseDraft.value.version.trim(), percentage: Number(releaseDraft.value.percentage), gate: releaseGateDraft.value })
    await refreshReleaseData({ silent: true })
    notify(`${releaseDraft.value.name} ${releaseDraft.value.version} 已进入 ${result.percentage}% 灰度`)
  } catch (error) {
    notify(`发布失败：${error.message || '发布治理服务不可用'}`)
  }
}
async function checkReleaseGate() {
  try {
    releaseGateResult.value = await evaluateReleaseGate(props.apiBase, { ...releaseGateDraft.value, project: releaseDraft.value.project, name: releaseDraft.value.name, version: releaseDraft.value.version })
    notify(releaseGateResult.value.passed ? '质量门禁已通过' : '质量门禁未通过')
  } catch (error) { notify(`质量门禁检查失败：${error.message || '发布治理服务不可用'}`) }
}
async function rollbackReleaseByRow(row) {
  try {
    await rollbackRelease(props.apiBase, { project: row.project, name: row.name })
    await refreshReleaseData({ silent: true })
    notify(`${row.name} 已回滚`)
  } catch (error) {
    notify(`回滚失败：${error.message || '发布治理服务不可用'}`)
  }
}
function refreshActiveSection() {
  if (activeSection.value === 'evaluations') return refreshEvaluationData()
  if (activeSection.value === 'releases') return refreshReleaseData()
  if (['agents', 'workspaces'].includes(activeSection.value)) return refreshResourceData()
  return refreshExecutionRuns()
}
async function refreshResourceData({ silent = false } = {}) {
  try {
    const [agents, workspaces, tools, models, skills, machines, approvals, artifacts, traceRuns] = await Promise.all([getHarnessAgents(props.apiBase), getHarnessWorkspaces(props.apiBase), getHarnessTools(props.apiBase), getHarnessModels(props.apiBase), getSkills(props.apiBase), getHarnessMachines(props.apiBase), getHarnessApprovals(props.apiBase, 'pending'), getHarnessArtifacts(props.apiBase), getHarnessObservabilityRuns(props.apiBase)])
    harnessAgents.value = agents?.items || []
    harnessWorkspaces.value = workspaces?.items || []
    harnessTools.value = tools?.items || []
    harnessModels.value = models?.items || []
    harnessSkills.value = skills?.skills || []
    harnessMachines.value = machines?.items || []
    harnessApprovals.value = approvals?.items || []
    harnessArtifacts.value = artifacts?.items || []
    harnessTraceRuns.value = traceRuns?.items || []
    resourceConnected.value = true
    resourceError.value = ''
  } catch (error) {
    resourceConnected.value = false
    resourceError.value = error.message || '资源目录服务暂不可用'
    if (!silent) notify(`资源目录刷新失败：${resourceError.value}`)
  }
}
function openAgentDialog() {
  agentDraft.value = { name: '', description: '', version: 'v1', model: 'auto' }
  showAgentDialog.value = true
}
async function submitAgent() {
  if (!agentDraft.value.name.trim()) return notify('请输入 Agent 名称')
  try {
    await createHarnessAgent(props.apiBase, { ...agentDraft.value, name: agentDraft.value.name.trim() })
    showAgentDialog.value = false
    await refreshResourceData({ silent: true })
    notify('Agent 已创建')
  } catch (error) { notify(`创建 Agent 失败：${error.message || '资源服务不可用'}`) }
}
function openWorkspaceDialog() {
  workspaceDraft.value = { name: '', repository: '', branch: 'main' }
  showWorkspaceDialog.value = true
}
async function submitWorkspace() {
  if (!workspaceDraft.value.name.trim()) return notify('请输入工作空间名称')
  try {
    await createHarnessWorkspace(props.apiBase, { ...workspaceDraft.value, name: workspaceDraft.value.name.trim() })
    showWorkspaceDialog.value = false
    await refreshResourceData({ silent: true })
    notify('工作空间已创建')
  } catch (error) { notify(`创建工作空间失败：${error.message || '资源服务不可用'}`) }
}
async function decideApproval(row, decision) {
  try {
    await decideHarnessApproval(props.apiBase, row.request_id, { decision, reason: decision === 'approved' ? 'Harness 操作者批准' : 'Harness 操作者拒绝' })
    await refreshResourceData({ silent: true })
    notify(decision === 'approved' ? '审批已通过' : '审批已拒绝')
  } catch (error) { notify(`审批处理失败：${error.message || '审批服务不可用'}`) }
}
function selectEvaluationTab(tab) {
  evaluationTab.value = tab
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
    runs: ['执行任务', '提交、排队、停止、重试并查看单次运行的 Trace、上下文和产物。资源配置通过关联只读查看。', ['RUN-2048 · 运行中 · Support analyst', 'RUN-2047 · 运行中 · Docs engineer', 'RUN-2046 · 排队中 · Platform operator', 'RUN-2045 · 运行中 · QA engineer']],
    agents: ['Agent 实例', '4 个 Agent 配置正在工作空间中执行。每个实例绑定独立的模型路由、工具权限和运行策略。', ['support-analyst · v1.8 · 运行中', 'docs-engineer · v2.1 · 运行中', 'platform-operator · v1.3 · 空闲', 'qa-engineer · v1.4 · 运行中']],
    workspaces: ['工作空间', '每次运行使用独立工作目录与会话快照。Git 分支、文件变更和运行历史均可追溯。', ['support-ops · main · 2 个运行', 'docs-platform · feature/api-errors · 1 个运行', 'agent-platform · main · 空闲', 'support-ops · rules-v2 · 1 个运行']],
    tools: ['工具与 MCP', '统一查看工具来源、访问范围、调用策略和最近使用情况。敏感写入操作可配置人工审批。', ['knowledge.search · MCP · 只读', 'crm.ticket.update · MCP · 需审批', 'playwright.browser · 内置 · 沙箱', 'filesystem.patch · 内置 · 工作区范围']],
    skills: ['Skills', '可组合的任务能力包。Skill 版本随每次运行记录，变更后可比较行为和调用轨迹。', ['support-triage · v1.8 · 已启用', 'api-docs · v2.1 · 已启用', 'release-check · v1.3 · 草稿', 'refund-analysis · v1.2 · 已启用']],
    models: ['模型路由', '按任务类型、成本上限和可用性选择模型。每次路由决策都会记录原因和实际用量。', ['Claude Sonnet 4 · 默认 · 可用', 'GPT-5 · 文档任务 · 可用', 'DeepSeek V3.2 · 低成本队列 · 可用', '本地模型 · 私有任务 · 未连接']],
    machines: ['机器与运行时', '管理本地与远端执行节点，观察容量、隔离方式、版本和心跳。运行环境为演示数据。', ['local-dev · Docker · 2 / 4 slots', 'gpu-worker-01 · Remote · 1 / 2 slots', 'ci-runner · Container · 0 / 8 slots']],
    approvals: ['待审批', '高影响工具调用在执行前暂停，审批决定、操作者与执行结果一并进入审计事件。', ['RUN-2048 · crm.ticket.update · 影响 3 条记录', 'RUN-2043 · filesystem.patch · 修改 2 个文件']],
    artifacts: ['产物与存储', '按运行查看补丁、日志、截图、结构化结果和会话快照；产物继承对应工作空间权限。', ['RUN-2048 · refund-clusters.json · 4.2 KB', 'RUN-2047 · api-errors.patch · 2.1 KB', 'RUN-2045 · regression-report.html · 86 KB']],
    observability: ['追踪与日志', '将 Agent 推理阶段、模型请求、工具调用和运行时事件放进同一条可筛选时间线。', ['agent.turn · 1.84s · Claude Sonnet 4', 'knowledge.search · 0.32s · 4 chunks', 'approval.wait · 00:48 · pending', 'artifact.write · 0.08s · 1 file']],
    releases: ['发布治理', '管理已通过质量门禁的 Skill 版本灰度、线上指标和回滚记录。', ['hotline-agent / incident-summary · v2 · 10% 灰度', 'hotline-agent / api-docs · v1.4 · 已回滚']],
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
onMounted(() => {
  refreshExecutionRuns({ silent: true })
  refreshEvaluationData({ silent: true })
  refreshReleaseData({ silent: true })
  refreshResourceData({ silent: true })
  executionRefreshTimer = window.setInterval(() => {
    if (['overview', 'runs'].includes(activeSection.value)) refreshExecutionRuns({ silent: true })
  }, 5000)
})
onUnmounted(() => {
  window.clearInterval(executionRefreshTimer)
})
</script>

<template>
  <div class="harness-shell" :class="{ 'is-embedded': props.embedded }">
    <div v-if="mobileNavOpen" class="mobile-scrim" @click="mobileNavOpen = false"></div>
    <aside class="harness-sidebar" :class="{ 'is-open': mobileNavOpen }">
      <div class="brand-lockup"><div class="brand-symbol"><Workflow :size="18" :stroke-width="2" /></div><div class="brand-copy"><strong>HOTLINE</strong><span>AGENT HARNESS</span></div><button class="close-mobile" aria-label="关闭导航" @click="mobileNavOpen = false"><X :size="17" /></button></div>
      <nav class="side-navigation" aria-label="Harness 导航"><div v-for="group in sections" :key="group.label" class="nav-group"><div class="nav-group-label">{{ group.label }}</div><button v-for="item in group.items" :key="item.id" class="nav-link" :class="{ active: activeSection === item.id }" @click="selectSection(item.id)"><component :is="item.icon" :size="16" :stroke-width="1.8" /><span>{{ item.label }}</span><small v-if="item.count">{{ item.count }}</small></button></div></nav>
    </aside>

    <main class="main-surface">
      <header v-if="!props.embedded" class="topbar"><button class="mobile-menu" aria-label="打开导航" @click="mobileNavOpen = true"><Menu :size="19" /></button><div class="breadcrumbs"><span>Harness</span><span class="crumb-slash">/</span><strong>{{ navTitle }}</strong></div><div class="topbar-actions"><span class="demo-label" :class="{ planned: sectionMode === 'planned' }"><span></span>{{ sourceLabel }}</span><button class="top-icon" aria-label="搜索" title="搜索" @click="$refs.searchField?.focus()"><Search :size="16" /></button><button class="command-shortcut" @click="$refs.searchField?.focus()"><Command :size="13" />快速查找<kbd>Ctrl K</kbd></button><button class="avatar-small" aria-label="个人账户">SC</button></div></header>
      <div class="page-scroll"><div class="page-content">
      <div class="page-heading-row"><div><h1>{{ pageHeading }}</h1><p v-if="activeSection === 'overview'">统一查看 Agent 执行、工具治理与运行环境。</p><p v-else-if="activeSection === 'evaluations'">用可复现的测评集验证 Agent 质量，并在变更进入生产前发现回归。</p><p v-else>{{ sectionSummary(activeSection)[1] }}</p><small v-if="activeSection !== 'overview' && activeSection !== 'evaluations'" class="section-boundary">本页只负责：{{ moduleScope[0] }}。{{ moduleScope[1] }}。</small></div><div class="heading-actions"><button v-if="props.embedded" class="mobile-menu embedded-mobile-menu" type="button" title="打开 Harness 菜单" aria-label="打开 Harness 菜单" :aria-expanded="mobileNavOpen" @click="mobileNavOpen = true"><Menu :size="18" /></button><span v-if="props.embedded" class="embedded-source-label">{{ sourceLabel }}</span><button v-if="canRefreshStatus" class="button button-subtle refresh-button" title="刷新状态" aria-label="刷新状态" @click="refreshActiveSection"><Activity :size="15" /><span>{{ executionLoading ? '刷新中…' : '刷新状态' }}</span></button><button v-if="canCreateRun" class="button button-primary" @click="openCreateRun"><Plus :size="16" />新建运行</button></div></div>
      <div v-if="executionError && ['overview', 'runs'].includes(activeSection)" class="execution-error-banner"><ShieldCheck :size="16" /><span>{{ executionError }}，当前保留本地演示数据。</span><button class="text-action" @click="refreshExecutionRuns">重试</button></div>
      <div v-if="evaluationError && activeSection === 'evaluations'" class="execution-error-banner"><ShieldCheck :size="16" /><span>{{ evaluationError }}，当前保留测评演示数据。</span><button class="text-action" @click="refreshEvaluationData">重试</button></div>
      <div v-if="releaseError && activeSection === 'releases'" class="execution-error-banner"><ShieldCheck :size="16" /><span>{{ releaseError }}，当前保留发布演示数据。</span><button class="text-action" @click="refreshReleaseData">重试</button></div>
      <div v-if="resourceError && ['agents', 'workspaces'].includes(activeSection)" class="execution-error-banner"><ShieldCheck :size="16" /><span>{{ resourceError }}，当前保留资源演示数据。</span><button class="text-action" @click="refreshResourceData">重试</button></div>

        <div v-if="sectionMode === 'planned'" class="planned-notice"><div class="planned-mark"><ShieldCheck :size="18" /></div><div><strong>{{ navTitle }}尚未接入运行控制 API</strong><span>当前展示规划范围和待接入状态。接入后此处会显示来自后端的实时资源、版本与审计数据。</span></div><span class="planned-badge">目标模块 · {{ activeSection }}</span></div>
        <template v-if="activeSection === 'overview' || activeSection === 'runs'">
          <section class="overview-strip" aria-label="运行指标"><div class="overview-stat"><span>活动运行</span><strong>03</strong><small><i class="status-inline"></i>2 执行中 · 1 排队</small></div><div class="overview-stat"><span>今日完成</span><strong>28</strong><small class="positive"><Check :size="12" />成功率 96.4%</small></div><div class="overview-stat"><span>待人工审批</span><strong class="stat-warn">02</strong><small>最高风险：写入操作</small></div><div class="overview-stat"><span>今日模型用量</span><strong>1.82M</strong><small>Tokens · 估算 $4.82</small></div><div class="overview-stat stat-runtime"><span>运行时节点</span><strong>02 <em>/ 03</em></strong><small>8 / 14 并发槽位可用</small></div></section>

          <section v-if="activeSection === 'runs'" class="run-workbench runs-view">
            <div class="run-list-panel"><div class="panel-heading run-list-heading"><div><h2>执行队列</h2><span>任务、Agent 与工作空间</span></div><button class="icon-action" title="筛选任务" @click="filter = filter === '全部任务' ? '运行中' : '全部任务'"><Filter :size="15" /></button></div><div class="run-list-tools"><div class="run-filters"><button v-for="option in ['全部任务', '运行中', '排队中']" :key="option" :class="{ selected: filter === option }" @click="filter = option">{{ option }}<span v-if="option === '全部任务'">12</span></button></div><label class="run-search"><Search :size="14" /><input ref="searchField" v-model="search" placeholder="搜索任务" /></label></div><div class="run-list"><button v-for="run in visibleRuns" :key="run.id" class="run-row" :class="{ selected: selectedRunId === run.id }" @click="selectedRunId = run.id; activeView = 'control'"><div class="run-row-top"><span class="run-status-dot" :class="run.status"></span><strong>{{ run.title }}</strong><span class="run-row-menu" @click.stop="notify(`${run.id} 操作菜单`)"><MoreHorizontal :size="16" /></span></div><div class="run-row-meta"><span>{{ run.id }}</span><span class="meta-sep">·</span><span>{{ run.agent }}</span></div><div class="run-row-bottom"><span>{{ run.workspace }}</span><span v-if="run.status === 'running'" class="run-elapsed">{{ run.elapsed }}</span><span v-else class="queued-tag">排队中</span></div><div v-if="run.status === 'running'" class="run-progress"><i :style="{ width: `${run.progress}%` }"></i></div></button><div v-if="!visibleRuns.length" class="empty-runs"><Search :size="18" /><span>没有匹配的运行</span><button @click="search = ''; filter = '全部任务'">清除筛选</button></div></div><button class="queue-footer" @click="activeSection = 'runs'"><span>查看全部执行记录</span><ArrowRight :size="14" /></button></div>

              <div class="run-detail-panel"><div class="run-detail-top"><div class="detail-title-group"><div class="detail-run-id"><span class="run-status-dot" :class="selectedRun.status"></span>{{ selectedRun.id }}<span class="status-pill" :class="selectedRun.status">{{ selectedRun.status === 'running' ? '运行中' : selectedRun.status === 'queued' ? '排队中' : selectedRun.status === 'failed' ? '失败' : selectedRun.status === 'cancelled' ? '已取消' : '已完成' }}</span></div><h2>{{ selectedRun.title }}</h2><div class="detail-subtitle"><span>{{ selectedRun.workspace }}</span><span>·</span><span>{{ selectedRun.agent }}</span></div></div><div class="detail-toolbar"><button class="icon-action" title="下载运行记录" @click="notify('运行记录导出已准备')"><ArrowDownToLine :size="15" /></button><button class="icon-action" title="更多操作" @click="notify('运行操作菜单')"><MoreHorizontal :size="16" /></button><button v-if="running && ['queued', 'running'].includes(selectedRun.status)" class="button button-stop" @click="stopSelectedRun"><Square :size="12" />停止运行</button><button v-else-if="selectedRun.status === 'failed'" class="button button-subtle" @click="retrySelectedRun"><Play :size="14" />重新运行</button></div></div>
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
          <section v-else-if="activeSection === 'evaluations'" class="evaluation-page">
          <div class="evaluation-toolbar"><div class="evaluation-tabs"><button :class="{ active: evaluationTab === 'overview' }" @click="selectEvaluationTab('overview')">测评总览</button><button :class="{ active: evaluationTab === 'datasets' }" @click="selectEvaluationTab('datasets')">测评集</button><button :class="{ active: evaluationTab === 'config' }" @click="selectEvaluationTab('config')">评测配置</button><button :class="{ active: evaluationTab === 'reports' }" @click="selectEvaluationTab('reports')">历史报告</button></div><button class="button button-primary" @click="runEvaluation"><Play :size="14" />运行测评</button></div>
          <template v-if="evaluationTab === 'overview'">
          <section class="evaluation-hero"><div><span class="harness-eyebrow">AGENT EVALUATION HARNESS</span><h2>让每次 Agent 变更都有可验证的结果</h2><p>用版本化测评集回放真实任务，统一检查端到端完成度、RAG 质量、工具调用与多轮记忆。</p></div><div class="evaluation-score"><strong>89.6</strong><span>综合得分 / 100</span><small><i></i>较上次 +3.4</small></div></section>
          <section class="evaluation-kpis"><div><span>活跃测评集</span><strong>06</strong><small>228 条测试样本</small></div><div><span>最近通过率</span><strong>89.6%</strong><small class="positive">较上个版本 +3.4%</small></div><div><span>失败样本</span><strong class="stat-warn">24</strong><small>需要回放与归因</small></div><div><span>平均耗时</span><strong>4.8s</strong><small>每个样本 · 估算 $0.018</small></div></section>
          <div class="evaluation-grid"><section class="harness-panel evaluation-dimensions"><div class="harness-panel-heading"><div><h3>能力维度</h3><p>当前版本 v1.8.2 · 以最近一次完整测评为准</p></div><button class="text-action" @click="selectEvaluationTab('config')">配置维度 <ArrowRight :size="13" /></button></div><div class="dimension-list"><div v-for="dimension in evalDimensions" :key="dimension.label" class="dimension-row"><div class="dimension-icon" :class="dimension.color"><Gauge :size="15" /></div><div class="dimension-copy"><strong>{{ dimension.label }}</strong><small>{{ dimension.note }}</small></div><div class="dimension-track"><i :class="dimension.color" :style="{ width: `${dimension.value}%` }"></i></div><strong class="dimension-score">{{ dimension.score }}</strong></div></div></section><aside class="harness-panel evaluation-health"><div class="harness-panel-heading"><div><h3>质量门禁</h3><p>合并前自动检查</p></div><span class="eval-gate-pass"><Check :size="12" />通过</span></div><div class="gate-row"><span>端到端通过率 ≥ 90%</span><strong>91.7%</strong><Check :size="14" /></div><div class="gate-row"><span>RAG 忠实度 ≥ 0.85</span><strong>0.91</strong><Check :size="14" /></div><div class="gate-row"><span>高风险工具误调用 = 0</span><strong>0</strong><Check :size="14" /></div><div class="gate-note"><ShieldCheck :size="14" />所有样本均保留输入、Trace、工具调用和评分证据。</div></aside></div>
          <section class="harness-panel evaluation-datasets"><div class="harness-panel-heading"><div><h3>测评集</h3><p>可复用的输入、期望结果和评分规则</p></div><button class="button button-subtle" @click="openDatasetDialog"><Plus :size="14" />新建测评集</button></div><div class="dataset-table"><div class="dataset-head"><span>名称</span><span>类型</span><span>样本数</span><span>通过率</span><span>最近运行</span><span>状态</span></div><button v-for="dataset in evalDatasets" :key="dataset.name" class="dataset-row" @click="selectEvaluationDataset(dataset)"><strong>{{ dataset.name }}</strong><span class="dataset-type">{{ dataset.type }}</span><span>{{ dataset.cases }}</span><span class="dataset-pass">{{ dataset.pass }} <small>{{ dataset.delta }}</small></span><span>{{ dataset.updated }}</span><span class="dataset-state" :class="{ running: dataset.state === '运行中', attention: dataset.state === '需关注' }"><i></i>{{ dataset.state }}</span><ArrowRight :size="14" /></button></div></section>
          </template>
          <section v-else-if="evaluationTab === 'datasets'" class="harness-panel evaluation-subpage"><div class="harness-panel-heading"><div><h3>测评集管理</h3><p>维护测试输入、期望结果、工具断言和评分规则。</p></div><button class="button button-primary" @click="openDatasetDialog"><Plus :size="14" />新建测评集</button></div><div class="evaluation-dataset-cards"><button v-for="dataset in evalDatasets" :key="dataset.name" class="evaluation-dataset-card" @click="selectEvaluationDataset(dataset)"><div><strong>{{ dataset.name }}</strong><span>{{ dataset.type }} · {{ dataset.cases }} 条样本</span></div><b>{{ dataset.pass }}</b><ArrowRight :size="14" /></button></div></section>
          <section v-else-if="evaluationTab === 'config'" class="harness-panel evaluation-subpage"><div class="harness-panel-heading"><div><h3>评测配置</h3><p>为本次测评任务选择测评维度和质量门禁。</p></div><button class="button button-primary" @click="saveEvalConfig"><Check :size="14" />保存配置</button></div><div class="evaluation-config-list"><label v-for="dimension in evalDimensions" :key="dimension.label"><input type="checkbox" :checked="isDimensionEnabled(dimension.label)" @change="toggleDimension(dimension.label, $event.target.checked)" /> <span><strong>{{ dimension.label }}</strong><small>{{ dimension.note }}</small></span><em>已启用</em></label></div></section>
          <section v-else class="harness-panel evaluation-subpage"><div class="harness-panel-heading"><div><h3>历史报告</h3><p>按版本查看测评结果、回归样本和质量门禁状态。</p></div><button class="button button-subtle" @click="notify('历史报告导出已准备')"><ArrowDownToLine :size="14" />导出报告</button></div><div class="evaluation-report-list"><button v-for="report in evalReports" :key="report.version" @click="notify(`${report.version}：打开历史报告`)" class="evaluation-report-row"><strong>{{ report.version }}</strong><span>{{ report.date }}</span><b>{{ report.score }} / 100</b><span class="dataset-state" :class="{ attention: report.state === '需关注' }"><i></i>{{ report.state }}</span><ArrowRight :size="14" /></button></div></section>
          <footer class="page-footer"><span>Harness 控制面 · 测评中心</span><span><i class="footer-health demo-health"></i>演示数据 · 测评执行器未连接</span><span>更新时间 14:33</span></footer>
        </section>
        <section v-else-if="['artifacts', 'observability'].includes(activeSection)" class="resource-page">
          <div class="release-toolbar"><div><span class="harness-eyebrow">READ-ONLY OPERATIONS</span><h2>{{ activeSection === 'artifacts' ? '产物与存储' : '追踪与日志' }}</h2><p>{{ activeSection === 'artifacts' ? '索引、预览、下载和保留运行产物。' : '查询 Trace、运行事件和日志，不负责启动或停止运行。' }}</p></div><button class="button button-subtle" @click="refreshResourceData">刷新数据</button></div>
          <section class="harness-panel resource-table-panel"><div class="harness-panel-heading"><div><h3>{{ activeSection === 'artifacts' ? '产物索引' : '运行 Trace' }}</h3><p>{{ activeSection === 'artifacts' ? artifactRows.length : traceRunRows.length }} 条记录 · 只读</p></div></div><div v-if="activeSection === 'artifacts' && artifactRows.length" class="resource-table"><div class="resource-table-head workspace-cols"><span>名称</span><span>路径</span><span>运行</span><span>大小</span><span>时间</span></div><div v-for="row in artifactRows" :key="row.artifact_id" class="resource-row workspace-cols"><span><strong>{{ row.name }}</strong></span><span>{{ row.path }}</span><span>{{ row.run_id || '—' }}</span><span>{{ row.size }}</span><span>{{ row.updated_at }}</span></div></div><div v-else-if="activeSection === 'observability' && traceRunRows.length" class="resource-table"><div class="resource-table-head workspace-cols"><span>运行</span><span>Agent</span><span>任务</span><span>状态</span><span>时间</span></div><div v-for="row in traceRunRows" :key="row.run_id" class="resource-row workspace-cols"><span><strong>{{ row.run_id }}</strong></span><span>{{ row.agent }}</span><span>{{ row.query }}</span><span>{{ row.status }}</span><span>{{ row.created_at }}</span></div></div><div v-else class="release-empty"><span>暂无记录</span></div></section>
          <footer class="page-footer"><span>Harness 控制面 · {{ activeSection === 'artifacts' ? '产物与存储' : '追踪与日志' }}</span><span><i class="footer-health demo-health"></i>{{ resourceConnected ? '已连接只读运营 API' : '演示数据 · 未连接运营 API' }}</span><span>只读观察，不修改运行配置</span></footer>
        </section>
        <section v-else-if="['machines', 'approvals'].includes(activeSection)" class="resource-page">
          <div class="release-toolbar"><div><span class="harness-eyebrow">RUNTIME GOVERNANCE</span><h2>{{ activeSection === 'machines' ? '机器与运行时' : '待审批' }}</h2><p>{{ activeSection === 'machines' ? '只读查看 Worker 心跳、当前运行和运行时容量。' : '只处理高影响工具调用的审批决定和审计理由。' }}</p></div><button class="button button-subtle" @click="refreshResourceData">刷新状态</button></div>
          <section class="harness-panel resource-table-panel"><div class="harness-panel-heading"><div><h3>{{ activeSection === 'machines' ? '运行时节点' : '审批队列' }}</h3><p>{{ activeSection === 'machines' ? machineRows.length : approvalRows.length }} 条记录 · {{ resourceConnected ? '已连接治理 API' : '演示数据' }}</p></div></div><div v-if="activeSection === 'machines' && machineRows.length" class="resource-table"><div class="resource-table-head workspace-cols"><span>Worker</span><span>进程</span><span>最近心跳</span><span>当前运行</span><span>状态</span></div><div v-for="row in machineRows" :key="row.worker_id" class="resource-row workspace-cols"><span><strong>{{ row.worker_id }}</strong></span><span>{{ row.process_id }}</span><span>{{ row.last_seen }}</span><span>{{ row.current_run_id || '空闲' }}</span><span>{{ row.current_run_id ? '运行中' : '在线' }}</span></div></div><div v-else-if="activeSection === 'approvals' && approvalRows.length" class="resource-table"><div class="resource-table-head workspace-cols"><span>请求</span><span>工具</span><span>运行</span><span>风险</span><span>决定</span></div><div v-for="row in approvalRows" :key="row.request_id" class="resource-row workspace-cols"><span><strong>{{ row.request_id }}</strong><small>{{ row.detail }}</small></span><span>{{ row.tool }}</span><span>{{ row.run_id }}</span><span>{{ row.risk }}</span><span><button v-if="row.status === 'pending'" class="text-action" @click="decideApproval(row, 'approved')">批准</button><button v-if="row.status === 'pending'" class="text-action" @click="decideApproval(row, 'rejected')">拒绝</button><span v-else>{{ row.status }}</span></span></div></div><div v-else class="release-empty"><span>当前没有记录</span></div></section>
          <footer class="page-footer"><span>Harness 控制面 · {{ activeSection === 'machines' ? '机器与运行时' : '待审批' }}</span><span><i class="footer-health demo-health"></i>{{ resourceConnected ? '已连接治理 API' : '演示数据 · 未连接治理 API' }}</span><span>{{ activeSection === 'machines' ? '任务状态只在执行任务查看' : '审批决定保留审计记录' }}</span></footer>
        </section>
        <section v-else-if="['tools', 'models', 'skills'].includes(activeSection)" class="resource-page">
          <div class="release-toolbar"><div><span class="harness-eyebrow">CAPABILITY REGISTRY</span><h2>{{ activeSection === 'tools' ? '工具与 MCP' : activeSection === 'models' ? '模型路由' : 'Skills' }}</h2><p>{{ activeSection === 'tools' ? '管理工具来源、权限范围、风险和审批策略。调用结果回到运行 Trace。' : activeSection === 'models' ? '管理提供商、路由、fallback 和成本策略。实际调用只读关联运行。' : '管理本地 Skill 包的安装状态和运行可用性。版本绑定与灰度由发布治理负责。' }}</p></div><button class="button button-subtle" @click="refreshResourceData">刷新目录</button></div>
          <section class="harness-panel resource-table-panel"><div class="harness-panel-heading"><div><h3>{{ activeSection === 'tools' ? '工具目录' : activeSection === 'models' ? '模型路由目录' : 'Skill 安装目录' }}</h3><p>{{ activeSection === 'tools' ? toolRows.length : modelRows.length }} 条资源记录 · {{ resourceConnected ? '已连接资源目录' : '演示数据' }}</p></div></div><div v-if="activeSection === 'tools' && toolRows.length" class="resource-table"><div class="resource-table-head"><span>名称</span><span>来源</span><span>范围</span><span>风险</span><span>状态</span></div><div v-for="row in toolRows" :key="row.tool_id" class="resource-row"><span><strong>{{ row.name }}</strong><small>{{ row.description || '暂无描述' }}</small></span><span>{{ row.source }}</span><span>{{ row.scope }}</span><span>{{ row.risk }}</span><span>{{ row.status }}</span></div></div><div v-else-if="activeSection === 'models' && modelRows.length" class="resource-table"><div class="resource-table-head workspace-cols"><span>模型</span><span>提供商</span><span>路由</span><span>状态</span><span>成本策略</span></div><div v-for="row in modelRows" :key="row.model_id" class="resource-row workspace-cols"><span><strong>{{ row.name }}</strong></span><span>{{ row.provider }}</span><span>{{ row.route }}</span><span>{{ row.status }}</span><span>{{ row.cost_policy || '未配置' }}</span></div></div><div v-else-if="activeSection === 'skills' && skillRows.length" class="resource-table"><div class="resource-table-head"><span>名称</span><span>说明</span><span>来源</span><span>状态</span><span></span></div><div v-for="row in skillRows" :key="row.id" class="resource-row"><span><strong>{{ row.name }}</strong></span><span>{{ row.description || '暂无描述' }}</span><span>{{ row.sourceFile || '本地 Skill' }}</span><span>{{ row.enabled ? '已启用' : '已停用' }}</span><span>只读</span></div></div><div v-else class="release-empty"><span>还没有资源记录</span></div></section>
          <footer class="page-footer"><span>Harness 控制面 · {{ activeSection === 'tools' ? '工具与 MCP' : '模型路由' }}</span><span><i class="footer-health demo-health"></i>{{ resourceConnected ? '已连接资源目录' : '演示数据 · 未连接资源 API' }}</span><span>调用详情只在运行 Trace 查看</span></footer>
        </section>
        <section v-else-if="['agents', 'workspaces'].includes(activeSection)" class="resource-page">
          <div class="release-toolbar"><div><span class="harness-eyebrow">RESOURCE REGISTRY</span><h2>{{ activeSection === 'agents' ? 'Agent 实例' : '工作空间' }}</h2><p>{{ activeSection === 'agents' ? '管理 Agent 定义、版本、模型和运行策略。实际运行通过 runId 只读关联。' : '管理仓库、分支和运行快照归属。运行只读引用工作空间。' }}</p></div><button class="button button-primary" @click="activeSection === 'agents' ? openAgentDialog() : openWorkspaceDialog()"><Plus :size="14" />{{ activeSection === 'agents' ? '新建 Agent' : '新建工作空间' }}</button></div>
          <section class="harness-panel resource-table-panel"><div class="harness-panel-heading"><div><h3>{{ activeSection === 'agents' ? 'Agent 目录' : '工作空间目录' }}</h3><p>{{ activeSection === 'agents' ? agentRows.length : workspaceRows.length }} 条资源记录 · {{ resourceConnected ? '已连接资源目录' : '演示数据' }}</p></div><button class="button button-subtle" @click="refreshResourceData">刷新目录</button></div><div v-if="activeSection === 'agents' && agentRows.length" class="resource-table"><div class="resource-table-head"><span>名称</span><span>版本</span><span>模型</span><span>状态</span><span></span></div><div v-for="row in agentRows" :key="row.agent_id" class="resource-row"><span><strong>{{ row.name }}</strong><small>{{ row.description || '暂无描述' }}</small></span><span>{{ row.version }}</span><span>{{ row.model }}</span><span>{{ row.status }}</span><button class="text-action" @click="notify('Agent 详情将在下一阶段开放')">查看</button></div></div><div v-else-if="activeSection === 'workspaces' && workspaceRows.length" class="resource-table"><div class="resource-table-head workspace-cols"><span>名称</span><span>仓库</span><span>分支</span><span>状态</span><span></span></div><div v-for="row in workspaceRows" :key="row.workspace_id" class="resource-row workspace-cols"><span><strong>{{ row.name }}</strong><small>{{ row.workspace_id }}</small></span><span>{{ row.repository || '未绑定仓库' }}</span><span>{{ row.branch }}</span><span>{{ row.status }}</span><button class="text-action" @click="notify('工作空间详情将在下一阶段开放')">查看</button></div></div><div v-else class="release-empty"><span>还没有资源记录</span></div></section>
          <footer class="page-footer"><span>Harness 控制面 · {{ activeSection === 'agents' ? 'Agent 实例' : '工作空间' }}</span><span><i class="footer-health demo-health"></i>{{ resourceConnected ? '已连接资源目录' : '演示数据 · 未连接资源 API' }}</span><span>运行通过 ID 只读关联</span></footer>
        </section>
        <section v-else-if="activeSection === 'releases'" class="release-page">
          <div class="release-toolbar"><div><span class="harness-eyebrow">RELEASE GOVERNANCE</span><h2>发布治理</h2><p>只负责版本灰度、指标观察和回滚，不编辑测评样本。</p></div><button class="button button-subtle" @click="refreshReleaseData">刷新发布状态</button></div>
          <div class="release-kpis"><div><span>活动灰度</span><strong>{{ releaseRollouts.filter(item => item.active).length }}</strong><small>当前项目绑定</small></div><div><span>最高灰度比例</span><strong>{{ releaseRollouts.length ? Math.max(...releaseRollouts.map(item => item.percentage || 0)) : 0 }}%</strong><small>按技能版本统计</small></div><div><span>发布记录</span><strong>{{ releaseRuns.length }}</strong><small>包含门禁结果</small></div><div><span>线上指标</span><strong>{{ releaseMetrics.length }}</strong><small>最近 500 条</small></div></div>
          <div class="release-grid"><section class="harness-panel"><div class="harness-panel-heading"><div><h3>当前灰度</h3><p>发布后续请求按比例选择候选版本。</p></div></div><div v-if="releaseRollouts.length" class="release-table"><div class="release-table-head"><span>项目 / 技能</span><span>候选版本</span><span>旧版本</span><span>比例</span><span>状态</span><span></span></div><div v-for="row in releaseRollouts" :key="`${row.project}-${row.name}`" class="release-row"><span><strong>{{ row.name }}</strong><small>{{ row.project }}</small></span><span>{{ row.candidate_version }}</span><span>{{ row.previous_version || '—' }}</span><span>{{ row.percentage }}%</span><span>{{ row.active ? '灰度中' : '已回滚' }}</span><button v-if="row.active" class="text-action" @click="rollbackReleaseByRow(row)">回滚</button></div></div><div v-else class="release-empty"><GitBranch :size="20" /><span>当前没有灰度版本</span></div></section><section class="harness-panel"><div class="harness-panel-heading"><div><h3>推进灰度</h3><p>发布治理只接受已存在的 Skill 版本。</p></div></div><div class="release-form"><label>项目<input v-model="releaseDraft.project" /></label><label>技能名称<input v-model="releaseDraft.name" placeholder="例如 incident-summary" /></label><label>候选版本<input v-model="releaseDraft.version" placeholder="例如 v2" /></label><label>灰度比例<input v-model.number="releaseDraft.percentage" type="number" min="0" max="100" /></label><div class="release-gate-fields"><strong>发布前质量门禁</strong><label>评测运行 ID<input v-model="releaseGateDraft.evalRunId" placeholder="可选，关联 evalRunId" /></label><label>端到端通过率<input v-model.number="releaseGateDraft.e2ePassRate" type="number" min="0" max="1" step="0.001" /></label><label>RAG 忠实度<input v-model.number="releaseGateDraft.ragFaithfulness" type="number" min="0" max="1" step="0.001" /></label><label>高风险误调用<input v-model.number="releaseGateDraft.highRiskErrors" type="number" min="0" step="1" /></label><button class="button button-subtle" @click="checkReleaseGate">检查质量门禁</button><span v-if="releaseGateResult" class="release-gate-result" :class="{ passed: releaseGateResult.passed }">{{ releaseGateResult.passed ? '门禁通过' : '门禁未通过' }}</span></div><button class="button button-primary" :disabled="!releaseGateResult?.passed" @click="promoteCurrentRelease"><GitBranch :size="14" />进入灰度</button></div></section></div>
          <section class="harness-panel release-history"><div class="harness-panel-heading"><div><h3>发布记录</h3><p>发布状态和质量门禁结果只读展示。</p></div></div><div v-if="releaseRuns.length" class="release-history-list"><div v-for="row in releaseRuns" :key="row.run_id" class="release-history-row"><span>{{ row.created_at }}</span><strong>{{ row.name }}</strong><span>{{ row.base_version }} → {{ row.candidate_version || '—' }}</span><b>{{ row.status }}</b><code>{{ row.run_id }}</code></div></div><div v-else class="release-empty"><span>暂无发布记录</span></div></section>
          <section class="harness-panel release-history"><div class="harness-panel-heading"><div><h3>线上指标</h3><p>指标用于观察灰度版本，错误率达到阈值时由后端执行自动回滚。</p></div></div><div v-if="releaseMetrics.length" class="release-history-list"><div v-for="row in releaseMetrics.slice(0, 20)" :key="`${row.id}-${row.created_at}`" class="release-history-row"><span>{{ row.created_at }}</span><strong>{{ row.metric }}</strong><span>{{ row.name }} / {{ row.version }}</span><b>{{ row.value }}</b><code>{{ row.request_id || '—' }}</code></div></div><div v-else class="release-empty"><span>暂无线上指标</span></div></section>
          <footer class="page-footer"><span>Harness 控制面 · 发布治理</span><span><i class="footer-health demo-health"></i>{{ releaseConnected ? '已连接发布目录' : '演示数据 · 未连接发布 API' }}</span><span>发布与回滚需保留审计记录</span></footer>
        </section>
        <section v-else class="module-page">
          <div class="module-toolbar"><div class="module-tabs"><button v-for="tab in moduleTabs" :key="tab.id" class="module-tab" :class="{ active: moduleTab === tab.id }" @click="selectModuleTab(tab.id)">{{ tab.label }}</button></div><label class="module-search"><Search :size="14" /><input v-model="search" :placeholder="`搜索${navTitle}`" /></label><select v-model="moduleStateFilter" class="module-filter" aria-label="按状态筛选"><option>全部状态</option><option v-for="state in [...new Set(sectionRecords(activeSection).map(row => row.state))]" :key="state">{{ state }}</option></select></div>
          <div class="module-kpis"><div><span>资源总数</span><strong>{{ sectionRecords(activeSection).length }}</strong><small>当前演示目录</small></div><div><span>可用 / 已启用</span><strong>{{ sectionRecords(activeSection).filter(row => ['可用', '已启用', '在线', '已配置', '已生成'].includes(row.state)).length }}</strong><small>状态正常</small></div><div><span>需要关注</span><strong class="module-kpi-warn">{{ sectionRecords(activeSection).filter(row => ['待审批', '草稿', '未连接', '离线', '待处理'].includes(row.state)).length }}</strong><small>待处理或未连接</small></div><div><span>最近更新</span><strong class="module-kpi-time">14:33</strong><small>示例时间</small></div></div>
          <div class="module-content-grid"><section class="module-table-panel"><div class="module-table-heading"><div><h2>{{ sectionSummary(activeSection)[0] }}{{ moduleTab === 'catalog' ? '目录' : moduleTab === 'runs' ? '运行关联' : '变更记录' }}</h2><span>{{ filteredModuleRows.length }} 条演示记录 · {{ moduleTab === 'catalog' ? '展示资源结构' : moduleTab === 'runs' ? '按运行、调用和活动筛选' : '按配置变更和异常状态筛选' }}</span></div><button class="icon-action" title="导出当前记录" @click="notify('当前筛选记录已准备导出')"><ArrowDownToLine :size="15" /></button></div><div class="module-table"><div class="module-table-head"><span>名称 / 标识</span><span>类型 / 来源</span><span>最近活动</span><span>状态</span><span></span></div><button v-for="row in filteredModuleRows" :key="row.name" class="module-table-row" @click="openModuleRecord(row)"><span class="module-primary-cell"><i class="module-item-icon"><component :is="sections.flatMap(group => group.items).find(item => item.id === activeSection)?.icon || Boxes" :size="16" /></i><span><strong>{{ row.name }}</strong><small>{{ row.detail || row.name }}</small></span></span><span class="module-cell"><strong>{{ row.type }}</strong><small>{{ row.owner }}</small></span><span class="module-cell activity-cell">{{ row.activity }}</span><span class="module-state" :class="{ warning: ['待审批', '需审批', '草稿', '未连接', '待处理'].includes(row.state), offline: row.state === '离线' }"><i></i>{{ row.state }}</span><ArrowRight :size="14" class="module-row-arrow" /></button><div v-if="!filteredModuleRows.length" class="module-empty"><Search :size="18" /><strong>当前视图没有匹配记录</strong><button @click="search = ''; moduleStateFilter = '全部状态'; moduleTab = 'catalog'">重置视图和筛选</button></div></div><div class="module-table-footer"><span>数据来源：Harness 规划演示集</span><span>变更与运行时状态尚未持久化</span></div></section>
            <aside class="module-side-panel"><template v-if="selectedModuleRecord"><div class="module-side-heading"><button class="module-back" @click="selectedModuleRecord = null">← {{ navTitle }}</button><span class="module-detail-state">{{ selectedModuleRecord.state }}</span></div><h2 class="module-detail-title">{{ selectedModuleRecord.name }}</h2><p>{{ selectedModuleRecord.detail }}</p><div class="module-side-section"><strong>资源属性</strong><div class="module-detail-field"><span>类型</span><b>{{ selectedModuleRecord.type }}</b></div><div class="module-detail-field"><span>来源 / 负责人</span><b>{{ selectedModuleRecord.owner }}</b></div><div class="module-detail-field"><span>最近活动</span><b>{{ selectedModuleRecord.activity }}</b></div><div class="module-detail-field"><span>数据状态</span><b>本地演示数据</b></div></div><div v-if="moduleTabs.length > 1" class="module-side-section"><strong>只读关联</strong><button v-for="tab in moduleTabs.filter(item => item.id !== 'catalog')" :key="tab.id" class="module-related-link" @click="selectModuleTab(tab.id)">查看{{ tab.label }} <ArrowRight :size="13" /></button></div><div class="module-side-note"><ShieldCheck :size="15" /><span>详情只读，修改操作需要接入后端 API。</span></div></template><template v-else><div class="module-side-heading"><h2>{{ navTitle }}概览</h2><span>演示</span></div><p>{{ sectionSummary(activeSection)[1] }}</p><div class="module-side-section"><strong>当前关注</strong><button v-for="row in sectionRecords(activeSection).filter(item => ['待审批', '需审批', '草稿', '未连接', '离线', '待处理'].includes(item.state))" :key="row.name" class="module-attention" @click="openModuleRecord(row)"><span class="attention-led"></span><span><b>{{ row.name }}</b><small>{{ row.state }} · {{ row.activity }}</small></span></button><div v-if="!sectionRecords(activeSection).some(item => ['待审批', '需审批', '草稿', '未连接', '离线', '待处理'].includes(item.state))" class="module-no-attention"><Check :size="14" />当前没有待处理项</div></div><div class="module-side-section"><strong>此模块包含</strong><ul><li v-for="item in moduleScope" :key="item">{{ item }}</li></ul></div><div class="module-side-note"><ShieldCheck :size="15" /><span>页面内容为本地演示数据。执行控制 API 接入后，资源状态将由后端提供。</span></div></template></aside></div>
          <footer class="page-footer"><span>Harness 控制面 · {{ navTitle }}规划视图</span><span><i class="footer-health demo-health"></i>演示数据 · 未连接运行 API</span><span>更新时间 14:33</span></footer>
        </section>
      </div></div>
      <div v-if="showAgentDialog" class="modal-backdrop" @click.self="showAgentDialog = false"><section class="dialog run-create-dialog" role="dialog" aria-modal="true" aria-labelledby="agent-create-title"><div class="dialog-heading"><div class="dialog-symbol"><Bot :size="19" /></div><button class="icon-button" type="button" aria-label="关闭新建 Agent" @click="showAgentDialog = false"><X :size="18" /></button></div><h2 id="agent-create-title">新建 Agent</h2><p>这里只保存 Agent 定义，不会创建执行任务。</p><label class="run-create-field"><span>名称</span><input v-model="agentDraft.name" placeholder="例如 support-analyst" autofocus /></label><label class="run-create-field"><span>版本</span><input v-model="agentDraft.version" placeholder="v1" /></label><label class="run-create-field"><span>模型路由</span><input v-model="agentDraft.model" placeholder="auto" /></label><label class="run-create-field"><span>说明</span><textarea v-model="agentDraft.description" rows="3" placeholder="描述 Agent 负责的任务范围"></textarea></label><div class="dialog-actions"><button class="secondary-button" type="button" @click="showAgentDialog = false">取消</button><button class="primary-button" type="button" @click="submitAgent">创建 Agent</button></div></section></div>
      <div v-if="showWorkspaceDialog" class="modal-backdrop" @click.self="showWorkspaceDialog = false"><section class="dialog run-create-dialog" role="dialog" aria-modal="true" aria-labelledby="workspace-create-title"><div class="dialog-heading"><div class="dialog-symbol"><Layers3 :size="19" /></div><button class="icon-button" type="button" aria-label="关闭新建工作空间" @click="showWorkspaceDialog = false"><X :size="18" /></button></div><h2 id="workspace-create-title">新建工作空间</h2><p>这里只保存仓库归属和分支，不会启动运行。</p><label class="run-create-field"><span>名称</span><input v-model="workspaceDraft.name" placeholder="例如 support-ops" autofocus /></label><label class="run-create-field"><span>仓库</span><input v-model="workspaceDraft.repository" placeholder="仓库标识或地址" /></label><label class="run-create-field"><span>分支</span><input v-model="workspaceDraft.branch" placeholder="main" /></label><div class="dialog-actions"><button class="secondary-button" type="button" @click="showWorkspaceDialog = false">取消</button><button class="primary-button" type="button" @click="submitWorkspace">创建工作空间</button></div></section></div>
      <div v-if="selectedEvaluationDataset" class="modal-backdrop" @click.self="selectedEvaluationDataset = null"><section class="dialog dataset-detail-dialog" role="dialog" aria-modal="true" aria-labelledby="dataset-detail-title"><div class="dialog-heading"><div class="dialog-symbol"><Gauge :size="19" /></div><button class="icon-button" type="button" aria-label="关闭测评集详情" @click="selectedEvaluationDataset = null"><X :size="18" /></button></div><h2 id="dataset-detail-title">{{ selectedEvaluationDataset.name }}</h2><p>{{ selectedEvaluationDataset.description || '维护输入、期望结果和评分规则。' }} · {{ selectedEvaluationDataset.case_count }} 条样本</p><div class="dataset-detail-toolbar"><strong>样本列表</strong><button class="button button-subtle" @click="openCaseDialog()"><Plus :size="14" />新增样本</button></div><div class="dataset-case-list"><article v-for="item in selectedEvaluationDataset.cases" :key="item.case_id" class="dataset-case-row"><div><strong>{{ item.case_id }}</strong><p>{{ item.input_text }}</p><small>期望输出：{{ item.expected_output || '未设置' }}</small></div><button class="text-action" @click="openCaseDialog(item)">编辑</button></article><div v-if="!selectedEvaluationDataset.cases.length" class="release-empty"><span>暂无样本</span></div></div><div class="dialog-actions"><button class="secondary-button" type="button" @click="selectedEvaluationDataset = null">关闭</button></div></section></div>
      <div v-if="showCaseDialog" class="modal-backdrop" @click.self="showCaseDialog = false"><section class="dialog run-create-dialog" role="dialog" aria-modal="true" aria-labelledby="case-create-title"><div class="dialog-heading"><div class="dialog-symbol"><FileText :size="19" /></div><button class="icon-button" type="button" aria-label="关闭样本编辑" @click="showCaseDialog = false"><X :size="18" /></button></div><h2 id="case-create-title">{{ caseDraft.caseId ? '编辑测评样本' : '新增测评样本' }}</h2><label class="run-create-field"><span>测试输入</span><textarea v-model="caseDraft.input" rows="4" placeholder="输入要回放的问题或任务" autofocus></textarea></label><label class="run-create-field"><span>期望输出</span><textarea v-model="caseDraft.expectedOutput" rows="3" placeholder="可选，填写期望结果"></textarea></label><label class="run-create-field"><span>评分规则 JSON</span><textarea v-model="caseDraft.rubric" rows="4" spellcheck="false"></textarea></label><div class="dialog-actions"><button class="secondary-button" type="button" @click="showCaseDialog = false">取消</button><button class="primary-button" type="button" @click="saveCase">保存样本</button></div></section></div>
      <div v-if="showDatasetDialog" class="modal-backdrop" @click.self="showDatasetDialog = false"><section class="dialog run-create-dialog" role="dialog" aria-modal="true" aria-labelledby="dataset-create-title"><div class="dialog-heading"><div class="dialog-symbol"><Gauge :size="19" /></div><button class="icon-button" type="button" aria-label="关闭新建测评集" @click="showDatasetDialog = false"><X :size="18" /></button></div><h2 id="dataset-create-title">新建测评集</h2><p>测评集只保存测试输入、期望结果和评分规则，不会创建执行任务。</p><label class="run-create-field"><span>测评集名称</span><input v-model="datasetDraft.name" placeholder="例如：客服全链路回归集" autofocus /></label><label class="run-create-field"><span>类型</span><select v-model="datasetDraft.datasetType"><option>通用</option><option>端到端</option><option>RAG</option><option>Tool calling</option><option>Memory</option></select></label><label class="run-create-field"><span>说明</span><textarea v-model="datasetDraft.description" rows="3" placeholder="描述测评集覆盖的能力范围"></textarea></label><div class="dialog-actions"><button class="secondary-button" type="button" @click="showDatasetDialog = false">取消</button><button class="primary-button" type="button" @click="submitDataset">创建测评集</button></div></section></div>
      <div v-if="showRunDialog" class="modal-backdrop" @click.self="showRunDialog = false"><section class="dialog run-create-dialog" role="dialog" aria-modal="true" aria-labelledby="run-create-title"><div class="dialog-heading"><div class="dialog-symbol"><Play :size="19" /></div><button class="icon-button" type="button" aria-label="关闭新建运行" @click="showRunDialog = false"><X :size="18" /></button></div><h2 id="run-create-title">新建执行任务</h2><p>提交一个独立的 Agent 运行。运行创建后只在“执行任务”页面管理。</p><label class="run-create-field"><span>执行模式</span><select v-model="runDraft.agent"><option value="chat">对话助手</option><option value="file">文件问答</option><option value="ppt">PPT 生成</option><option value="deep">深度研究</option><option value="skills">技能助手</option></select></label><label class="run-create-field"><span>任务内容</span><textarea v-model="runDraft.query" rows="5" placeholder="描述要执行的任务" autofocus></textarea></label><label class="run-create-field"><span>会话编号</span><input v-model="runDraft.conversationId" placeholder="可选，默认自动生成" /></label><label v-if="runDraft.agent === 'file' || runDraft.agent === 'skills'" class="run-create-field"><span>文件编号</span><input v-model="runDraft.fileId" placeholder="填写已上传文件或文档的 fileId" /></label><div class="dialog-actions"><button class="secondary-button" type="button" @click="showRunDialog = false">取消</button><button class="primary-button" type="button" :disabled="executionLoading" @click="submitRun">{{ executionLoading ? '提交中…' : '提交运行' }}</button></div></section></div>
      <div v-if="toast" class="toast-message"><Check :size="15" />{{ toast }}</div>
    </main>
  </div>
</template>
