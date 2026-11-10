<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import ExecutionRunDetails from './modules/execution/ExecutionRunDetails.vue'
import ArtifactList from './modules/artifacts/ArtifactList.vue'
import { useRunEvents } from './modules/execution/useRunEvents'
import { getHarnessAgent, updateHarnessAgent } from './api'
import { getHarnessWorkspace, updateHarnessWorkspace } from './api'
import { getHarnessTool, createHarnessTool, updateHarnessTool } from './api'
import { getHarnessModel, createHarnessModel, updateHarnessModel } from './api'
import { getSkillDetail, setSkillEnabled } from './api'
import { getCatalogSkills, getCatalogVersion, compareCatalogVersions } from './api'
import { bindCatalogSkill, callMcpTool, checkoutWorkspace, compareEvaluationRuns, downloadEvaluationRun, getApprovalNotifications, getHarnessOverview, getMachineErrors, getModelFallbackChain, getObservabilityExports, getObservabilityTrends, getReleaseObservations, getWorkspaceCheckout, observeReleaseRollout, unbindCatalogSkill } from './api'
import { Activity, Archive, ArrowDownToLine, ArrowRight, Bot, Boxes, Check, Clock3, Command, Cpu, FileText, Filter, Gauge, GitBranch, HardDrive, Layers3, ListChecks, Menu, MoreHorizontal, Network, Pause, Play, Plus, Search, Settings2, ShieldCheck, Sparkles, Square, Terminal, Workflow, Wrench, X } from 'lucide-vue-next'
import { cancelExecutionRun, createEvaluationDataset, createEvaluationRun, getEvaluationConfig, getEvaluationDatasets, getEvaluationRuns, saveEvaluationConfig, createExecutionRun, getExecutionRuns, getReleaseSummary, promoteRelease, evaluateReleaseGate, getReleaseGates, rollbackRelease, getHarnessAgents, createHarnessAgent, getHarnessWorkspaces, createHarnessWorkspace, getHarnessTools, getHarnessModels, getSkills, getHarnessMachines, getHarnessApprovals, decideHarnessApproval, getHarnessObservabilityRuns, retryExecutionRun, getEvaluationDataset, addEvaluationCase, updateEvaluationCase, deleteEvaluationCase, importEvaluationCases, createEvaluationSnapshot, getEvaluationSnapshots, getEvaluationRun, replayEvaluationRun, getReleaseRecords, advanceRollout, getReleaseConfig, saveReleaseConfig, getReleaseGateThresholds, saveReleaseGateThresholds, getHarnessApproval, decideHarnessApprovalsBatch, harnessApprovalAuditUrl, drainHarnessMachine, getHarnessTrace, getHarnessObservabilityMetrics, harnessTraceExportUrl, getHarnessSettings, saveHarnessSettings, getHarnessMcpServers, testHarnessTool, testHarnessModel, setHarnessAgentStatus, bindHarnessAgentSkills, unbindHarnessAgentSkill, getHarnessAgentVersions, getHarnessAgentDiff, getHarnessAgentRuns, getHarnessWorkspaceRuns, createHarnessWorkspaceSnapshot, getHarnessWorkspaceSnapshots, getHarnessWorkspaceChanges } from './api'

const sections = [
  { label: '控制平面', items: [{ id: 'overview', label: '运行总览', icon: Activity }, { id: 'runs', label: '执行任务', icon: ListChecks }, { id: 'evaluations', label: '测评中心', icon: Gauge }, { id: 'agents', label: 'Agent 实例', icon: Bot }, { id: 'workspaces', label: '工作空间', icon: Layers3 }] },
  { label: '能力注册表', items: [{ id: 'tools', label: '工具与 MCP', icon: Wrench }, { id: 'skills', label: 'Skills', icon: Sparkles }, { id: 'models', label: '模型路由', icon: Network }] },
  { label: '运行治理', items: [{ id: 'machines', label: '机器与运行时', icon: Cpu }, { id: 'approvals', label: '待审批', icon: ShieldCheck }, { id: 'artifacts', label: '产物与存储', icon: Archive }, { id: 'observability', label: '追踪与日志', icon: Terminal }, { id: 'releases', label: '发布治理', icon: GitBranch }, { id: 'settings', label: 'Harness 设置', icon: Settings2 }] },
]
const props = defineProps({ embedded: { type: Boolean, default: false }, apiBase: { type: String, default: '' } })
const runs = ref([])
const activeSection = ref('overview')
const activeView = ref('control')
const filter = ref('全部任务')
const search = ref('')
const selectedModuleRecord = ref(null)
const evaluationTab = ref('overview')
const selectedRunId = ref('')
const toast = ref('')
const mobileNavOpen = ref(false)
const runActionBusy = ref(false)
const executionLoaded = ref(false)
const executionConnected = ref(false)
const executionLoading = ref(false)
const executionError = ref('')
const executionTotal = ref(0)
const runOffset = ref(0)
const runPageSize = 25
const runSubmitBusy = ref(false)
let runListGeneration = 0
const showRunDialog = ref(false)
const runDraft = ref({ conversationId: '', agent: 'chat', query: '', fileId: '', agentId: '', workspaceId: '' })
let executionRefreshTimer
const sectionMode = computed(() => activeSection.value === 'artifacts' ? 'live' : activeSection.value === 'skills' ? ((skillDirectoryTab.value === 'catalog' ? catalogConnected.value : skillsConnected.value) ? 'live' : 'demo') : activeSection.value === 'models' ? (modelsConnected.value ? 'live' : 'demo') : activeSection.value === 'tools' ? (toolsConnected.value ? 'live' : 'demo') : ['overview', 'runs'].includes(activeSection.value) && executionConnected.value ? 'live' : activeSection.value === 'evaluations' && evaluationConnected.value ? 'live' : activeSection.value === 'releases' && releaseConnected.value ? 'live' : (activeSection.value === 'agents' ? agentsConnected.value : activeSection.value === 'workspaces' && workspacesConnected.value) ? 'live' : activeSection.value === 'settings' && settingsConnected.value ? 'live' : ['overview', 'runs', 'evaluations', 'releases', 'settings'].includes(activeSection.value) ? 'demo' : 'planned')
const sourceLabel = computed(() => activeSection.value === 'artifacts' ? '登记产物 · 只读' : activeSection.value === 'overview' ? '今日真实运行记录' : activeSection.value === 'skills' ? (skillDirectoryTab.value === 'catalog' ? (catalogConnected.value ? 'Catalog 版本目录' : 'Catalog 目录未连接') : skillsConnected.value ? '本地安装包目录' : '未连接 Skill 目录') : activeSection.value === 'models' ? (modelsConnected.value ? '模型路由登记数据' : '未连接模型目录') : activeSection.value === 'tools' ? (toolsConnected.value ? '工具登记数据' : '未连接工具目录') : ['overview', 'runs'].includes(activeSection.value) ? (executionConnected.value ? '运行服务数据' : executionLoaded.value ? '运行数据缓存 · 连接失败' : '运行服务未连接') : activeSection.value === 'evaluations' ? (evaluationConnected.value ? '实时测评数据 · 后台执行' : '未连接测评服务') : activeSection.value === 'releases' ? (releaseConnected.value ? '实时发布数据' : '未连接发布目录') : ['agents', 'workspaces'].includes(activeSection.value) ? ((activeSection.value === 'agents' ? agentsConnected.value : workspacesConnected.value) ? '实时资源目录' : '未连接资源目录') : activeSection.value === 'settings' ? (settingsConnected.value ? '实时设置' : '默认设置 · 未连接设置 API') : '未接入运行 API')
const canCreateRun = computed(() => ['overview', 'runs'].includes(activeSection.value))
const canRefreshStatus = computed(() => ['overview', 'runs', 'evaluations', 'releases', 'agents', 'workspaces', 'settings'].includes(activeSection.value))
const selectedRun = computed(() => {
  const base = runs.value.find(run => run.id === selectedRunId.value) || runs.value[0]
  if (!base) return null
  const detail = runDetail.value
  if (detail && detail.run_id === base.id) return { ...base, raw: { ...base.raw, ...detail } }
  return base
})
const { items: runEvents, loading: eventsLoading, error: eventsError, output: runOutput, streamState: eventsStreamState, refresh: refreshSelectedRunEvents } = useRunEvents(computed(() => activeSection.value === 'runs' ? selectedRun.value : undefined), () => props.apiBase)
const statusLabels = { queued: '排队中', running: '运行中', completed: '已完成', failed: '失败', cancelled: '已取消' }
const statusFilters = { '运行中': 'running', '排队中': 'queued', '已完成': 'completed', '失败': 'failed', '已取消': 'cancelled' }
watch([filter, search, () => props.apiBase], () => {
  runOffset.value = 0
  runs.value = []
  executionTotal.value = 0
  refreshExecutionRuns()
}, { flush: 'sync' })
const sectionCounts = computed(() => ({
  runs: executionTotal.value,
  evaluations: evalRuns.value.length,
  agents: harnessAgents.value.length,
  workspaces: harnessWorkspaces.value.length,
  tools: harnessTools.value.length,
  skills: harnessSkills.value.length,
  models: harnessModels.value.length,
  machines: harnessMachines.value.length,
  approvals: pendingApprovalRows.value.length,
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
    workspace: run.workspace_id || (run.file_id ? `file:${run.file_id}` : '未绑定工作空间'),
    agent: run.agent_id || run.agent || '通用执行 Agent',
    model: '由运行时路由',
    status,
    elapsed: formatRunElapsed(run),
    tokens: '—',
    cost: '—',
    phase: status === 'queued' ? '排队 · 等待运行时资源' : status === 'running' ? '运行中 · 等待事件更新' : status === 'failed' ? `失败 · ${run.error || '请查看运行事件'}` : status === 'cancelled' ? '已取消' : '执行完成',
    raw: run,
  }
}

async function refreshExecutionRuns({ silent = false } = {}) {
  const request = ++runListGeneration
  executionLoading.value = true
  try {
    const result = await getExecutionRuns(props.apiBase, {
      limit: runPageSize, offset: runOffset.value,
      status: statusFilters[filter.value], search: search.value.trim(),
    })
    if (request !== runListGeneration) return
    executionTotal.value = result.total
    if (result.total > 0 && runOffset.value >= result.total) {
      runOffset.value = Math.floor((result.total - 1) / runPageSize) * runPageSize
      return refreshExecutionRuns({ silent })
    }
    if (!result.total) runOffset.value = 0
    const items = (result?.items || []).map(normalizeRun)
    runs.value = items
    executionLoaded.value = true
    executionConnected.value = true
    executionError.value = ''
    if (items.length && !items.some(run => run.id === selectedRunId.value)) selectedRunId.value = items[0].id
  } catch (error) {
    if (request !== runListGeneration) return
    executionConnected.value = false
    executionError.value = error.message || '运行服务暂不可用'
    if (!silent) notify(`运行状态刷新失败：${executionError.value}`)
  } finally {
    if (request === runListGeneration) executionLoading.value = false
  }
}

function changeRunPage(offset) {
  runOffset.value = offset
  runs.value = []
  refreshExecutionRuns()
}

async function revealCreatedRun(run) {
  filter.value = '全部任务'
  search.value = ''
  runOffset.value = 0
  runs.value = [run]
  executionTotal.value = 1
  selectedRunId.value = run.id
  await refreshExecutionRuns({ silent: true })
}

function openCreateRun() {
  runDraft.value = { conversationId: `harness-${Date.now()}`, agent: 'chat', query: '', fileId: '', agentId: '', workspaceId: '' }
  showRunDialog.value = true
}

function duplicateSelectedRun() {
  const raw = selectedRun.value?.raw
  if (!raw) return
  runDraft.value = {
    conversationId: `harness-${Date.now()}`,
    agent: raw.agent || 'chat',
    query: raw.query || '',
    fileId: raw.file_id || '',
  }
  activeSection.value = 'runs'
  showRunDialog.value = true
  notify('已复制运行配置，提交后会创建新的运行')
}

async function submitRun() {
  if (runSubmitBusy.value) return
  if (!runDraft.value.query.trim()) {
    notify('请输入执行任务')
    return
  }
  try {
    runSubmitBusy.value = true
    const result = await createExecutionRun(props.apiBase, {
      conversationId: runDraft.value.conversationId.trim() || `harness-${Date.now()}`,
      agent: runDraft.value.agent,
      query: runDraft.value.query.trim(),
      fileId: runDraft.value.fileId.trim() || null,
      agentId: runDraft.value.agentId.trim() || null,
      workspaceId: runDraft.value.workspaceId.trim() || null,
    })
    const run = normalizeRun(result.run)
    executionLoaded.value = true
    executionConnected.value = true
    activeSection.value = 'runs'
    activeView.value = 'control'
    showRunDialog.value = false
    notify(`${run.id} 已加入执行队列`)
    await revealCreatedRun(run)
  } catch (error) {
    notify(`创建运行失败：${error.message || '运行服务不可用'}`)
  } finally {
    runSubmitBusy.value = false
  }
}

async function stopSelectedRun() {
  const runId = selectedRun.value?.id
  if (!runId || runActionBusy.value) return
  runActionBusy.value = true
  try {
    const result = await cancelExecutionRun(props.apiBase, runId)
    notify(result.message || '停止请求已提交')
    await refreshExecutionRuns({ silent: true })
  } catch (error) { notify(`停止运行失败：${error.message}`) }
  finally { runActionBusy.value = false }
}

async function retrySelectedRun() {
  const runId = selectedRun.value?.id
  if (!runId || runActionBusy.value) return
  runActionBusy.value = true
  try {
    const result = await retryExecutionRun(props.apiBase, runId)
    const run = normalizeRun(result.run)
    await revealCreatedRun(run)
    notify(`${run.id} 已重新加入执行队列`)
  } catch (error) { notify(`重试运行失败：${error.message}`) }
  finally { runActionBusy.value = false }
}

function selectSection(id) {
  activeSection.value = id
  mobileNavOpen.value = false
  activeView.value = 'control'
  selectedModuleRecord.value = null
  if (id === 'observability') { loadTraceEvents(); loadTraceMetrics(); loadTraceTrends() }
}
const evalDatasets = ref([])
const defaultDimensionLabels = ['端到端任务完成', 'RAG 事实一致性', '工具调用正确性', '多轮记忆保持']
const evaluationConfig = ref({ dimensions: defaultDimensionLabels.map(label => ({ label, enabled: true })), gates: [] })
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
const harnessSettings = ref({ isolation: 'container', auditRetentionDays: 30, approvalPolicy: 'risk-based', defaultBudgetUsd: 0.2, defaultTimeoutSeconds: 900, defaultRetryCount: 1 })
const settingsConnected = ref(false)
const settingsError = ref('')
const harnessAgents = ref([])
const agentsConnected = ref(false)
const agentsError = ref('')
const harnessWorkspaces = ref([])
const workspacesConnected = ref(false)
const workspacesError = ref('')
const resourceConnected = computed(() => machinesConnected.value || approvalsConnected.value || traceConnected.value)
const resourceError = ref('')
const showAgentDialog = ref(false)
const editingAgent = ref(null)
const agentSaving = ref(false)
const agentError = ref('')
const agentPolicyText = ref('{}')
const agentStatusBusy = ref('')
const agentVersions = ref([])
const agentVersionsBusy = ref(false)
const agentDiffBase = ref('')
const agentDiffTarget = ref('')
const agentDiff = ref(null)
const agentDiffBusy = ref(false)
const agentDiffError = ref('')
const agentRuns = ref([])
const agentRunsBusy = ref(false)
const agentRunsError = ref('')
const agentSkillPick = ref('')
const agentSkillInput = ref('')
const agentSkillBusy = ref(false)
const agentSkillError = ref('')
const showWorkspaceDialog = ref(false)
const editingWorkspace = ref(null)
const workspaceSaving = ref(false)
const workspaceError = ref('')
const workspaceSnapshots = ref([])
const workspaceChanges = ref([])
const workspaceRuns = ref([])
const workspaceSelectedSnapshotId = ref('')
const workspaceSnapshotBusy = ref(false)
const workspaceSnapshotError = ref('')
const workspaceChangesError = ref('')
const workspaceRunsError = ref('')
const agentDraft = ref({ name: '', description: '', version: 'v1', model: 'auto' })
const workspaceDraft = ref({ name: '', repository: '', branch: 'main' })
const harnessTools = ref([])
const toolsConnected = ref(false)
const toolsError = ref('')
const showToolDialog = ref(false)
const editingTool = ref(null)
const toolSaving = ref(false)
const toolError = ref('')
const toolTestBusy = ref('')
const toolTestResults = ref({})
const harnessMcpServers = ref([])
const mcpServersError = ref('')
const toolDraft = ref({ name: '', source: 'mcp', scope: 'workspace', risk: 'low', status: 'configured', description: '', approval_policy: 'risk-based' })
const toolSchemaText = ref('{"type":"object","properties":{}}')
const harnessModels = ref([])
const modelsConnected = ref(false)
const modelsError = ref('')
const showModelDialog = ref(false)
const editingModel = ref(null)
const modelSaving = ref(false)
const modelError = ref('')
const modelTestBusy = ref('')
const modelTestResults = ref({})
const modelFallbackChain = ref([])
const modelDraft = ref({ name: '', provider: '', route: 'default', status: 'configured', cost_policy: '', fallback_model_id: null })
const harnessSkills = ref([])
const skillsConnected = ref(false)
const skillsError = ref('')
const selectedSkill = ref(null)
const skillChangingId = ref('')
const skillChangeError = ref('')
const skillDirectoryTab = ref('installed')
const catalog = ref({ project: '', skills: [], bindings: [], rollouts: [] })
const catalogLoading = ref(false)
const catalogConnected = ref(false)
const catalogError = ref('')
const selectedCatalogName = ref('')
const catalogVersion = ref('')
const catalogBaseVersion = ref('')
const catalogDetail = ref(null)
const catalogComparison = ref(null)
const catalogDetailBusy = ref(false)
const catalogDetailError = ref('')
const catalogNames = computed(() => [...new Set(catalog.value.skills.map(item => item.name))])
const catalogVersions = computed(() => catalog.value.skills.filter(item => item.name === selectedCatalogName.value))
const harnessMachines = ref([])
const harnessApprovals = ref([])
const harnessTraceRuns = ref([])
const machinesConnected = ref(false)
const approvalsConnected = ref(false)
const traceConnected = ref(false)
const machineBusy = ref('')
const datasetBusy = ref('')
const runDetail = ref(null)
const overviewStats = ref(null)
const machineErrors = ref([])
const machineErrorWorker = ref('')
const machineErrorsBusy = ref(false)
const machineErrorsError = ref('')
const approvalSelection = ref([])
const approvalDetail = ref(null)
const approvalDetailBusy = ref(false)
const approvalBusy = ref(false)
const rejectDialog = ref(null)
const rejectReason = ref('')
const selectedTraceRunId = ref('')
const traceEvents = ref([])
const traceEventsBusy = ref(false)
const traceEventsError = ref('')
const traceFilters = ref({ level: '', tool: '', hasError: false, since: '', until: '', type: '' })
const traceMetrics = ref(null)
const evalRunItems = ref([])
const evalRunDetail = ref(null)
const evalRunCases = ref([])
const evalRunBusy = ref(false)
const evalPolling = ref(false)
const evalRunStatus = ref('')
const evalRuns = ref([])
const evalGates = ref([])
const evalRunDataset = ref(null)
const evalProgress = ref('')
const evalReplayRuns = ref({})
const evalSnapshots = ref([])
const snapshotBusy = ref(false)
const showImportDialog = ref(false)
const importCasesText = ref('')
const importBusy = ref(false)
const releaseRecords = ref([])
const approvalNotifications = ref([])
const notificationsBusy = ref(false)
const notificationsError = ref('')
const evalCompareBase = ref('')
const evalCompareTarget = ref('')
const evalComparison = ref(null)
const evalComparisonBusy = ref(false)
const evalComparisonError = ref('')
const evalExportRunId = ref('')
const releaseObservations = ref([])
const observationsBusy = ref(false)
const observationBusy = ref('')
const observationError = ref('')
const mcpToolPick = ref('')
const mcpCallArgs = ref('{}')
const mcpCallResult = ref(null)
const mcpCallBusy = ref(false)
const mcpCallError = ref('')
const workspaceCheckout = ref(null)
const checkoutBusy = ref(false)
const checkoutError = ref('')
const catalogBindPercentage = ref(0)
const catalogBindBusy = ref(false)
const catalogBindError = ref('')
const traceTrendBucket = ref('hour')
const traceTrends = ref([])
const trendsBusy = ref(false)
const trendsError = ref('')
const exportFrom = ref('')
const exportTo = ref('')
const exportRunId = ref('')
const exportBusy = ref(false)
const exportError = ref('')
const releaseThresholdsDraft = ref({ e2ePassRate: null, ragFaithfulness: null, highRiskErrors: null })
const releaseConfigDraft = ref({ rolloutErrorThreshold: null, rolloutMinSamples: null, autoRollback: true })
const releasePolicyBusy = ref(false)
const rolloutBusy = ref('')
const rolloutAdvanceDrafts = ref({})
const releaseRecordsBusy = ref(false)
const releaseRecordsError = ref('')
const releaseThresholdsBusy = ref(false)
const releasePolicyLoading = ref(false)
const releasePolicyError = ref('')
const agentRows = computed(() => harnessAgents.value)
const workspaceRows = computed(() => harnessWorkspaces.value)
const toolRows = computed(() => harnessTools.value)
const modelRows = computed(() => harnessModels.value)
const skillRows = computed(() => harnessSkills.value)
function formatWorkerSeen(value) {
  if (value == null) return '—'
  const stamp = typeof value === 'number' ? value * 1000 : Date.parse(value)
  if (!Number.isFinite(stamp)) return String(value)
  const seconds = Math.max(0, Math.round((Date.now() - stamp) / 1000))
  if (seconds < 5) return '刚刚'
  if (seconds < 60) return `${seconds} 秒前`
  if (seconds < 3600) return `${Math.round(seconds / 60)} 分钟前`
  if (seconds < 86400) return `${Math.round(seconds / 3600)} 小时前`
  return `${Math.round(seconds / 86400)} 天前`
}
const machineRows = computed(() => harnessMachines.value)
const approvalRows = computed(() => harnessApprovals.value)
const onlineWorkerCount = computed(() => machineRows.value.filter(row => row.state !== 'offline').length)
const traceRunRows = computed(() => harnessTraceRuns.value)
const pendingApprovalRows = computed(() => approvalRows.value.filter(row => row.status === 'pending'))
const selectedTraceRun = computed(() => traceRunRows.value.find(row => row.run_id === selectedTraceRunId.value) || traceRunRows.value[0] || null)
async function refreshEvaluationData({ silent = false } = {}) {
  try {
    const [datasets, config, reports] = await Promise.all([
      getEvaluationDatasets(props.apiBase),
      getEvaluationConfig(props.apiBase),
      getEvaluationRuns(props.apiBase),
    ])
    const items = (datasets?.items || []).map(item => ({ name: item.name, type: item.dataset_type, cases: String(item.case_count || 0), caseCount: Number(item.case_count || 0), pass: '—', delta: '', state: '未运行', updated: item.updated_at || '刚刚', datasetId: item.dataset_id }))
    evalDatasets.value = items
    if (items.length && !items.some(item => item.datasetId === selectedEvaluationDatasetId.value)) selectedEvaluationDatasetId.value = items[0].datasetId || ''
    const nextConfig = config?.config
    if (nextConfig) {
      evaluationConfig.value = { ...evaluationConfig.value, ...nextConfig, dimensions: Array.isArray(nextConfig.dimensions) ? nextConfig.dimensions : evaluationConfig.value.dimensions }
    }
    evalRuns.value = reports?.items || []
    evaluationConnected.value = true
    evaluationError.value = ''
  } catch (error) {
    evaluationConnected.value = false
    evalRuns.value = []
    evaluationError.value = error.message || '测评服务暂不可用'
    if (!silent) notify(`测评数据刷新失败：${evaluationError.value}`)
  }
  try {
    const gates = await getReleaseGates(props.apiBase)
    evalGates.value = gates?.items || []
  } catch {
    evalGates.value = []
  }
}

function formatPercentNumber(value, digits = 1) {
  if (value == null || value === '') return null
  const num = Number(value)
  if (!Number.isFinite(num)) return null
  return (num <= 1 ? num * 100 : num).toFixed(digits)
}

function evalStatusLabel(status) {
  return ({ running: '运行中', queued: '排队中', completed: '已完成', failed: '未通过', blocked: '已阻塞' })[status] || status || '未知'
}

function evalVerdictLabel(verdict) {
  return ({ passed: '通过', failed: '失败', timeout: '超时', not_scored: '未评分', invalid_rubric: '规则无效' })[verdict] || verdict || '未知'
}
const latestEvalRun = computed(() => evalRuns.value[0] || null)
const latestEvalSummary = computed(() => latestEvalRun.value?.summary || null)
const evalCaseTotal = computed(() => evalDatasets.value.reduce((sum, item) => sum + (Number(item.caseCount) || 0), 0))
const evalPassRateText = computed(() => {
  const value = formatPercentNumber(latestEvalSummary.value?.passRate)
  return value === null ? '—' : `${value}%`
})
const latestGate = computed(() => evalGates.value[0] || null)
const gateCheckRows = computed(() => {
  const gate = latestGate.value
  if (!gate) return []
  const checks = gate.checks || {}
  const thresholds = gate.thresholds || {}
  return [
    { label: '端到端通过率', threshold: thresholds.e2ePassRate, format: 'percent', passed: checks.e2ePassRate },
    { label: 'RAG 忠实度', threshold: thresholds.ragFaithfulness, format: 'decimal', passed: checks.ragFaithfulness },
    { label: '高风险工具误调用', threshold: thresholds.highRiskErrors, format: 'count', passed: checks.highRiskErrors },
  ].map(row => ({
    ...row,
    value: row.threshold == null ? '—' : row.format === 'percent' ? (formatPercentNumber(row.threshold) === null ? '—' : `${formatPercentNumber(row.threshold)}%`) : row.format === 'decimal' ? Number(row.threshold).toFixed(2) : String(row.threshold),
  }))
})
const configuredDimensions = computed(() => (evaluationConfig.value.dimensions || []).filter(item => item && (item.label || item.name)))
const dimensionRows = computed(() => {
  const source = configuredDimensions.value.length ? configuredDimensions.value : defaultDimensionLabels.map(label => ({ label }))
  return source.map((item, index) => ({
    label: item.label || item.name,
    enabled: item.enabled !== false,
    color: ['green', 'blue', 'orange', 'purple'][index % 4],
    score: '—',
    value: 0,
    note: latestEvalSummary.value ? `最近一次测评整体通过率 ${evalPassRateText.value}` : '暂无真实测评结果',
    demo: !configuredDimensions.value.length,
  }))
})
const evalReports = computed(() => evalRuns.value.map(run => ({
  runId: run.eval_run_id,
  score: formatPercentNumber(run.summary?.passRate) === null ? '—' : `${formatPercentNumber(run.summary?.passRate)}%`,
  date: run.created_at || '—',
  state: evalStatusLabel(run.status),
  error: run.error || '',
})))
const evalCaseMap = computed(() => {
  const map = {}
  for (const item of evalRunDataset.value?.cases || []) map[item.case_id] = item
  return map
})
function evalCaseInput(caseId) { return evalCaseMap.value[caseId]?.input_text || '未记录' }
function evalCaseExpected(caseId) { return evalCaseMap.value[caseId]?.expected_output || '未设置' }
function selectedDatasetCaseCount() {
  const row = evalDatasets.value.find(item => item.datasetId === selectedEvaluationDatasetId.value)
  return row ? Number(row.caseCount) || 0 : 0
}

async function openEvalRun(runId) {
  if (evalRunBusy.value) return
  evalRunBusy.value = true
  try {
    const detail = await getEvaluationRun(props.apiBase, runId)
    evalRunDetail.value = detail.run || null
    evalRunCases.value = detail.results || []
    evalRunDataset.value = null
    const datasetId = detail.run?.dataset_id
    if (datasetId) {
      const dataset = await getEvaluationDataset(props.apiBase, datasetId)
      evalRunDataset.value = dataset.dataset || null
    }
  } catch (error) {
    notify(`读取测评运行失败：${error.message || '测评服务不可用'}`)
  } finally {
    evalRunBusy.value = false
  }
}

async function replayEvalCase(runId, caseId) {
  try {
    const result = await replayEvaluationRun(props.apiBase, runId, [caseId])
    const items = result.runs || []
    if (!items.length) { notify('该样本没有可回放的失败记录'); return }
    notify(`回放运行已进入执行队列：${items.map(item => item.runId).join('、')}`)
  } catch (error) {
    notify(`回放失败：${error.message || '测评服务不可用'}`)
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
    await loadDatasetSnapshots(dataset.datasetId)
  } catch (error) { notify(`读取测评集失败：${error.message || '测评服务不可用'}`) }
}

function openCaseDialog(caseItem = null) {
  caseDraft.value = { caseId: caseItem?.case_id || '', input: caseItem?.input_text || '', expectedOutput: caseItem?.expected_output || '', rubric: JSON.stringify(caseItem?.rubric || {}, null, 2) }
  showCaseDialog.value = true
}

async function refreshSelectedDataset() {
  const datasetId = selectedEvaluationDataset.value?.dataset_id
  if (!datasetId) return
  const result = await getEvaluationDataset(props.apiBase, datasetId)
  selectedEvaluationDataset.value = result.dataset
}

async function deleteDatasetCase(caseItem) {
  const datasetId = selectedEvaluationDataset.value?.dataset_id
  if (!datasetId || !caseItem?.case_id) return
  if (!window.confirm(`确认删除样本 ${caseItem.case_id}？删除后不可恢复。`)) return
  try {
    await deleteEvaluationCase(props.apiBase, datasetId, caseItem.case_id)
    await refreshSelectedDataset()
    await refreshEvaluationData({ silent: true })
    notify('测评样本已删除')
  } catch (error) { notify(`删除测评样本失败：${error.message || '测评服务不可用'}`) }
}

function openImportCasesDialog() {
  importCasesText.value = ''
  showImportDialog.value = true
}

function readNumberField(value) {
  if (value === null || value === undefined || value === '') return null
  const num = Number(value)
  return Number.isFinite(num) ? num : null
}

async function submitImportCases() {
  const datasetId = selectedEvaluationDataset.value?.dataset_id
  if (!datasetId) return notify('请先打开一个真实测评集')
  const text = importCasesText.value.trim()
  if (!text) return notify('请粘贴要导入的 JSON 数组')
  let parsed
  try { parsed = JSON.parse(text) } catch (error) { return notify(`JSON 解析失败：${error.message}`) }
  if (!Array.isArray(parsed)) return notify('导入内容必须是 JSON 数组，例如 [{"input":"问题"}]')
  if (!parsed.length) return notify('导入数组不能为空')
  const invalidIndex = parsed.findIndex(item => !item || typeof item !== 'object' || !String(item.input ?? '').trim())
  if (invalidIndex >= 0) return notify(`第 ${invalidIndex + 1} 条样本缺少非空的 input 字段`)
  if (importBusy.value) return
  importBusy.value = true
  try {
    const result = await importEvaluationCases(props.apiBase, datasetId, parsed.map(item => ({
      input: String(item.input).trim(),
      expectedOutput: item.expectedOutput == null ? '' : String(item.expectedOutput),
      rubric: item.rubric && typeof item.rubric === 'object' ? item.rubric : {},
    })))
    showImportDialog.value = false
    await refreshSelectedDataset()
    await refreshEvaluationData({ silent: true })
    notify(`已导入 ${result.created ?? parsed.length} 条样本`)
  } catch (error) { notify(`批量导入失败：${error.message || '测评服务不可用'}`) }
  finally { importBusy.value = false }
}

async function loadDatasetSnapshots(datasetId) {
  try {
    const result = await getEvaluationSnapshots(props.apiBase, datasetId)
    evalSnapshots.value = result?.items || []
  } catch (error) {
    evalSnapshots.value = []
    notify(`读取版本快照失败：${error.message || '测评服务不可用'}`)
  }
}

async function saveDatasetSnapshot() {
  const datasetId = selectedEvaluationDataset.value?.dataset_id
  if (!datasetId) return notify('请先打开一个真实测评集')
  if (snapshotBusy.value) return
  snapshotBusy.value = true
  try {
    const result = await createEvaluationSnapshot(props.apiBase, datasetId)
    await loadDatasetSnapshots(datasetId)
    await refreshEvaluationData({ silent: true })
    notify(`已保存版本快照 v${result?.snapshot?.version ?? '—'}`)
  } catch (error) { notify(`保存版本快照失败：${error.message || '测评服务不可用'}`) }
  finally { snapshotBusy.value = false }
}

async function saveCase() {
  if (!selectedEvaluationDataset.value?.dataset_id || !caseDraft.value.input.trim()) return notify('请输入测试输入')
  let rubric
  try { rubric = JSON.parse(caseDraft.value.rubric || '{}') } catch { notify('评分规则必须是合法 JSON'); return }
  try {
    const payload = { input: caseDraft.value.input.trim(), expectedOutput: caseDraft.value.expectedOutput, rubric }
    if (caseDraft.value.caseId) await updateEvaluationCase(props.apiBase, selectedEvaluationDataset.value.dataset_id, caseDraft.value.caseId, payload)
    else await addEvaluationCase(props.apiBase, selectedEvaluationDataset.value.dataset_id, payload)
    await refreshSelectedDataset()
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
  if (evalRunBusy.value) return
  evalRunBusy.value = true
  evalPolling.value = true
  evalProgress.value = '测评进行中…（已通过 0/0）'
  try {
    const result = await createEvaluationRun(props.apiBase, { datasetId, agent: 'chat', version: 'current' })
    const runId = result.run?.eval_run_id
    if (!runId) throw new Error(result.message || '测评服务未返回运行编号')
    await pollEvaluationRun(runId, selectedDatasetCaseCount())
  } catch (error) {
    evalPolling.value = false
    notify(`创建测评任务失败：${error.message || '测评服务不可用'}`)
  } finally {
    evalRunBusy.value = false
  }
}

async function pollEvaluationRun(runId, total) {
  const deadline = Date.now() + 120000
  while (Date.now() < deadline) {
    const detail = await getEvaluationRun(props.apiBase, runId)
    const run = detail.run || {}
    const results = detail.results || []
    const passed = results.filter(item => item.verdict === 'passed').length
    evalProgress.value = `测评进行中…（已通过 ${passed}/${total || results.length}）`
    if (!['running', 'queued'].includes(run.status)) {
      evalPolling.value = false
      evalRunDetail.value = run
      evalRunCases.value = results
      evalRunDataset.value = null
      if (run.dataset_id) {
        try {
          const dataset = await getEvaluationDataset(props.apiBase, run.dataset_id)
          evalRunDataset.value = dataset.dataset || null
        } catch {
          // 样本输入取不到时只展示结果字段
        }
      }
      await refreshEvaluationData({ silent: true })
      const rateText = formatPercentNumber(run.summary?.passRate)
      const rateLabel = rateText === null ? '—' : `${rateText}%`
      if (run.status === 'completed') {
        evalProgress.value = `测评完成：通过 ${passed}/${total || results.length}，通过率 ${rateLabel}`
        notify(`测评完成，通过率 ${rateLabel}`)
      } else {
        evalProgress.value = `测评${evalStatusLabel(run.status)}：${run.error || '后端未返回错误说明'}`
        notify(evalProgress.value)
      }
      return
    }
    await new Promise(resolve => window.setTimeout(resolve, 3000))
  }
  evalPolling.value = false
  notify('测评仍在后台执行，请稍后刷新查看结果')
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
    rolloutAdvanceDrafts.value = Object.fromEntries(releaseRollouts.value.map(row => [rolloutKey(row), Math.min(100, (Number(row.percentage) || 0) + 10)]))
    releaseConnected.value = true
    releaseError.value = ''
  } catch (error) {
    releaseConnected.value = false
    releaseError.value = error.message || '发布治理服务暂不可用'
    if (!silent) notify(`发布数据刷新失败：${releaseError.value}`)
  }
  await Promise.all([loadReleaseRecords(), loadReleasePolicy(), loadReleaseObservations()])
}

function rolloutKey(row) {
  return `${row.project}-${row.name}`
}

async function loadReleaseRecords() {
  releaseRecordsBusy.value = true
  try {
    const result = await getReleaseRecords(props.apiBase)
    releaseRecords.value = result?.items || []
    releaseRecordsError.value = ''
  } catch (error) {
    releaseRecords.value = []
    releaseRecordsError.value = error.message || '发布记录暂不可用'
  } finally { releaseRecordsBusy.value = false }
}

async function loadReleasePolicy() {
  releasePolicyLoading.value = true
  try {
    const [thresholds, config] = await Promise.all([getReleaseGateThresholds(props.apiBase), getReleaseConfig(props.apiBase)])
    releaseThresholdsDraft.value = {
      e2ePassRate: thresholds?.thresholds?.e2ePassRate ?? null,
      ragFaithfulness: thresholds?.thresholds?.ragFaithfulness ?? null,
      highRiskErrors: thresholds?.thresholds?.highRiskErrors ?? null,
    }
    releaseConfigDraft.value = {
      rolloutErrorThreshold: config?.config?.rolloutErrorThreshold ?? null,
      rolloutMinSamples: config?.config?.rolloutMinSamples ?? null,
      autoRollback: config?.config?.autoRollback !== false,
    }
    releasePolicyError.value = ''
  } catch (error) {
    releasePolicyError.value = error.message || '门禁阈值与发布策略暂不可用'
  } finally { releasePolicyLoading.value = false }
}

async function saveReleaseThresholds() {
  const e2ePassRate = readNumberField(releaseThresholdsDraft.value.e2ePassRate)
  const ragFaithfulness = readNumberField(releaseThresholdsDraft.value.ragFaithfulness)
  const highRiskErrors = readNumberField(releaseThresholdsDraft.value.highRiskErrors)
  if (e2ePassRate === null || e2ePassRate < 0 || e2ePassRate > 1) return notify('端到端通过率阈值需在 0 到 1 之间')
  if (ragFaithfulness === null || ragFaithfulness < 0 || ragFaithfulness > 1) return notify('RAG 忠实度阈值需在 0 到 1 之间')
  if (highRiskErrors === null || !Number.isInteger(highRiskErrors) || highRiskErrors < 0) return notify('高风险工具误调用上限需为不小于 0 的整数')
  if (releaseThresholdsBusy.value) return
  releaseThresholdsBusy.value = true
  try {
    await saveReleaseGateThresholds(props.apiBase, { e2ePassRate, ragFaithfulness, highRiskErrors })
    notify('门禁阈值已保存')
  } catch (error) { notify(`保存门禁阈值失败：${error.message || '发布治理服务不可用'}`) }
  finally { releaseThresholdsBusy.value = false }
}

async function saveReleasePolicy() {
  const rolloutErrorThreshold = readNumberField(releaseConfigDraft.value.rolloutErrorThreshold)
  const rolloutMinSamples = readNumberField(releaseConfigDraft.value.rolloutMinSamples)
  if (rolloutErrorThreshold === null || rolloutErrorThreshold < 0 || rolloutErrorThreshold > 1) return notify('错误率阈值需在 0 到 1 之间')
  if (rolloutMinSamples === null || !Number.isInteger(rolloutMinSamples) || rolloutMinSamples < 0) return notify('观察最小样本数需为不小于 0 的整数')
  if (releasePolicyBusy.value) return
  releasePolicyBusy.value = true
  try {
    await saveReleaseConfig(props.apiBase, { rolloutErrorThreshold, rolloutMinSamples, autoRollback: !!releaseConfigDraft.value.autoRollback })
    notify('发布策略已保存')
  } catch (error) { notify(`保存发布策略失败：${error.message || '发布治理服务不可用'}`) }
  finally { releasePolicyBusy.value = false }
}

async function advanceRolloutRow(row) {
  const percentage = readNumberField(rolloutAdvanceDrafts.value[rolloutKey(row)])
  if (percentage === null || percentage < 0 || percentage > 100) return notify('灰度比例需在 0 到 100 之间')
  if (rolloutBusy.value) return
  rolloutBusy.value = rolloutKey(row)
  try {
    await advanceRollout(props.apiBase, { project: row.project, name: row.name, version: row.candidate_version, percentage })
    await refreshReleaseData({ silent: true })
    notify(`${row.name} 灰度已推进到 ${percentage}%`)
  } catch (error) { notify(`推进灰度失败：${error.message || '发布治理服务不可用'}`) }
  finally { rolloutBusy.value = '' }
}

function releaseActionLabel(action) {
  return ({ promote: '发布', rollback: '回滚', advance: '推进灰度', auto_rollback: '自动回滚' })[action] || action || '—'
}

function releaseRecordChecks(record) {
  const checks = record?.checks || {}
  const thresholds = record?.thresholds || {}
  if (!Object.keys(checks).length) return []
  return [
    { label: '端到端通过率', threshold: thresholds.e2ePassRate, passed: checks.e2ePassRate },
    { label: 'RAG 忠实度', threshold: thresholds.ragFaithfulness, passed: checks.ragFaithfulness },
    { label: '高风险误调用', threshold: thresholds.highRiskErrors, passed: checks.highRiskErrors },
  ]
}
const releaseRecordRows = computed(() => releaseRecords.value.map(row => ({
  ...row,
  actionLabel: releaseActionLabel(row.action),
  checks: releaseRecordChecks(row),
})))
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

async function loadApprovalNotifications() {
  if (notificationsBusy.value) return
  notificationsBusy.value = true
  try {
    const result = await getApprovalNotifications(props.apiBase, { limit: 50 })
    approvalNotifications.value = result.items || []
    notificationsError.value = ''
  } catch (error) {
    approvalNotifications.value = []
    notificationsError.value = error.message || '审批通知读取失败'
  } finally { notificationsBusy.value = false }
}

async function compareEvalRuns() {
  if (!evalCompareBase.value || !evalCompareTarget.value) { evalComparisonError.value = '请选择基线和目标测评运行'; return }
  if (evalCompareBase.value === evalCompareTarget.value) { evalComparisonError.value = '请选择两次不同的测评运行'; return }
  evalComparisonBusy.value = true
  evalComparisonError.value = ''
  evalComparison.value = null
  try {
    evalComparison.value = await compareEvaluationRuns(props.apiBase, evalCompareBase.value, evalCompareTarget.value)
  } catch (error) { evalComparisonError.value = error.message || '报告对比失败' }
  finally { evalComparisonBusy.value = false }
}

async function exportEvalRunSamples(format) {
  if (!evalExportRunId.value) { notify('请选择要导出的测评运行'); return }
  try {
    const blob = await downloadEvaluationRun(props.apiBase, evalExportRunId.value, format)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `evaluation-${evalExportRunId.value}.${format}`
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    notify(`已导出测评运行 ${evalExportRunId.value}`)
  } catch (error) { notify(`导出失败：${error.message || '测评服务不可用'}`) }
}

async function loadReleaseObservations() {
  if (observationsBusy.value) return
  observationsBusy.value = true
  try {
    const result = await getReleaseObservations(props.apiBase, { limit: 50 })
    releaseObservations.value = result.items || []
    observationError.value = ''
  } catch (error) {
    releaseObservations.value = []
    observationError.value = error.message || '观察记录读取失败'
  } finally { observationsBusy.value = false }
}

async function observeRollout(row) {
  if (observationBusy.value) return
  observationBusy.value = rolloutKey(row)
  observationError.value = ''
  try {
    const result = await observeReleaseRollout(props.apiBase, { project: row.project || '', name: row.name, version: row.candidate_version || undefined })
    notify(result.rolledBack ? `错误率超阈值，已自动回滚：${result.detail}` : `观察完成：${result.detail || '无异常'}`)
    await Promise.all([loadReleaseObservations(), refreshReleaseData({ silent: true })])
  } catch (error) {
    observationError.value = error.message || '灰度观察失败'
    notify(`观察失败：${observationError.value}`)
  } finally { observationBusy.value = '' }
}

async function callSelectedMcpTool() {
  if (!mcpToolPick.value) { mcpCallError.value = '请选择要调用的工具'; return }
  let args = {}
  try { args = mcpCallArgs.value.trim() ? JSON.parse(mcpCallArgs.value) : {} }
  catch { mcpCallError.value = '调用参数不是合法 JSON'; return }
  const [toolId, toolName] = mcpToolPick.value.split('::')
  mcpCallBusy.value = true
  mcpCallError.value = ''
  mcpCallResult.value = null
  try {
    mcpCallResult.value = await callMcpTool(props.apiBase, toolId, toolName, args)
  } catch (error) { mcpCallError.value = error.message || '工具调用失败' }
  finally { mcpCallBusy.value = false }
}

async function loadWorkspaceCheckoutState(workspaceId) {
  try {
    workspaceCheckout.value = await getWorkspaceCheckout(props.apiBase, workspaceId)
    checkoutError.value = ''
  } catch (error) {
    workspaceCheckout.value = null
    checkoutError.value = error.message || '检出状态读取失败'
  }
}

async function runWorkspaceCheckout() {
  if (!editingWorkspace.value || checkoutBusy.value) return
  checkoutBusy.value = true
  checkoutError.value = ''
  try {
    const result = await checkoutWorkspace(props.apiBase, editingWorkspace.value.workspace_id)
    notify(`检出完成：${result.branch || ''} ${result.commit || ''}`.trim())
    await loadWorkspaceCheckoutState(editingWorkspace.value.workspace_id)
  } catch (error) { checkoutError.value = error.message || '仓库检出失败' }
  finally { checkoutBusy.value = false }
}

async function bindSelectedCatalogVersion() {
  if (!selectedCatalogName.value || !catalogVersion.value) { catalogBindError.value = '请先选择技能与版本'; return }
  catalogBindBusy.value = true
  catalogBindError.value = ''
  try {
    await bindCatalogSkill(props.apiBase, { name: selectedCatalogName.value, version: catalogVersion.value, percentage: Number(catalogBindPercentage.value) || 0 })
    notify(`已绑定 ${selectedCatalogName.value} ${catalogVersion.value}`)
    await refreshCatalogData()
  } catch (error) { catalogBindError.value = error.message || '绑定失败' }
  finally { catalogBindBusy.value = false }
}

async function unbindCurrentCatalogSkill() {
  if (!selectedCatalogName.value) return
  catalogBindBusy.value = true
  catalogBindError.value = ''
  try {
    await unbindCatalogSkill(props.apiBase, { name: selectedCatalogName.value })
    notify(`已解绑 ${selectedCatalogName.value}`)
    await refreshCatalogData()
  } catch (error) { catalogBindError.value = error.message || '解绑失败' }
  finally { catalogBindBusy.value = false }
}

async function loadTraceEvents() {
  const run = selectedTraceRun.value
  if (!run) { traceEvents.value = []; return }
  traceEventsBusy.value = true
  traceEventsError.value = ''
  try {
    const result = await getHarnessTrace(props.apiBase, run.run_id, { after: 0, ...traceFilters.value })
    traceEvents.value = result.items || []
  } catch (error) {
    traceEvents.value = []
    traceEventsError.value = error.message || '事件读取失败'
  } finally { traceEventsBusy.value = false }
}

async function loadTraceMetrics() {
  try {
    traceMetrics.value = await getHarnessObservabilityMetrics(props.apiBase)
  } catch (error) { traceMetrics.value = null }
}

async function loadTraceTrends() {
  if (trendsBusy.value) return
  trendsBusy.value = true
  try {
    const result = await getObservabilityTrends(props.apiBase, { bucket: traceTrendBucket.value, limit: 48 })
    traceTrends.value = result.points || []
    trendsError.value = ''
  } catch (error) {
    traceTrends.value = []
    trendsError.value = error.message || '趋势读取失败'
  } finally { trendsBusy.value = false }
}

async function exportObservabilityEvents(format) {
  exportBusy.value = true
  exportError.value = ''
  try {
    const result = await getObservabilityExports(props.apiBase, { from: exportFrom.value, to: exportTo.value, runId: exportRunId.value.trim(), format })
    const blob = format === 'csv' ? result.blob : new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = format === 'csv' ? 'harness-events.csv' : 'harness-events.json'
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    notify(`已导出 ${result.total} 条事件${result.truncated ? '（达到上限，已截断）' : ''}`)
  } catch (error) { exportError.value = error.message || '导出失败' }
  finally { exportBusy.value = false }
}

function refreshActiveSection() {
  if (activeSection.value === 'skills') return skillDirectoryTab.value === 'catalog' ? refreshCatalogData() : refreshSkillData()
  if (activeSection.value === 'models') return refreshModelData()
  if (activeSection.value === 'tools') return refreshToolData()
  if (activeSection.value === 'agents') return refreshAgentData()
  if (activeSection.value === 'evaluations') return refreshEvaluationData()
  if (activeSection.value === 'releases') return refreshReleaseData()
  if (activeSection.value === 'workspaces') return refreshWorkspaceData()
  if (activeSection.value === 'settings') return refreshHarnessSettings()
  return refreshExecutionRuns()
}

async function refreshSkillData() {
  try {
    harnessSkills.value = await getSkills(props.apiBase)
    skillsConnected.value = true
    skillsError.value = ''
  } catch (error) { skillsError.value = error.message || 'Skill 目录暂不可用' }
}

async function refreshCatalogData() {
  if (catalogLoading.value) return
  catalogLoading.value = true
  try {
    catalog.value = await getCatalogSkills(props.apiBase)
    catalogConnected.value = true
    catalogError.value = ''
  } catch (error) { catalogError.value = error.message || 'Catalog 读取失败' }
  finally { catalogLoading.value = false }
}

function selectSkillDirectory(tab) {
  skillDirectoryTab.value = tab
  if (tab === 'catalog') refreshCatalogData()
  else refreshSkillData()
}

async function loadCatalogVersion() {
  if (catalogDetailBusy.value) return
  catalogDetailBusy.value = true
  catalogDetail.value = null
  catalogComparison.value = null
  catalogDetailError.value = ''
  try {
    catalogDetail.value = await getCatalogVersion(props.apiBase, selectedCatalogName.value, catalogVersion.value)
  } catch (error) { catalogDetailError.value = error.message || '版本读取失败' }
  finally { catalogDetailBusy.value = false }
}

function openCatalogSkill(name) {
  selectedCatalogName.value = name
  const versions = catalog.value.skills.filter(item => item.name === name)
  catalogVersion.value = versions[0].version
  catalogBaseVersion.value = versions[1]?.version || versions[0].version
  loadCatalogVersion()
}

async function compareCatalogSkill() {
  if (catalogDetailBusy.value) return
  catalogDetailBusy.value = true
  catalogDetailError.value = ''
  catalogComparison.value = null
  try {
    catalogComparison.value = await compareCatalogVersions(props.apiBase, selectedCatalogName.value, catalogBaseVersion.value, catalogVersion.value)
  } catch (error) { catalogDetailError.value = error.message || '版本比较失败' }
  finally { catalogDetailBusy.value = false }
}

async function openSkillDetails(row) {
  if (row.id.startsWith('demo-')) return notify('请连接 Skill 目录后查看真实安装包')
  try {
    selectedSkill.value = await getSkillDetail(props.apiBase, row.id)
    skillChangeError.value = ''
  } catch (error) { notify(`读取 Skill 失败：${error.message}`) }
}

async function toggleInstalledSkill(skill) {
  if (skillChangingId.value) return
  skillChangeError.value = ''
  skillChangingId.value = skill.id
  try {
    const updated = await setSkillEnabled(props.apiBase, skill.id, !skill.enabled)
    harnessSkills.value = harnessSkills.value.map(item => item.id === updated.id ? updated : item)
    if (selectedSkill.value?.id === updated.id) selectedSkill.value = { ...selectedSkill.value, ...updated }
    notify(updated.enabled ? 'Skill 已启用' : 'Skill 已停用')
  } catch (error) { skillChangeError.value = error.message || 'Skill 启停失败，请重试' }
  finally { skillChangingId.value = '' }
}

async function refreshModelData() {
  try {
    const result = await getHarnessModels(props.apiBase)
    harnessModels.value = result.items
    modelsConnected.value = true
    modelsError.value = ''
  } catch (error) { modelsError.value = error.message || '模型路由目录暂不可用' }
}

async function testModelConnection(row) {
  if (modelTestBusy.value) return
  modelTestBusy.value = row.model_id
  try {
    const result = await testHarnessModel(props.apiBase, row.model_id)
    modelTestResults.value = { ...modelTestResults.value, [row.model_id]: result }
    notify(result.ok ? `${row.name}：连接正常` : `${row.name}：连接失败，${result.message || '后端未返回原因'}`)
  } catch (error) {
    modelTestResults.value = { ...modelTestResults.value, [row.model_id]: { ok: false, message: error.message || '连接测试失败' } }
    notify(`连接测试失败：${error.message}`)
  } finally {
    modelTestBusy.value = ''
  }
}

function openModelDialog() {
  editingModel.value = null
  modelDraft.value = { name: '', provider: '', route: 'default', status: 'configured', cost_policy: '', fallback_model_id: null }
  modelError.value = ''
  modelFallbackChain.value = []
  showModelDialog.value = true
}

async function loadModelFallbackChain(modelId) {
  if (!modelId) { modelFallbackChain.value = []; return }
  try {
    const result = await getModelFallbackChain(props.apiBase, modelId)
    modelFallbackChain.value = result.chain || []
  } catch (error) {
    modelFallbackChain.value = []
  }
}

async function openModelDetails(row) {
  if (row.model_id.startsWith('demo-')) return notify('请连接模型目录后查看真实记录')
  try {
    const { model } = await getHarnessModel(props.apiBase, row.model_id)
    editingModel.value = model
    modelDraft.value = { name: model.name, provider: model.provider, route: model.route, status: model.status, cost_policy: model.cost_policy, fallback_model_id: model.fallback_model_id }
    modelError.value = ''
    showModelDialog.value = true
    await loadModelFallbackChain(model.model_id)
  } catch (error) { notify(`读取模型路由失败：${error.message}`) }
}

async function saveModel() {
  if (modelSaving.value) return
  modelError.value = ''
  if (![modelDraft.value.name, modelDraft.value.route, modelDraft.value.status].every(value => value.trim())) {
    modelError.value = '请填写模型名称、路由用途和登记状态'
    return
  }
  modelSaving.value = true
  try {
    const payload = { ...modelDraft.value }
    const result = editingModel.value
      ? await updateHarnessModel(props.apiBase, editingModel.value.model_id, { ...payload, revision: editingModel.value.revision })
      : await createHarnessModel(props.apiBase, payload)
    harnessModels.value = [result.model, ...harnessModels.value.filter(item => item.model_id !== result.model.model_id)]
    modelsConnected.value = true
    modelsError.value = ''
    showModelDialog.value = false
    notify('模型路由登记信息已保存')
  } catch (error) { modelError.value = error.message || '保存失败，请重试' }
  finally { modelSaving.value = false }
}

async function refreshToolData() {
  try {
    const result = await getHarnessTools(props.apiBase)
    harnessTools.value = result.items
    toolsConnected.value = true
    toolsError.value = ''
  } catch (error) { toolsError.value = error.message || '工具目录暂不可用' }
  try {
    const result = await getHarnessMcpServers(props.apiBase)
    harnessMcpServers.value = result.items || []
    mcpServersError.value = ''
  } catch (error) {
    harnessMcpServers.value = []
    mcpServersError.value = error.message || 'MCP 连接器读取失败'
  }
}

async function testToolConnection(row) {
  if (toolTestBusy.value) return
  toolTestBusy.value = row.tool_id
  try {
    const result = await testHarnessTool(props.apiBase, row.tool_id)
    toolTestResults.value = { ...toolTestResults.value, [row.tool_id]: result }
    notify(result.ok ? `${row.name}：连接正常` : `${row.name}：连接失败，${result.message || '后端未返回原因'}`)
  } catch (error) {
    toolTestResults.value = { ...toolTestResults.value, [row.tool_id]: { ok: false, message: error.message || '连接测试失败' } }
    notify(`连接测试失败：${error.message}`)
  } finally {
    toolTestBusy.value = ''
  }
}

function openToolDialog() {
  editingTool.value = null
  toolDraft.value = { name: '', source: 'mcp', scope: 'workspace', risk: 'low', status: 'configured', description: '', approval_policy: 'risk-based' }
  toolSchemaText.value = JSON.stringify({ type: 'object', properties: {} }, null, 2)
  toolError.value = ''
  showToolDialog.value = true
}

async function openToolDetails(row) {
  if (row.tool_id.startsWith('demo-')) return notify('请连接工具目录后查看真实记录')
  try {
    const { tool } = await getHarnessTool(props.apiBase, row.tool_id)
    editingTool.value = tool
    toolDraft.value = { name: tool.name, source: tool.source, scope: tool.scope, risk: tool.risk, status: tool.status, description: tool.description, approval_policy: tool.approval_policy }
    toolSchemaText.value = JSON.stringify(tool.input_schema, null, 2)
    toolError.value = ''
    showToolDialog.value = true
  } catch (error) { notify(`读取工具失败：${error.message}`) }
}

async function saveTool() {
  if (toolSaving.value) return
  toolError.value = ''
  let schema
  try {
    schema = JSON.parse(toolSchemaText.value)
    if (!schema || Array.isArray(schema) || schema.type !== 'object') throw new Error()
  } catch {
    toolError.value = '参数 Schema 必须是根 type 为 object 的 JSON 对象'
    return
  }
  if (![toolDraft.value.name, toolDraft.value.source, toolDraft.value.scope, toolDraft.value.status].every(value => value.trim())) {
    toolError.value = '请填写名称、来源、范围和状态'
    return
  }
  toolSaving.value = true
  try {
    const payload = { ...toolDraft.value, input_schema: schema }
    const result = editingTool.value
      ? await updateHarnessTool(props.apiBase, editingTool.value.tool_id, { ...payload, revision: editingTool.value.revision })
      : await createHarnessTool(props.apiBase, payload)
    harnessTools.value = [result.tool, ...harnessTools.value.filter(item => item.tool_id !== result.tool.tool_id)]
    toolsConnected.value = true
    toolsError.value = ''
    showToolDialog.value = false
    notify('工具登记配置已保存')
  } catch (error) { toolError.value = error.message || '保存失败，请重试' }
  finally { toolSaving.value = false }
}

async function refreshAgentData() {
  try {
    const result = await getHarnessAgents(props.apiBase)
    harnessAgents.value = result.items
    agentsConnected.value = true
    agentsError.value = ''
  } catch (error) {
    agentsError.value = error.message || 'Agent 服务暂不可用'
  }
}

async function refreshWorkspaceData() {
  try {
    const result = await getHarnessWorkspaces(props.apiBase)
    harnessWorkspaces.value = result.items
    workspacesConnected.value = true
    workspacesError.value = ''
  } catch (error) {
    workspacesError.value = error.message || '工作空间服务暂不可用'
  }
}

async function refreshResourceData({ silent = false } = {}) {
  try {
    const [machines, approvals, traceRuns] = await Promise.all([getHarnessMachines(props.apiBase), getHarnessApprovals(props.apiBase, 'pending'), getHarnessObservabilityRuns(props.apiBase)])
    harnessMachines.value = machines?.items || []
    harnessApprovals.value = approvals?.items || []
    harnessTraceRuns.value = traceRuns?.items || []
    resourceConnected.value = true
    resourceError.value = ''
  } catch (error) {
    resourceConnected.value = false
    resourceError.value = error.message || '资源目录服务暂不可用'
    if (!silent) notify(`资源目录刷新失败：${resourceError.value}`)
  }
  loadApprovalNotifications()
}

async function refreshHarnessSettings({ silent = false } = {}) {
  try {
    const result = await getHarnessSettings(props.apiBase)
    harnessSettings.value = result?.settings || harnessSettings.value
    settingsConnected.value = true
    settingsError.value = ''
  } catch (error) {
    settingsConnected.value = false
    settingsError.value = error.message || '设置服务暂不可用'
    if (!silent) notify(`设置读取失败：${settingsError.value}`)
  }
}

async function saveSettings() {
  try {
    const result = await saveHarnessSettings(props.apiBase, harnessSettings.value)
    harnessSettings.value = result.settings
    settingsConnected.value = true
    notify('Harness 设置已保存')
  } catch (error) { notify(`设置保存失败：${error.message || '设置服务不可用'}`) }
}

function openAgentDialog() {
  editingAgent.value = null
  agentPolicyText.value = '{}'
  agentError.value = ''
  agentDraft.value = { name: '', description: '', version: 'v1', model: 'auto' }
  showAgentDialog.value = true
}

async function openAgentDetails(row) {
  if (row.agent_id.startsWith('demo-')) return notify('演示 Agent 仅供查看，请连接资源服务后编辑真实配置')
  try {
    const result = await getHarnessAgent(props.apiBase, row.agent_id)
    const agent = result.agent
    const rawPolicy = typeof agent.policy === 'string' ? (agent.policy || '{}') : agent.policy
    let policy = {}
    try { policy = rawPolicy ? JSON.parse(rawPolicy) : {} } catch { policy = {} }
    if (!policy || Array.isArray(policy) || typeof policy !== 'object') policy = {}
    editingAgent.value = agent
    agentDraft.value = { name: agent.name, description: agent.description, version: agent.version, model: agent.model }
    agentPolicyText.value = JSON.stringify(policy, null, 2)
    agentError.value = ''
    agentSkillError.value = ''
    agentSkillInput.value = ''
    agentSkillPick.value = ''
    showAgentDialog.value = true
    await Promise.all([loadAgentVersions(agent.agent_id), loadAgentRuns(agent.agent_id)])
  } catch (error) { notify(`读取 Agent 失败：${error.message}`) }
}

async function toggleAgentStatus(row) {
  if (agentStatusBusy.value) return
  agentStatusBusy.value = row.agent_id
  try {
    const result = await setHarnessAgentStatus(props.apiBase, row.agent_id, !row.enabled)
    harnessAgents.value = harnessAgents.value.map(item => item.agent_id === result.agent.agent_id ? result.agent : item)
    if (editingAgent.value?.agent_id === result.agent.agent_id) editingAgent.value = result.agent
    notify(result.agent.enabled ? 'Agent 已启用' : 'Agent 已停用')
  } catch (error) {
    notify(`Agent 启停失败：${error.message || '资源服务不可用'}`)
  } finally {
    agentStatusBusy.value = ''
  }
}

async function loadAgentVersions(agentId) {
  agentVersionsBusy.value = true
  try {
    const result = await getHarnessAgentVersions(props.apiBase, agentId)
    agentVersions.value = result.items || []
    agentDiffTarget.value = agentVersions.value[0]?.version_id || ''
    agentDiffBase.value = agentVersions.value[1]?.version_id || agentVersions.value[0]?.version_id || ''
    agentDiff.value = null
    agentDiffError.value = ''
  } catch (error) {
    agentVersions.value = []
    agentDiffError.value = error.message || '版本历史读取失败'
  } finally {
    agentVersionsBusy.value = false
  }
}

function formatDiffValue(value) {
  if (value == null) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

async function compareAgentVersions() {
  if (!agentDiffBase.value || !agentDiffTarget.value) { agentDiffError.value = '请选择两个版本快照'; return }
  agentDiffBusy.value = true
  try {
    agentDiff.value = await getHarnessAgentDiff(props.apiBase, editingAgent.value.agent_id, agentDiffBase.value, agentDiffTarget.value)
    agentDiffError.value = ''
  } catch (error) {
    agentDiff.value = null
    agentDiffError.value = error.message || '版本比较失败'
  } finally {
    agentDiffBusy.value = false
  }
}

async function loadAgentRuns(agentId) {
  agentRunsBusy.value = true
  try {
    const result = await getHarnessAgentRuns(props.apiBase, agentId)
    agentRuns.value = result.items || []
    agentRunsError.value = ''
  } catch (error) {
    agentRuns.value = []
    agentRunsError.value = error.message || '关联运行读取失败'
  } finally {
    agentRunsBusy.value = false
  }
}
const pendingAgentSkillId = computed(() => agentSkillInput.value.trim() || agentSkillPick.value)
async function bindAgentSkill() {
  const skillId = pendingAgentSkillId.value
  if (!skillId) { agentSkillError.value = '请选择或输入要绑定的 skillId'; return }
  const current = [...(editingAgent.value?.skills || [])]
  if (current.includes(skillId)) { agentSkillError.value = '该 Skill 已绑定'; return }
  agentSkillBusy.value = true
  try {
    const result = await bindHarnessAgentSkills(props.apiBase, editingAgent.value.agent_id, [...current, skillId])
    editingAgent.value = result.agent
    harnessAgents.value = harnessAgents.value.map(item => item.agent_id === result.agent.agent_id ? result.agent : item)
    agentSkillInput.value = ''
    agentSkillPick.value = ''
    agentSkillError.value = ''
    notify(`已绑定 Skill ${skillId}`)
  } catch (error) {
    agentSkillError.value = error.message || 'Skill 绑定失败'
  } finally {
    agentSkillBusy.value = false
  }
}

async function unbindAgentSkill(skillId) {
  agentSkillBusy.value = true
  try {
    const result = await unbindHarnessAgentSkill(props.apiBase, editingAgent.value.agent_id, skillId)
    editingAgent.value = result.agent
    harnessAgents.value = harnessAgents.value.map(item => item.agent_id === result.agent.agent_id ? result.agent : item)
    agentSkillError.value = ''
    notify(`已解绑 Skill ${skillId}`)
  } catch (error) {
    agentSkillError.value = error.message || 'Skill 解绑失败'
  } finally {
    agentSkillBusy.value = false
  }
}

async function submitAgent() {
  if (agentSaving.value) return
  agentError.value = ''
  let policy
  try {
    policy = JSON.parse(agentPolicyText.value)
    if (!policy || Array.isArray(policy) || typeof policy !== 'object') throw new Error()
  } catch {
    agentError.value = '运行策略必须是 JSON 对象'
    return
  }
  if (![agentDraft.value.name, agentDraft.value.version, agentDraft.value.model].every(value => value.trim())) {
    agentError.value = '请填写名称、版本和模型路由'
    return
  }
  agentSaving.value = true
  try {
    const payload = { ...agentDraft.value, policy }
    const result = editingAgent.value
      ? await updateHarnessAgent(props.apiBase, editingAgent.value.agent_id, { ...payload, revision: editingAgent.value.revision })
      : await createHarnessAgent(props.apiBase, payload)
    harnessAgents.value = [result.agent, ...harnessAgents.value.filter(item => item.agent_id !== result.agent.agent_id)]
    agentsConnected.value = true
    agentsError.value = ''
    showAgentDialog.value = false
    notify(editingAgent.value ? 'Agent 配置已保存' : 'Agent 已创建')
  } catch (error) {
    agentError.value = error.message || '保存失败，请重试'
  } finally { agentSaving.value = false }
}

function openWorkspaceDialog() {
  editingWorkspace.value = null
  workspaceError.value = ''
  workspaceDraft.value = { name: '', repository: '', branch: 'main' }
  showWorkspaceDialog.value = true
}

async function openWorkspaceDetails(row) {
  if (row.workspace_id.startsWith('demo-')) return notify('演示工作空间仅供查看，请连接资源服务后编辑真实记录')
  try {
    const result = await getHarnessWorkspace(props.apiBase, row.workspace_id)
    const workspace = result.workspace
    editingWorkspace.value = workspace
    workspaceDraft.value = { name: workspace.name, repository: workspace.repository, branch: workspace.branch }
    workspaceError.value = ''
    workspaceSnapshotError.value = ''
    workspaceChangesError.value = ''
    workspaceRunsError.value = ''
    showWorkspaceDialog.value = true
    await Promise.all([loadWorkspaceSnapshots(workspace.workspace_id), loadWorkspaceRuns(workspace.workspace_id), loadWorkspaceCheckoutState(workspace.workspace_id)])
  } catch (error) { notify(`读取工作空间失败：${error.message}`) }
}

async function loadWorkspaceSnapshots(workspaceId) {
  try {
    const result = await getHarnessWorkspaceSnapshots(props.apiBase, workspaceId)
    workspaceSnapshots.value = result.items || []
    workspaceSnapshotError.value = ''
    workspaceSelectedSnapshotId.value = workspaceSnapshots.value[0]?.snapshot_id || ''
    await loadWorkspaceChanges(workspaceId, workspaceSelectedSnapshotId.value)
  } catch (error) {
    workspaceSnapshots.value = []
    workspaceSnapshotError.value = error.message || '快照读取失败'
  }
}

async function loadWorkspaceChanges(workspaceId, snapshotId) {
  if (!snapshotId) { workspaceChanges.value = []; return }
  try {
    const result = await getHarnessWorkspaceChanges(props.apiBase, workspaceId, snapshotId)
    workspaceChanges.value = result.items || []
    workspaceChangesError.value = ''
  } catch (error) {
    workspaceChanges.value = []
    workspaceChangesError.value = error.message || '文件变更读取失败'
  }
}

async function createWorkspaceSnapshot() {
  if (workspaceSnapshotBusy.value) return
  workspaceSnapshotBusy.value = true
  workspaceSnapshotError.value = ''
  try {
    const result = await createHarnessWorkspaceSnapshot(props.apiBase, editingWorkspace.value.workspace_id)
    await loadWorkspaceSnapshots(editingWorkspace.value.workspace_id)
    notify(`快照已创建：${result.snapshot.snapshot_id}`)
  } catch (error) {
    workspaceSnapshotError.value = error.message || '快照创建失败'
    notify(`创建快照失败：${workspaceSnapshotError.value}`)
  } finally {
    workspaceSnapshotBusy.value = false
  }
}

async function loadWorkspaceRuns(workspaceId) {
  try {
    const result = await getHarnessWorkspaceRuns(props.apiBase, workspaceId)
    workspaceRuns.value = result.items || []
    workspaceRunsError.value = ''
  } catch (error) {
    workspaceRuns.value = []
    workspaceRunsError.value = error.message || '关联运行读取失败'
  }
}

async function submitWorkspace() {
  if (workspaceSaving.value) return
  workspaceError.value = ''
  if (![workspaceDraft.value.name, workspaceDraft.value.branch].every(value => value.trim())) {
    workspaceError.value = '请填写工作空间名称和分支'
    return
  }
  workspaceSaving.value = true
  try {
    const payload = { ...workspaceDraft.value }
    const result = editingWorkspace.value
      ? await updateHarnessWorkspace(props.apiBase, editingWorkspace.value.workspace_id, { ...payload, revision: editingWorkspace.value.revision })
      : await createHarnessWorkspace(props.apiBase, payload)
    harnessWorkspaces.value = [result.workspace, ...harnessWorkspaces.value.filter(item => item.workspace_id !== result.workspace.workspace_id)]
    workspacesConnected.value = true
    workspacesError.value = ''
    showWorkspaceDialog.value = false
    notify(editingWorkspace.value ? '工作空间登记信息已保存' : '工作空间已创建')
  } catch (error) {
    workspaceError.value = error.message || '保存失败，请重试'
  } finally { workspaceSaving.value = false }
}

async function loadMachineErrors(workerId) {
  machineErrorsBusy.value = true
  machineErrorsError.value = ''
  try {
    const result = await getMachineErrors(props.apiBase, workerId)
    machineErrors.value = result.items || []
    machineErrorWorker.value = workerId
  } catch (error) {
    machineErrors.value = []
    machineErrorsError.value = error.message || '节点错误日志读取失败'
  } finally { machineErrorsBusy.value = false }
}

async function decideApproval(row, decision, reason = '') {
  if (approvalBusy.value) return
  approvalBusy.value = true
  try {
    await decideHarnessApproval(props.apiBase, row.request_id, {
      decision,
      reason: reason || (decision === 'approved' ? 'Harness 操作者批准' : 'Harness 操作者拒绝'),
      operator: 'harness-operator',
    })
    await refreshResourceData({ silent: true })
    approvalSelection.value = approvalSelection.value.filter(id => id !== row.request_id)
    notify(decision === 'approved' ? '审批已通过' : '审批已拒绝')
  } catch (error) { notify(`审批处理失败：${error.message || '审批服务不可用'}`) }
  finally { approvalBusy.value = false }
}

async function decideApprovalBatch(decision) {
  if (approvalBusy.value || !approvalSelection.value.length) return
  approvalBusy.value = true
  try {
    const result = await decideHarnessApprovalsBatch(props.apiBase, {
      requestIds: approvalSelection.value,
      decision,
      reason: decision === 'approved' ? 'Harness 批量批准' : 'Harness 批量拒绝',
      operator: 'harness-operator',
    })
    await refreshResourceData({ silent: true })
    approvalSelection.value = []
    notify(`已处理 ${result?.items?.length ?? 0} 条审批${result?.failed?.length ? `，${result.failed.length} 条失败` : ''}`)
  } catch (error) { notify(`批量审批失败：${error.message || '审批服务不可用'}`) }
  finally { approvalBusy.value = false }
}

async function openApprovalDetail(row) {
  approvalDetailBusy.value = true
  try {
    const result = await getHarnessApproval(props.apiBase, row.request_id)
    approvalDetail.value = result.approval || null
  } catch (error) { notify(`审批详情读取失败：${error.message || '审批服务不可用'}`) }
  finally { approvalDetailBusy.value = false }
}

function openRejectDialog(row) {
  rejectDialog.value = row
  rejectReason.value = ''
}

async function submitRejectApproval() {
  if (!rejectDialog.value) return
  const reason = rejectReason.value.trim()
  if (!reason) { notify('请填写拒绝理由'); return }
  const row = rejectDialog.value
  rejectDialog.value = null
  await decideApproval(row, 'rejected', reason)
}

async function toggleMachineDrain(row) {
  if (machineBusy.value) return
  machineBusy.value = row.worker_id
  try {
    await drainHarnessMachine(props.apiBase, row.worker_id, row.state !== 'draining')
    await refreshResourceData({ silent: true })
    notify(row.state === 'draining' ? `${row.worker_id} 已恢复接单` : `${row.worker_id} 已进入排空状态`)
  } catch (error) { notify(`节点状态更新失败：${error.message || '治理服务不可用'}`) }
  finally { machineBusy.value = '' }
}

async function removeEvaluationDataset(dataset) {
  if (datasetBusy.value) return
  datasetBusy.value = dataset.datasetId
  try {
    await deleteEvaluationDataset(props.apiBase, dataset.datasetId)
    if (selectedEvaluationDataset.value?.datasetId === dataset.datasetId) selectedEvaluationDataset.value = null
    notify(`测评集已删除：${dataset.name}`)
    await refreshEvaluationData({ silent: true })
  } catch (error) { notify(`删除失败：${error.message || '测评服务不可用'}`) }
  finally { datasetBusy.value = '' }
}

async function loadRunDetail(runId) {
  if (!runId) { runDetail.value = null; return }
  try {
    const result = await getExecutionRun(props.apiBase, runId)
    runDetail.value = result?.run || result || null
  } catch (error) { runDetail.value = null }
}

function formatTokenCount(value) {
  const num = Number(value) || 0
  if (num >= 1000000) return `${(num / 1000000).toFixed(2)}M`
  if (num >= 1000) return `${(num / 1000).toFixed(1)}K`
  return String(num)
}

async function loadOverviewStats() {
  try {
    overviewStats.value = await getHarnessOverview(props.apiBase)
  } catch (error) {
    overviewStats.value = null
  }
}

function selectRun(runId) {
  selectedRunId.value = runId
  loadRunDetail(runId)
}

function selectEvaluationTab(tab) {
  evaluationTab.value = tab
}

// Harness 弹窗统一按 DOM 定位，只在 .harness-shell 内查找，不影响 App 自身弹窗
const harnessRoot = ref(null)
const harnessDialogCount = computed(() => [
  selectedCatalogName.value, selectedSkill.value, showModelDialog.value, showToolDialog.value,
  showAgentDialog.value, showWorkspaceDialog.value, selectedEvaluationDataset.value, showCaseDialog.value,
  showImportDialog.value, showDatasetDialog.value, showRunDialog.value, evalRunDetail.value,
  approvalDetail.value, rejectDialog.value,
].filter(Boolean).length)
let harnessDialogReturnFocus
function harnessDialogBackdrops() {
  return Array.from(harnessRoot.value?.querySelectorAll('.modal-backdrop') || [])
}
function harnessTopDialog() {
  const backdrops = harnessDialogBackdrops()
  return backdrops[backdrops.length - 1]?.querySelector('[role="dialog"], [role="alertdialog"]') || null
}
function harnessDialogControls(dialog) {
  return Array.from(dialog?.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex="0"]') || []).filter(element => element.getClientRects().length)
}
function harnessKeydown(event) {
  const dialog = harnessTopDialog()
  if (!dialog) return
  if (event.key === 'Escape') {
    event.preventDefault()
    // 点遮罩复用各弹窗自己的关闭逻辑，保存进行中不会被误关
    harnessDialogBackdrops().pop()?.click()
  } else if (event.key === 'Tab') {
    const controls = harnessDialogControls(dialog)
    const first = controls[0]
    const last = controls[controls.length - 1]
    if (!first) event.preventDefault()
    else if (!controls.includes(document.activeElement) || (event.shiftKey && document.activeElement === first) || (!event.shiftKey && document.activeElement === last)) {
      event.preventDefault()
      const nextControl = event.shiftKey ? last : first
      nextControl.focus()
    }
  }
}
watch(harnessDialogCount, async (count, previousCount) => {
  if (count > 0) {
    if (previousCount === 0) harnessDialogReturnFocus = document.activeElement
    await nextTick()
    // 模板里的 autofocus 优先，保留各弹窗原本的落点意图
    const controls = harnessDialogControls(harnessTopDialog())
    ;(controls.find(element => element.hasAttribute('autofocus')) || controls[0])?.focus()
  } else if (previousCount > 0) {
    if (harnessDialogReturnFocus?.isConnected) harnessDialogReturnFocus.focus()
    harnessDialogReturnFocus = null
  }
})

onMounted(() => {
  refreshSkillData()
  refreshModelData()
  refreshToolData()
  refreshAgentData()
  refreshWorkspaceData()
  refreshExecutionRuns({ silent: true })
  refreshEvaluationData({ silent: true })
  refreshReleaseData({ silent: true })
  refreshResourceData({ silent: true })
  refreshHarnessSettings({ silent: true })
  loadOverviewStats()
  loadTraceTrends()
  loadTraceMetrics()
  executionRefreshTimer = window.setInterval(() => {
    if (['overview', 'runs'].includes(activeSection.value) && !executionLoading.value && !runSubmitBusy.value && !runActionBusy.value) refreshExecutionRuns({ silent: true })
  }, 5000)
  window.addEventListener('keydown', harnessKeydown)
})
onUnmounted(() => {
  runListGeneration += 1
  window.clearInterval(executionRefreshTimer)
  window.clearTimeout(notify.timer)
  window.removeEventListener('keydown', harnessKeydown)
})
</script>

<template>
  <div ref="harnessRoot" class="harness-shell" :class="{ 'is-embedded': props.embedded }">
    <div v-if="mobileNavOpen" class="mobile-scrim" @click="mobileNavOpen = false"></div>
    <aside class="harness-sidebar" :class="{ 'is-open': mobileNavOpen }">
      <div class="brand-lockup"><div class="brand-symbol"><Workflow :size="18" :stroke-width="2" /></div><div class="brand-copy"><strong>HOTLINE</strong></div><button class="close-mobile" aria-label="关闭导航" @click="mobileNavOpen = false"><X :size="17" /></button></div>
      <nav class="side-navigation" aria-label="Harness 导航"><div v-for="group in sections" :key="group.label" class="nav-group"><div class="nav-group-label">{{ group.label }}</div><button v-for="item in group.items" :key="item.id" class="nav-link" :class="{ active: activeSection === item.id }" @click="selectSection(item.id)"><component :is="item.icon" :size="16" :stroke-width="1.8" /><span>{{ item.label }}</span><small v-if="sectionCounts[item.id]">{{ sectionCounts[item.id] }}</small></button></div></nav>
    </aside>

    <main class="main-surface">
      <header v-if="!props.embedded" class="topbar"><button class="mobile-menu" aria-label="打开导航" @click="mobileNavOpen = true"><Menu :size="19" /></button><div class="breadcrumbs"><span>Harness</span><span class="crumb-slash">/</span><strong>{{ navTitle }}</strong></div><div class="topbar-actions"><span class="demo-label" :class="{ planned: sectionMode !== 'live' }"><span></span>{{ sourceLabel }}</span><button class="top-icon" aria-label="搜索" title="搜索" @click="$refs.searchField?.focus()"><Search :size="16" /></button><button class="command-shortcut" @click="$refs.searchField?.focus()"><Command :size="13" />快速查找<kbd>Ctrl K</kbd></button><button class="avatar-small" aria-label="个人账户">SC</button></div></header>
      <div class="page-scroll"><div class="page-content">
      <div class="page-heading-row"><div><h1>{{ pageHeading }}</h1></div><div class="heading-actions"><button v-if="props.embedded" class="mobile-menu embedded-mobile-menu" type="button" title="打开 Harness 菜单" aria-label="打开 Harness 菜单" :aria-expanded="mobileNavOpen" @click="mobileNavOpen = true"><Menu :size="18" /></button><span v-if="props.embedded" class="embedded-source-label">{{ sourceLabel }}</span><button v-if="canRefreshStatus" class="button button-subtle refresh-button" title="刷新状态" aria-label="刷新状态" @click="refreshActiveSection"><Activity :size="15" /><span>{{ executionLoading ? '刷新中…' : '刷新状态' }}</span></button><button v-if="canCreateRun" class="button button-primary" @click="openCreateRun"><Plus :size="16" />新建运行</button></div></div>
      <div v-if="executionError && ['overview', 'runs'].includes(activeSection)" class="execution-error-banner"><ShieldCheck :size="16" /><span>{{ executionError }}。{{ executionLoaded ? '保留上次读取的记录。' : '尚未读取到运行记录。' }}</span><button class="text-action" @click="refreshExecutionRuns">重试</button></div>
      <div v-if="evaluationError && activeSection === 'evaluations'" class="execution-error-banner"><ShieldCheck :size="16" /><span>{{ evaluationError }}，当前保留测评演示数据。</span><button class="text-action" @click="refreshEvaluationData">重试</button></div>
      <div v-if="releaseError && activeSection === 'releases'" class="execution-error-banner"><ShieldCheck :size="16" /><span>{{ releaseError }}，当前保留发布演示数据。</span><button class="text-action" @click="refreshReleaseData">重试</button></div>

      <div v-if="settingsError && activeSection === 'settings'" class="execution-error-banner"><ShieldCheck :size="16" /><span>{{ settingsError }}，当前保留默认设置。</span><button class="text-action" @click="refreshHarnessSettings">重试</button></div>

        <div v-if="sectionMode === 'planned'" class="planned-notice"><div class="planned-mark"><ShieldCheck :size="18" /></div><div><strong>{{ navTitle }}尚未接入运行控制 API</strong><span>当前展示规划范围和待接入状态。接入后此处会显示来自后端的实时资源、版本与审计数据。</span></div><span class="planned-badge">目标模块 · {{ activeSection }}</span></div>
        <template v-if="activeSection === 'overview' || activeSection === 'runs'">
          <p v-if="activeSection === 'overview'">下列汇总指标与节点表为演示数据，实际运行请进入执行任务。</p>
          <section v-if="activeSection === 'overview'" class="overview-strip" aria-label="今日运行指标"><div class="overview-stat"><span>活动运行</span><strong>{{ overviewStats ? overviewStats.activeRuns : '—' }}</strong><small><i class="status-inline"></i>排队与执行中</small></div><div class="overview-stat"><span>今日完成</span><strong>{{ overviewStats ? overviewStats.completedToday : '—' }}</strong><small class="positive"><Check :size="12" />失败 {{ overviewStats?.failedToday ?? '—' }} · 取消 {{ overviewStats?.cancelledToday ?? '—' }}</small></div><div class="overview-stat"><span>待人工审批</span><strong class="stat-warn">{{ overviewStats ? overviewStats.pendingApprovals : '—' }}</strong><small>来自真实审批队列</small></div><div class="overview-stat"><span>今日模型用量</span><strong>{{ overviewStats ? formatTokenCount(overviewStats.tokensToday) : '—' }}</strong><small>Tokens · 工具调用 {{ overviewStats?.toolCallsToday ?? '—' }}</small></div><div class="overview-stat stat-runtime"><span>运行时节点</span><strong>{{ onlineWorkerCount }} <em>/ {{ machineRows.length }}</em></strong><small>在线节点</small></div></section>

          <section v-if="activeSection === 'runs'" class="run-workbench execution-live">
            <div class="run-list-panel">
              <div class="panel-heading"><div><h2>执行任务</h2><span>共 {{ executionTotal }} 条匹配记录 · 每页 {{ runPageSize }} 条</span></div></div>
              <div class="run-list-tools"><select v-model="filter" aria-label="任务状态"><option v-for="option in ['全部任务', ...Object.keys(statusFilters)]" :key="option">{{ option }}</option></select><label class="run-search"><Search :size="14" /><input ref="searchField" v-model="search" placeholder="搜索任务" /></label></div>
              <div class="run-list" :aria-busy="executionLoading"><button v-for="run in runs" :key="run.id" class="run-row" :class="{ selected: selectedRun?.id === run.id }" @click="selectRun(run.id)"><strong>{{ run.title }}</strong><div class="run-row-meta">{{ run.id }}</div><div class="run-row-bottom"><span>{{ run.agent }}</span><span>{{ statusLabels[run.status] || run.status }}</span></div></button>
                <div v-if="!runs.length" class="empty-runs"><span>{{ executionLoading ? '正在读取任务…' : executionLoaded ? '没有匹配的运行记录' : '等待运行服务连接' }}</span><button v-if="search || filter !== '全部任务'" @click="search = ''; filter = '全部任务'">清除筛选</button></div>
              </div>
              <nav class="execution-pagination" aria-label="执行任务分页"><button class="button button-subtle" :disabled="executionLoading || runOffset === 0" @click="changeRunPage(runOffset - runPageSize)">上一页</button><span aria-live="polite">{{ Math.floor(runOffset / runPageSize) + 1 }} / {{ Math.max(1, Math.ceil(executionTotal / runPageSize)) }}</span><button class="button button-subtle" :disabled="executionLoading || runOffset + runPageSize >= executionTotal" @click="changeRunPage(runOffset + runPageSize)">下一页</button></nav>
            </div>
            <ExecutionRunDetails v-if="selectedRun" :key="selectedRun.id" :run="selectedRun" :api-base="props.apiBase" :items="runEvents" :loading="eventsLoading" :error="eventsError" :output="runOutput" :stream-state="eventsStreamState" :action-busy="runActionBusy" @refresh="refreshSelectedRunEvents" @cancel="stopSelectedRun" @retry="retrySelectedRun" @duplicate="duplicateSelectedRun" />
            <div v-else class="empty-runs">选择运行后查看输入、输出和 Trace</div>
          </section>

          <section v-if="activeSection === 'overview'" class="machine-section"><div class="section-title-row"><div><h2>执行节点</h2><span>本地与远端 Agent Runtime 的容量和健康状态</span></div><button class="text-action" @click="selectSection('machines')">管理机器 <ArrowRight :size="13" /></button></div><div v-if="machineRows.length" class="machine-table"><div class="machine-header"><span>节点</span><span>进程</span><span>状态</span><span>容量</span><span>最近心跳</span><span>当前运行</span></div><div v-for="row in machineRows" :key="row.worker_id" class="machine-row"><strong><i class="machine-led" :class="{ offline: row.state === 'offline' }"></i>{{ row.worker_id }}</strong><span>{{ row.process_id }}</span><span><i class="health-mini" :class="{ offline: row.state === 'offline' }"></i>{{ row.state === 'draining' ? '排空中' : row.state === 'offline' ? '离线' : '在线' }}</span><span>{{ row.capacity ?? 1 }}</span><span>{{ formatWorkerSeen(row.last_seen) }}</span><span>{{ row.current_run_id || '空闲' }}</span></div></div><div v-else class="release-empty"><span>{{ machinesConnected ? '当前没有注册节点' : '未连接运行时节点 API' }}</span></div></section>
          <footer class="page-footer"><span>{{ activeSection === 'runs' ? '运行记录来自执行服务 · 每 5 秒刷新' : '总览指标来自今日真实运行记录' }}</span></footer>
        </template>
          <section v-else-if="activeSection === 'evaluations'" class="evaluation-page">
          <div class="evaluation-toolbar"><div class="evaluation-tabs"><button :class="{ active: evaluationTab === 'overview' }" @click="selectEvaluationTab('overview')">测评总览</button><button :class="{ active: evaluationTab === 'datasets' }" @click="selectEvaluationTab('datasets')">测评集</button><button :class="{ active: evaluationTab === 'config' }" @click="selectEvaluationTab('config')">评测配置</button><button :class="{ active: evaluationTab === 'reports' }" @click="selectEvaluationTab('reports')">历史报告</button></div><button class="button button-primary" :disabled="evalRunBusy" @click="runEvaluation"><Play :size="14" />{{ evalRunBusy ? '测评进行中…' : '运行测评' }}</button><span v-if="evalProgress" class="evaluation-progress">{{ evalProgress }}</span></div>
          <template v-if="evaluationTab === 'overview'">

          <section class="evaluation-kpis"><div><span>活跃测评集</span><strong>{{ evaluationConnected ? evalDatasets.length : '—' }}</strong><small>{{ evaluationConnected ? evalCaseTotal + ' 条测试样本' : '未连接测评服务' }}</small></div><div><span>最近通过率</span><strong>{{ evalPassRateText }}</strong><small v-if="latestEvalRun">{{ latestEvalRun.eval_run_id }}</small><small v-else>本次测评未产出可比结果</small></div><div><span>失败样本</span><strong class="stat-warn">{{ latestEvalSummary?.failedCount ?? '—' }}</strong></div><div><span>通过样本</span><strong>{{ latestEvalSummary?.passedCount ?? '—' }}</strong><small>最近一次运行共 {{ latestEvalSummary?.caseCount ?? '—' }} 个样本</small></div></section>
          <div class="evaluation-grid"><section class="harness-panel evaluation-dimensions"><div class="harness-panel-heading"><div><h3>能力维度</h3><p>{{ latestEvalRun ? '以最近一次测评 ' + latestEvalRun.eval_run_id + ' 为准' : '暂无真实测评结果' }}</p></div><button class="text-action" @click="selectEvaluationTab('config')">配置维度 <ArrowRight :size="13" /></button></div><div class="dimension-list"><div v-for="dimension in dimensionRows" :key="dimension.label" class="dimension-row"><div class="dimension-icon" :class="dimension.color"><Gauge :size="15" /></div><div class="dimension-copy"><strong>{{ dimension.label }}</strong><small>{{ dimension.note }}</small></div><div class="dimension-track"><i :class="dimension.color" style="width:0%"></i></div><strong class="dimension-score">{{ dimension.score }}</strong></div><div v-if="!dimensionRows.length" class="release-empty"><span>暂无评测维度配置</span></div></div></section><aside class="harness-panel evaluation-health"><div class="harness-panel-heading"><div><h3>质量门禁</h3></div><span v-if="latestGate" class="dataset-state" :class="{ attention: !latestGate.passed }"><i></i>{{ latestGate.passed ? '通过' : '未通过' }}</span></div><template v-if="latestGate"><div v-for="row in gateCheckRows" :key="row.label" class="gate-row" :class="{ failed: row.passed !== true }"><span>{{ row.label }} · 阈值 {{ row.value }}</span><strong>{{ row.passed === true ? '通过' : row.passed === false ? '未通过' : '未评估' }}</strong><Check v-if="row.passed === true" :size="14" /><X v-else :size="14" /></div><div class="gate-note"><ShieldCheck :size="14" />{{ latestGate.eval_run_id ? '关联测评运行 ' + latestGate.eval_run_id : '未关联测评运行' }} · {{ latestGate.name || '未命名版本' }} {{ latestGate.version || '' }} · 门禁编号 {{ latestGate.gate_id }}</div></template><div v-else class="release-empty"><span>暂无门禁记录</span><small>未连接发布服务</small></div></aside></div>
          <section class="harness-panel evaluation-datasets"><div class="harness-panel-heading"><div><h3>测评集</h3></div><button class="button button-subtle" @click="openDatasetDialog"><Plus :size="14" />新建测评集</button></div><div class="dataset-table"><div class="dataset-head"><span>名称</span><span>类型</span><span>样本数</span><span>通过率</span><span>最近运行</span><span>状态</span></div><button v-for="dataset in evalDatasets" :key="dataset.name" class="dataset-row" @click="selectEvaluationDataset(dataset)"><strong>{{ dataset.name }}</strong><span class="dataset-type">{{ dataset.type }}</span><span>{{ dataset.cases }}</span><span class="dataset-pass">{{ dataset.pass }} <small>{{ dataset.delta }}</small></span><span>{{ dataset.updated }}</span><span class="dataset-state" :class="{ running: dataset.state === '运行中', attention: dataset.state === '需关注' }"><i></i>{{ dataset.state }}</span><ArrowRight :size="14" /></button></div></section>
          </template>
          <section v-else-if="evaluationTab === 'datasets'" class="harness-panel evaluation-subpage"><div class="harness-panel-heading"><div><h3>测评集管理</h3></div><button class="button button-primary" @click="openDatasetDialog"><Plus :size="14" />新建测评集</button></div><div class="evaluation-dataset-cards"><div v-for="dataset in evalDatasets" :key="dataset.name" class="evaluation-dataset-card-wrap"><button class="evaluation-dataset-card" @click="selectEvaluationDataset(dataset)"><div><strong>{{ dataset.name }}</strong><span>{{ dataset.type }} · {{ dataset.cases }} 条样本</span></div><b>{{ dataset.pass }}</b><ArrowRight :size="14" /></button><button class="text-action danger" type="button" :disabled="datasetBusy === dataset.datasetId" @click="removeEvaluationDataset(dataset)">{{ datasetBusy === dataset.datasetId ? '删除中…' : '删除' }}</button></div></div></section>
          <section v-else-if="evaluationTab === 'config'" class="harness-panel evaluation-subpage"><div class="harness-panel-heading"><div><h3>评测配置</h3></div><button class="button button-primary" @click="saveEvalConfig"><Check :size="14" />保存配置</button></div><div class="evaluation-config-list"><label v-for="dimension in dimensionRows" :key="dimension.label"><input type="checkbox" :checked="isDimensionEnabled(dimension.label)" @change="toggleDimension(dimension.label, $event.target.checked)" /> <span><strong>{{ dimension.label }}</strong><small>{{ dimension.note }}</small></span><em>{{ isDimensionEnabled(dimension.label) ? '已启用' : '已停用' }}</em></label></div></section>
          <section v-else class="harness-panel evaluation-subpage"><div class="harness-panel-heading"><div><h3>历史报告</h3></div><button class="button button-subtle" type="button" @click="selectEvaluationTab('reports')"><ArrowDownToLine :size="14" />导出样本</button></div><div v-if="evalReports.length" class="evaluation-report-list"><button v-for="report in evalReports" :key="report.runId" :disabled="evalRunBusy" @click="openEvalRun(report.runId)" class="evaluation-report-row"><strong>{{ report.runId }}</strong><span>{{ report.date }}</span><b>{{ report.score }}</b><span class="dataset-state" :class="{ attention: report.state !== '已完成' }"><i></i>{{ report.state }}</span><ArrowRight :size="14" /></button></div><div v-else class="release-empty"><span>暂无真实测评运行记录</span><small>未连接测评服务</small></div>
          <div class="harness-detail-block"><strong>报告对比</strong><div class="harness-detail-actions"><select v-model="evalCompareBase"><option value="">基线测评运行</option><option v-for="run in evalRuns" :key="`cmp-base-${run.eval_run_id}`" :value="run.eval_run_id">{{ run.eval_run_id }} · {{ evalStatusLabel(run.status) }}</option></select><select v-model="evalCompareTarget"><option value="">目标测评运行</option><option v-for="run in evalRuns" :key="`cmp-target-${run.eval_run_id}`" :value="run.eval_run_id">{{ run.eval_run_id }} · {{ evalStatusLabel(run.status) }}</option></select><button class="button button-subtle" type="button" :disabled="evalComparisonBusy || !evalCompareBase || !evalCompareTarget" @click="compareEvalRuns">{{ evalComparisonBusy ? '对比中…' : '对比报告' }}</button></div><p v-if="evalComparisonError" role="alert">{{ evalComparisonError }}</p><div v-if="evalComparison" class="harness-detail-rows"><div class="harness-detail-row"><span>测评集</span><span>{{ evalComparison.sameDataset ? '同一测评集' : '不同测评集' }}</span></div><div class="harness-detail-row"><span>通过率</span><span>{{ formatPercentNumber(evalComparison.summaryDiff.passRate?.base) ?? '—' }} → {{ formatPercentNumber(evalComparison.summaryDiff.passRate?.target) ?? '—' }}（{{ formatPercentNumber(evalComparison.summaryDiff.passRate?.delta) }}）</span></div><div class="harness-detail-row"><span>样本 / 通过 / 失败</span><span>{{ evalComparison.summaryDiff.caseCount?.base }} → {{ evalComparison.summaryDiff.caseCount?.target }} · {{ evalComparison.summaryDiff.passedCount?.base }} → {{ evalComparison.summaryDiff.passedCount?.target }} · {{ evalComparison.summaryDiff.failedCount?.base }} → {{ evalComparison.summaryDiff.failedCount?.target }}</span></div><div v-for="item in evalComparison.cases" :key="`cmp-${item.caseId}`" class="harness-detail-row"><span>{{ item.caseId }} · {{ item.change }}</span><span>{{ item.base?.verdict || '—' }} → {{ item.target?.verdict || '—' }}</span></div></div></div>
          <div class="harness-detail-block"><strong>导出测评报告</strong><div class="harness-detail-actions"><select v-model="evalExportRunId"><option value="">选择测评运行</option><option v-for="run in evalRuns" :key="`exp-${run.eval_run_id}`" :value="run.eval_run_id">{{ run.eval_run_id }} · {{ evalStatusLabel(run.status) }}</option></select><button class="button button-subtle" type="button" :disabled="!evalExportRunId" @click="exportEvalRunSamples('csv')">导出样本 CSV</button><button class="button button-subtle" type="button" :disabled="!evalExportRunId" @click="exportEvalRunSamples('json')">导出 JSON</button></div></div></section>
          <footer class="page-footer"><span><i class="footer-health demo-health"></i>{{ evaluationConnected ? '已连接测评服务 · 测评在后台执行' : '未连接测评服务' }}</span></footer>
        </section>
        <section v-else-if="activeSection === 'settings'" class="resource-page">
          <div class="release-toolbar"><div><h2>Harness 设置</h2></div><button class="button button-primary" @click="saveSettings"><Check :size="14" />保存设置</button></div>
          <section class="harness-panel resource-table-panel"><div class="harness-panel-heading"><div><h3>运行策略</h3><p>{{ settingsConnected ? '设置已连接' : '当前使用默认值' }}</p></div><button class="button button-subtle" @click="refreshHarnessSettings">刷新设置</button></div><div class="release-form settings-form"><label>默认隔离方式<select v-model="harnessSettings.isolation"><option value="container">容器</option><option value="process">进程</option><option value="host">主机</option></select></label><label>审计保留天数<input v-model.number="harnessSettings.auditRetentionDays" type="number" min="1" max="3650" /></label><label>审批策略<select v-model="harnessSettings.approvalPolicy"><option value="risk-based">按风险等级</option><option value="always">所有写入都审批</option><option value="never">不自动审批</option></select></label><label>默认预算（USD）<input v-model.number="harnessSettings.defaultBudgetUsd" type="number" min="0" step="0.01" /></label><label>默认超时（秒）<input v-model.number="harnessSettings.defaultTimeoutSeconds" type="number" min="1" max="86400" /></label><label>默认重试次数<input v-model.number="harnessSettings.defaultRetryCount" type="number" min="0" max="10" /></label></div></section>
          <footer class="page-footer"><span><i class="footer-health demo-health"></i>{{ settingsConnected ? '已连接设置 API' : '默认设置 · 未连接设置 API' }}</span></footer>
        </section>
        <section v-else-if="activeSection === 'artifacts'" class="resource-page">
          <div class="release-toolbar"><div><h2>产物与存储</h2></div></div>
          <section class="harness-panel resource-table-panel"><ArtifactList :api-base="props.apiBase" /></section>

        </section>
        <section v-else-if="activeSection === 'observability'" class="resource-page">
          <div class="release-toolbar"><div><h2>追踪与日志</h2></div><button class="button button-subtle" @click="refreshResourceData">刷新数据</button></div>
          <section class="harness-panel resource-table-panel"><div class="harness-panel-heading"><div><h3>运行 Trace</h3><p>{{ traceRunRows.length }} 条记录 · 只读</p></div></div><div v-if="traceRunRows.length" class="resource-table"><div class="resource-table-head workspace-cols"><span>运行</span><span>Agent</span><span>任务</span><span>状态</span><span>时间</span></div><div v-for="row in traceRunRows" :key="row.run_id" class="resource-row workspace-cols"><span><strong>{{ row.run_id }}</strong></span><span>{{ row.agent }}</span><span>{{ row.query }}</span><span>{{ row.status }}</span><span>{{ row.created_at }}</span></div></div><div v-else class="release-empty"><span>暂无记录</span></div></section>
          <section class="harness-panel resource-table-panel"><div class="harness-panel-heading"><div><h3>运行事件</h3><p>{{ traceEvents.length }} 条事件 · 只读</p></div><button class="button button-subtle" :disabled="traceEventsBusy" @click="loadTraceEvents">{{ traceEventsBusy ? '读取中…' : '刷新事件' }}</button></div><div class="harness-detail-actions"><select v-model="selectedTraceRunId" @change="loadTraceEvents"><option value="">选择运行</option><option v-for="row in traceRunRows" :key="`trace-${row.run_id}`" :value="row.run_id">{{ row.run_id }} · {{ row.status }}</option></select><select v-model="traceFilters.level"><option value="">全部级别</option><option value="info">info</option><option value="warn">warn</option><option value="error">error</option></select><select v-model="traceFilters.type"><option value="">全部类型</option><option value="tool_start">tool_start</option><option value="tool_end">tool_end</option><option value="step">step</option><option value="usage">usage</option><option value="policy">policy</option></select><input v-model="traceFilters.tool" placeholder="工具名" /><input v-model="traceFilters.since" placeholder="起始时间" /><input v-model="traceFilters.until" placeholder="结束时间" /><label class="release-checkbox"><input v-model="traceFilters.hasError" type="checkbox" />只看错误</label><button class="button button-subtle" :disabled="traceEventsBusy" @click="loadTraceEvents">筛选</button><a v-if="selectedTraceRun" class="button button-subtle" :href="harnessTraceExportUrl(props.apiBase, selectedTraceRun.run_id)" download>导出该运行 JSON</a></div><p v-if="traceEventsError" role="alert">{{ traceEventsError }}</p><div v-if="traceEvents.length" class="resource-table"><div class="resource-table-head workspace-cols"><span>事件</span><span>类型</span><span>级别</span><span>工具</span><span>时间</span></div><div v-for="item in traceEvents" :key="item.event_id" class="resource-row workspace-cols"><span><strong>#{{ item.event_id }}</strong><small>{{ item.summary }}</small></span><span>{{ item.type || '—' }}</span><span>{{ item.level }}</span><span>{{ item.tool || '—' }}</span><span>{{ item.created_at }}</span></div></div><div v-else class="release-empty"><span>该运行没有匹配的事件</span></div></section>
          <section class="harness-panel resource-table-panel"><div class="harness-panel-heading"><div><h3>运行指标</h3><p>{{ traceMetrics ? '共 ' + traceMetrics.runs + ' 条运行记录' : '未读取到指标' }}</p></div><button class="button button-subtle" @click="loadTraceMetrics">刷新指标</button></div><div v-if="traceMetrics" class="release-history-list"><div class="release-history-row"><span>错误事件</span><strong>{{ traceMetrics.errors }}</strong><span>工具调用</span><b>{{ traceMetrics.toolCalls }}</b><code>统计近 {{ traceMetrics.limit }} 条运行</code></div><div v-for="(count, status) in traceMetrics.byStatus" :key="`status-${status}`" class="release-history-row"><span>{{ status }}</span><strong>{{ count }}</strong></div></div><div v-else class="release-empty"><span>暂无指标</span></div></section>
          <section class="harness-panel resource-table-panel"><div class="harness-panel-heading"><div><h3>指标趋势</h3><p>按 {{ traceTrendBucket === 'hour' ? '小时' : '天' }} 聚合</p></div><div class="harness-detail-actions"><select v-model="traceTrendBucket" @change="loadTraceTrends"><option value="hour">按小时</option><option value="day">按天</option></select><button class="button button-subtle" :disabled="trendsBusy" @click="loadTraceTrends">{{ trendsBusy ? '读取中…' : '刷新趋势' }}</button></div></div><p v-if="trendsError" role="alert">{{ trendsError }}</p><div v-if="traceTrends.length" class="resource-table"><div class="resource-table-head workspace-cols"><span>时间桶</span><span>运行</span><span>完成</span><span>失败</span><span>取消</span><span>错误</span><span>工具调用</span></div><div v-for="point in traceTrends" :key="point.bucketStart" class="resource-row workspace-cols"><span><strong>{{ point.bucketStart }}</strong></span><span>{{ point.runs }}</span><span>{{ point.completed }}</span><span>{{ point.failed }}</span><span>{{ point.cancelled }}</span><span>{{ point.errors }}</span><span>{{ point.toolCalls }}</span></div></div><div v-else class="release-empty"><span>暂无趋势数据</span></div></section>
          <section class="harness-panel resource-table-panel"><div class="harness-panel-heading"><div><h3>跨运行日志导出</h3></div></div><div class="harness-detail-actions"><input v-model="exportFrom" placeholder="起始时间" /><input v-model="exportTo" placeholder="结束时间" /><input v-model="exportRunId" placeholder="运行编号（可选）" /><button class="button button-subtle" :disabled="exportBusy" @click="exportObservabilityEvents('csv')">{{ exportBusy ? '导出中…' : '导出 CSV' }}</button><button class="button button-subtle" :disabled="exportBusy" @click="exportObservabilityEvents('json')">导出 JSON</button></div><p v-if="exportError" role="alert">{{ exportError }}</p></section>
          <footer class="page-footer"><span><i class="footer-health demo-health"></i>{{ resourceConnected ? '已连接只读运营 API' : '未连接运营 API' }}</span></footer>
        </section>
        <section v-else-if="['machines', 'approvals'].includes(activeSection)" class="resource-page">
          <div class="release-toolbar"><div><h2>{{ activeSection === 'machines' ? '机器与运行时' : '待审批' }}</h2></div><button class="button button-subtle" @click="refreshResourceData">刷新状态</button></div>
          <section class="harness-panel resource-table-panel"><div class="harness-panel-heading"><div><h3>{{ activeSection === 'machines' ? '运行时节点' : '审批队列' }}</h3></div><div v-if="activeSection === 'approvals'" class="harness-detail-actions"><button class="button button-subtle" type="button" :disabled="approvalBusy || !approvalSelection.length" @click="decideApprovalBatch('approved')">批量批准 ({{ approvalSelection.length }})</button><button class="button button-subtle" type="button" :disabled="approvalBusy || !approvalSelection.length" @click="decideApprovalBatch('rejected')">批量拒绝</button><a class="button button-subtle" :href="harnessApprovalAuditUrl(props.apiBase)" download>导出审计</a></div></div><div v-if="activeSection === 'machines' && machineRows.length" class="resource-table"><div class="resource-table-head workspace-cols"><span>Worker</span><span>进程</span><span>最近心跳</span><span>当前运行</span><span>容量</span><span>状态</span><span>错误</span></div><div v-for="row in machineRows" :key="row.worker_id" class="resource-row workspace-cols"><span><strong>{{ row.worker_id }}</strong></span><span>{{ row.process_id }}</span><span>{{ formatWorkerSeen(row.last_seen) }}</span><span>{{ row.current_run_id || '空闲' }}</span><span>{{ row.capacity ?? 1 }}</span><span>{{ row.state === 'draining' ? '排空中' : row.state === 'offline' ? '离线' : row.current_run_id ? '运行中' : '在线' }}</span><span><button class="text-action" :disabled="machineErrorsBusy" @click="loadMachineErrors(row.worker_id)">错误日志</button><button class="text-action" :disabled="machineBusy === row.worker_id" @click="toggleMachineDrain(row)">{{ machineBusy === row.worker_id ? '处理中…' : row.state === 'draining' ? '恢复' : '排空' }}</button></span></div></div><div v-else-if="activeSection === 'approvals' && approvalRows.length" class="resource-table"><div class="resource-table-head workspace-cols"><span>选择</span><span>请求</span><span>工具</span><span>运行</span><span>风险</span><span>决定</span></div><div v-for="row in approvalRows" :key="row.request_id" class="resource-row workspace-cols"><span><input type="checkbox" :value="row.request_id" v-model="approvalSelection" :disabled="row.status !== 'pending'" /></span><span><strong>{{ row.request_id }}</strong><small>{{ row.detail }}</small></span><span>{{ row.tool }}</span><span>{{ row.run_id }}</span><span>{{ row.risk }}</span><span><button v-if="row.status === 'pending'" class="text-action" :disabled="approvalBusy" @click="decideApproval(row, 'approved')">批准</button><button v-if="row.status === 'pending'" class="text-action" :disabled="approvalBusy" @click="openRejectDialog(row)">拒绝</button><span v-else>{{ row.status }}</span><button class="text-action" @click="openApprovalDetail(row)">详情</button></span></div></div><div v-else class="release-empty"><span>当前没有记录</span></div></section>
          <section v-if="activeSection === 'machines'" class="harness-panel resource-table-panel"><div class="harness-panel-heading"><div><h3>节点错误日志</h3><p>{{ machineErrorWorker ? machineErrorWorker + ' 的失败运行' : '选择节点查看失败运行与错误事件' }}</p></div></div><p v-if="machineErrorsError" role="alert">{{ machineErrorsError }}</p><div v-if="machineErrors.length" class="release-history-list"><div v-for="item in machineErrors" :key="item.run_id" class="release-history-row"><span>{{ item.finished_at || item.created_at || '—' }}</span><strong>{{ item.run_id }}</strong><span>{{ item.error }}</span><b>{{ item.status }}</b><code>{{ item.events.length }} 条错误事件</code></div><div v-if="item.events.length" class="resource-table"><div v-for="event in item.events" :key="event.event_id" class="resource-row"><span>{{ event.created_at }}</span><span>{{ event.tool || '—' }}</span><span>{{ event.content || '（无内容）' }}</span></div></div></div><div v-else class="release-empty"><span>{{ machineErrorWorker ? '该节点没有失败运行' : '尚未选择节点' }}</span></div></section>
          <section v-if="activeSection === 'approvals'" class="harness-panel resource-table-panel"><div class="harness-panel-heading"><div><h3>审批通知</h3><p>{{ approvalNotifications.length }} 条通知记录 · 审批决定后产生</p></div><button class="button button-subtle" :disabled="notificationsBusy" @click="loadApprovalNotifications">{{ notificationsBusy ? '读取中…' : '刷新通知' }}</button></div><p v-if="notificationsError" role="alert">{{ notificationsError }}</p><div v-if="approvalNotifications.length" class="resource-table"><div class="resource-table-head workspace-cols"><span>通知 / 时间</span><span>审批请求</span><span>事件</span><span>通道</span><span>状态</span></div><div v-for="row in approvalNotifications" :key="row.notification_id" class="resource-row workspace-cols"><span><strong>{{ row.notification_id }}</strong><small>{{ row.created_at }}</small></span><span>{{ row.request_id }}</span><span>{{ row.event }}</span><span>{{ row.channel }}</span><span>{{ row.status }}<small v-if="row.detail">{{ row.detail }}</small></span></div></div><div v-else class="release-empty"><span>暂无审批通知</span></div></section>
          <footer class="page-footer"><span><i class="footer-health demo-health"></i>{{ resourceConnected ? '已连接治理 API' : '未连接治理 API' }}</span></footer>
        </section>
        <section v-else-if="activeSection === 'tools'" class="resource-page">
          <div class="release-toolbar"><div><h2>工具与 MCP</h2></div><button class="button button-primary" @click="openToolDialog"><Plus :size="14" />登记工具</button></div>
          <p v-if="toolsError" role="alert">{{ toolsError }}</p>
          <section class="harness-panel resource-table-panel">
            <div class="harness-panel-heading"><div><h3>工具目录</h3><p>{{ toolRows.length }} 条记录 · {{ toolsConnected ? '已连接工具目录' : '演示数据' }}</p></div><button class="button button-subtle" @click="refreshToolData">刷新目录</button></div>
            <div v-if="toolRows.length" class="resource-table wide-actions">
              <div class="resource-table-head"><span>工具 / 来源</span><span>范围</span><span>风险</span><span>登记状态</span><span></span></div>
              <div v-for="row in toolRows" :key="row.tool_id" class="resource-row"><span><strong>{{ row.name }}</strong><small>{{ row.source }}</small><small v-if="toolTestResults[row.tool_id]" :class="toolTestResults[row.tool_id].ok ? '' : 'stat-warn'">{{ toolTestResults[row.tool_id].ok ? '连接正常' : toolTestResults[row.tool_id].message }}</small></span><span>{{ row.scope }}</span><span>{{ row.risk }}</span><span>{{ row.status }}</span><span><button class="text-action" :disabled="toolTestBusy === row.tool_id || !toolsConnected" :title="toolsConnected ? '测试工具连接' : '演示数据，未连接工具目录'" @click="testToolConnection(row)">{{ toolTestBusy === row.tool_id ? '测试中…' : '连接测试' }}</button><button class="text-action" @click="openToolDetails(row)">查看</button></span></div>
            </div>
            <div v-else class="release-empty"><span>尚未登记工具</span><button class="text-action" @click="openToolDialog">登记第一个工具</button></div>
          </section>
          <section class="harness-panel resource-table-panel">
            <div class="harness-panel-heading"><div><h3>MCP 连接器</h3><p>{{ harnessMcpServers.length }} 个连接器 · {{ toolsConnected ? '已连接目录' : '演示数据' }}</p></div></div>
            <p v-if="mcpServersError" role="alert">{{ mcpServersError }}</p>
            <div v-if="harnessMcpServers.length" class="resource-table">
              <div class="resource-table-head"><span>连接器 / 来源</span><span>状态</span><span>已发现工具</span><span>工具编号</span></div>
              <div v-for="row in harnessMcpServers" :key="row.tool_id" class="resource-row"><span><strong>{{ row.name }}</strong><small>{{ row.source }}</small><small v-if="row.message" class="stat-warn">{{ row.message }}</small></span><span>{{ row.status || '未记录状态' }}</span><span>{{ (row.tools || []).length ? row.tools.join('、') : '未发现工具' }}</span><span>{{ row.tool_id }}</span></div>
            </div>
            <div v-if="harnessMcpServers.length" class="harness-detail-block"><strong>工具调用</strong><div class="harness-detail-actions"><select v-model="mcpToolPick"><option value="">选择工具</option><template v-for="row in harnessMcpServers" :key="`call-${row.tool_id}`"><option v-for="tool in row.tools || []" :key="tool" :value="`${row.tool_id}::${tool}`">{{ row.name }} · {{ tool }}</option></template></select><input v-model="mcpCallArgs" placeholder='调用参数 JSON，例如 {"query":"测试"}' /><button class="button button-subtle" type="button" :disabled="mcpCallBusy || !mcpToolPick" @click="callSelectedMcpTool">{{ mcpCallBusy ? '调用中…' : '调用工具' }}</button></div><p v-if="mcpCallError" role="alert">{{ mcpCallError }}</p><pre v-if="mcpCallResult" class="execution-text">{{ JSON.stringify(mcpCallResult, null, 2) }}</pre></div>
            <div v-else class="release-empty"><span>暂无 MCP 连接器</span></div>
          </section>
        </section>
        <section v-else-if="activeSection === 'models'" class="resource-page">
          <div class="release-toolbar"><div><h2>模型路由</h2></div><button class="button button-primary" @click="openModelDialog"><Plus :size="14" />登记模型路由</button></div>
          <p v-if="modelsError" role="alert">{{ modelsError }}</p>
          <section class="harness-panel resource-table-panel">
            <div class="harness-panel-heading"><div><h3>模型路由目录</h3><p>{{ modelRows.length }} 条记录 · {{ modelsConnected ? '已连接目录' : '演示数据' }}</p></div><button class="button button-subtle" @click="refreshModelData">刷新目录</button></div>
            <div v-if="modelRows.length" class="resource-table wide-actions">
              <div class="resource-table-head"><span>模型 / 提供商</span><span>路由用途</span><span>备用模型</span><span>登记状态</span><span></span></div>
              <div v-for="row in modelRows" :key="row.model_id" class="resource-row"><span><strong>{{ row.name }}</strong><small>{{ row.provider || '未指定提供商' }}</small><small v-if="modelTestResults[row.model_id]" :class="modelTestResults[row.model_id].ok ? '' : 'stat-warn'">{{ modelTestResults[row.model_id].ok ? '连接正常' : modelTestResults[row.model_id].message }}</small></span><span>{{ row.route }}</span><span>{{ harnessModels.find(item => item.model_id === row.fallback_model_id)?.name || row.fallback_model_id || '无' }}</span><span>{{ row.status }}</span><span><button class="text-action" :disabled="modelTestBusy === row.model_id || !modelsConnected" :title="modelsConnected ? '测试模型路由连接' : '演示数据，未连接模型目录'" @click="testModelConnection(row)">{{ modelTestBusy === row.model_id ? '测试中…' : '连接测试' }}</button><button class="text-action" @click="openModelDetails(row)">查看</button></span></div>
            </div>
            <div v-else class="release-empty"><span>尚未登记模型路由</span><button class="text-action" @click="openModelDialog">登记第一个模型路由</button></div>
          </section>
        </section>
        <section v-else-if="activeSection === 'skills'" class="resource-page">
          <div class="release-toolbar"><div><h2>Skills</h2></div><button class="button button-subtle" @click="refreshActiveSection">刷新目录</button></div>
          <div class="evaluation-tabs" role="group" aria-label="Skill 来源"><button :class="{ active: skillDirectoryTab === 'installed' }" @click="selectSkillDirectory('installed')">本地安装包</button><button :class="{ active: skillDirectoryTab === 'catalog' }" @click="selectSkillDirectory('catalog')">Catalog 版本</button></div>
          <template v-if="skillDirectoryTab === 'installed'">
          <p v-if="skillsError" role="alert">{{ skillsError }}</p>
          <section class="harness-panel resource-table-panel"><div class="harness-panel-heading"><div><h3>本地 Skill 安装目录</h3><p>{{ skillRows.length }} 条记录 · {{ skillsConnected ? '已连接目录' : '演示数据' }}</p></div></div>
            <div v-if="skillRows.length" class="resource-table">
              <div class="resource-table-head"><span>名称 / 说明</span><span>来源文件</span><span>入口</span><span>状态</span><span></span></div>
              <div v-for="row in skillRows" :key="row.id" class="resource-row"><span><strong>{{ row.name }}</strong><small>{{ row.description || '暂无描述' }}</small></span><span>{{ row.sourceFile || '本地安装包' }}</span><span>{{ row.entry || '—' }}</span><span>{{ row.enabled ? '已启用' : '已停用' }}</span><button class="text-action" @click="openSkillDetails(row)">查看</button></div>
            </div>
            <div v-else class="release-empty"><span>尚未安装本地 Skill 包</span></div>
          </section>
          </template>
          <section v-else class="harness-panel resource-table-panel">
            <div class="harness-panel-heading"><div><h3>Catalog 版本与项目绑定</h3><p>{{ catalog.project || '当前项目' }} · {{ catalogNames.length }} 个技能 · {{ catalog.skills.length }} 个版本</p></div></div>
            <p v-if="catalogError" role="alert">{{ catalogError }}</p>
            <div v-if="catalogLoading" class="release-empty">正在读取 Catalog…</div>
            <div v-else-if="catalogNames.length" class="resource-table">
              <div class="resource-table-head"><span>技能</span><span>版本数</span><span>项目绑定</span><span>灰度状态</span><span></span></div>
              <div v-for="name in catalogNames" :key="name" class="resource-row"><span><strong>{{ name }}</strong></span><span>{{ catalog.skills.filter(row => row.name === name).length }}</span><span>{{ catalog.bindings.find(row => row.name === name)?.version || '未绑定' }}</span><span>{{ catalog.rollouts.find(row => row.name === name && row.active)?.percentage ?? '—' }}{{ catalog.rollouts.some(row => row.name === name && row.active) ? '%' : '' }}</span><button class="text-action" @click="openCatalogSkill(name)">查看</button></div>
            </div>
            <div v-else class="release-empty">当前没有 Catalog 版本</div>
          </section>
        </section>
        <section v-else-if="['agents', 'workspaces'].includes(activeSection)" class="resource-page">
          <div class="release-toolbar"><div><h2>{{ activeSection === 'agents' ? 'Agent 实例' : '工作空间' }}</h2></div><button class="button button-primary" @click="activeSection === 'agents' ? openAgentDialog() : openWorkspaceDialog()"><Plus :size="14" />{{ activeSection === 'agents' ? '新建 Agent' : '新建工作空间' }}</button></div>
          <p v-if="activeSection === 'agents' && agentsError" role="alert">{{ agentsError }}</p><p v-if="activeSection === 'workspaces' && workspacesError" role="alert">{{ workspacesError }}</p><section class="harness-panel resource-table-panel"><div class="harness-panel-heading"><div><h3>{{ activeSection === 'agents' ? 'Agent 目录' : '工作空间目录' }}</h3></div><button class="button button-subtle" @click="refreshActiveSection">刷新目录</button></div><div v-if="activeSection === 'agents' && agentRows.length" class="resource-table wide-actions"><div class="resource-table-head"><span>名称</span><span>版本</span><span>模型</span><span>启停</span><span></span></div><div v-for="row in agentRows" :key="row.agent_id" class="resource-row"><span><strong>{{ row.name }}</strong><small>{{ row.description || '暂无描述' }} · {{ row.status || '未记录状态' }}</small></span><span>{{ row.version }}</span><span>{{ row.model }}</span><span><span class="dataset-state" :class="{ attention: row.enabled === false }"><i></i>{{ row.enabled === true ? '启用' : row.enabled === false ? '停用' : '未连接' }}</span></span><span><button class="text-action" :disabled="agentStatusBusy === row.agent_id || !agentsConnected" :title="agentsConnected ? (row.enabled ? '停用该 Agent' : '启用该 Agent') : '演示数据，未连接资源目录'" @click="toggleAgentStatus(row)">{{ agentStatusBusy === row.agent_id ? '处理中…' : row.enabled ? '停用' : '启用' }}</button><button class="text-action" @click="openAgentDetails(row)">查看</button></span></div></div><div v-else-if="activeSection === 'workspaces' && workspaceRows.length" class="resource-table"><div class="resource-table-head workspace-cols"><span>名称</span><span>仓库</span><span>分支</span><span>状态</span><span></span></div><div v-for="row in workspaceRows" :key="row.workspace_id" class="resource-row workspace-cols"><span><strong>{{ row.name }}</strong><small>{{ row.workspace_id }}</small></span><span>{{ row.repository || '未绑定仓库' }}</span><span>{{ row.branch }}</span><span>{{ row.status }}</span><button class="text-action" @click="openWorkspaceDetails(row)">查看</button></div></div><div v-else class="release-empty"><span>还没有资源记录</span></div></section>
          <footer class="page-footer"><span><i class="footer-health demo-health"></i>{{ (activeSection === 'agents' ? agentsConnected : workspacesConnected) ? '已连接资源目录' : '未连接资源 API' }}</span></footer>
        </section>
        <section v-else-if="activeSection === 'releases'" class="release-page">
          <div class="release-toolbar"><div><h2>发布治理</h2></div><button class="button button-subtle" @click="refreshReleaseData">刷新发布状态</button></div>
          <div class="release-kpis"><div><span>活动灰度</span><strong>{{ releaseRollouts.filter(item => item.active).length }}</strong><small>当前项目绑定</small></div><div><span>最高灰度比例</span><strong>{{ releaseRollouts.length ? Math.max(...releaseRollouts.map(item => item.percentage || 0)) : 0 }}%</strong><small>按技能版本统计</small></div><div><span>发布记录</span><strong>{{ releaseRecords.length }}</strong><small>发布、回滚与推进审计</small></div><div><span>线上指标</span><strong>{{ releaseMetrics.length }}</strong><small>最近 500 条</small></div></div>
          <div class="release-grid"><section class="harness-panel"><div class="harness-panel-heading"><div><h3>当前灰度</h3></div></div><div v-if="releaseRollouts.length" class="release-table rollout-table"><div class="release-table-head"><span>项目 / 技能</span><span>候选版本</span><span>旧版本</span><span>比例</span><span>状态</span><span>推进灰度 / 回滚</span></div><div v-for="row in releaseRollouts" :key="rolloutKey(row)" class="release-row"><span><strong>{{ row.name }}</strong><small>{{ row.project }}</small></span><span>{{ row.candidate_version }}</span><span>{{ row.previous_version || '—' }}</span><span>{{ row.percentage }}%</span><span>{{ row.active ? '灰度中' : '已回滚' }}</span><span class="rollout-advance"><input v-if="row.active" v-model.number="rolloutAdvanceDrafts[rolloutKey(row)]" type="number" min="0" max="100" aria-label="目标灰度比例" /><button v-if="row.active" class="text-action" :disabled="rolloutBusy === rolloutKey(row)" @click="advanceRolloutRow(row)">{{ rolloutBusy === rolloutKey(row) ? '推进中…' : '推进灰度' }}</button><button v-if="row.active" class="text-action" :disabled="observationBusy === rolloutKey(row)" @click="observeRollout(row)">{{ observationBusy === rolloutKey(row) ? '观察中…' : '立即观察' }}</button><button v-if="row.active" class="text-action" @click="rollbackReleaseByRow(row)">回滚</button><small v-else>已回滚</small></span></div></div><div v-else class="release-empty"><GitBranch :size="20" /><span>当前没有灰度版本</span></div></section><section class="harness-panel"><div class="harness-panel-heading"><div><h3>推进灰度</h3></div></div><div class="release-form"><label>项目<input v-model="releaseDraft.project" /></label><label>技能名称<input v-model="releaseDraft.name" placeholder="例如 incident-summary" /></label><label>候选版本<input v-model="releaseDraft.version" placeholder="例如 v2" /></label><label>灰度比例<input v-model.number="releaseDraft.percentage" type="number" min="0" max="100" /></label><div class="release-gate-fields"><strong>发布前质量门禁</strong><label>评测运行 ID<input v-model="releaseGateDraft.evalRunId" placeholder="可选，关联 evalRunId" /></label><label>端到端通过率<input v-model.number="releaseGateDraft.e2ePassRate" type="number" min="0" max="1" step="0.001" /></label><label>RAG 忠实度<input v-model.number="releaseGateDraft.ragFaithfulness" type="number" min="0" max="1" step="0.001" /></label><label>高风险误调用<input v-model.number="releaseGateDraft.highRiskErrors" type="number" min="0" step="1" /></label><button class="button button-subtle" @click="checkReleaseGate">检查质量门禁</button><span v-if="releaseGateResult" class="release-gate-result" :class="{ passed: releaseGateResult.passed }">{{ releaseGateResult.passed ? '门禁通过' : '门禁未通过' }}</span></div><button class="button button-primary" :disabled="!releaseGateResult?.passed" @click="promoteCurrentRelease"><GitBranch :size="14" />进入灰度</button></div></section></div>
          <section class="harness-panel release-history"><div class="harness-panel-heading"><div><h3>灰度观察记录</h3></div><button class="button button-subtle" :disabled="observationsBusy" @click="loadReleaseObservations">{{ observationsBusy ? '读取中…' : '刷新观察记录' }}</button></div><p v-if="observationError" role="alert">{{ observationError }}</p><div v-if="releaseObservations.length" class="release-history-list"><div v-for="row in releaseObservations" :key="row.observation_id" class="release-history-row"><span>{{ row.created_at || '—' }}</span><strong>{{ row.name }}</strong><span>{{ row.project }} / {{ row.version || '—' }} · {{ row.percentage }}%</span><b>{{ row.auto_rolled_back ? '已自动回滚' : '观察完成' }}</b><code>错误率 {{ row.error_rate }} · 样本 {{ row.sample_count }} · 阈值 {{ row.threshold }}</code></div></div><div v-else class="release-empty"><span>暂无观察记录</span></div></section>
          <section class="harness-panel release-history"><div class="harness-panel-heading"><div><h3>发布记录</h3></div><span v-if="releaseRecordsBusy" class="release-gate-result">加载中…</span></div><div v-if="releaseRecordRows.length" class="release-record-list"><div class="release-record-head"><span>时间</span><span>项目 / 技能</span><span>版本</span><span>动作</span><span>灰度比例</span><span>门禁编号</span><span>关联测评运行</span><span>审批人</span><span>门禁检查</span></div><div v-for="row in releaseRecordRows" :key="row.record_id" class="release-record-row"><span>{{ row.created_at || '—' }}</span><span><strong>{{ row.name }}</strong><small>{{ row.project }}</small></span><span>{{ row.version || '—' }}</span><span>{{ row.actionLabel }}</span><span>{{ row.percentage ?? 0 }}%</span><code>{{ row.gate_id || '—' }}</code><code>{{ row.eval_run_id || '—' }}</code><span>{{ row.actor || '—' }}</span><span class="release-record-checks"><template v-if="row.checks.length"><span v-for="check in row.checks" :key="check.label" :class="{ failed: check.passed !== true }">{{ check.label }} {{ check.passed === true ? '通过' : check.passed === false ? '未通过' : '未评估' }}<small v-if="check.threshold != null">（阈值 {{ check.threshold }}）</small></span></template><small v-else>无门禁证据</small></span></div></div><div v-else class="release-empty"><span>{{ releaseRecordsError ? '发布记录读取失败：' + releaseRecordsError : '暂无发布记录' }}</span><small v-if="releaseRecordsError">连接发布治理服务后刷新重试</small></div></section>
          <div class="release-policy-grid"><section class="harness-panel"><div class="harness-panel-heading"><div><h3>门禁阈值</h3></div><span v-if="releasePolicyLoading" class="release-gate-result">加载中…</span><span v-else-if="releasePolicyError" class="release-gate-result">{{ releasePolicyError }}</span></div><div class="release-form"><label>端到端通过率（0-1）<input v-model.number="releaseThresholdsDraft.e2ePassRate" type="number" min="0" max="1" step="0.001" placeholder="例如 0.9" /></label><label>RAG 忠实度（0-1）<input v-model.number="releaseThresholdsDraft.ragFaithfulness" type="number" min="0" max="1" step="0.001" placeholder="例如 0.9" /></label><label>高风险工具误调用上限<input v-model.number="releaseThresholdsDraft.highRiskErrors" type="number" min="0" step="1" placeholder="例如 0" /></label><button class="button button-subtle" :disabled="releaseThresholdsBusy || releaseThresholdsDraft.e2ePassRate == null" @click="saveReleaseThresholds">{{ releaseThresholdsBusy ? '保存中…' : '保存门禁阈值' }}</button></div></section><section class="harness-panel"><div class="harness-panel-heading"><div><h3>发布策略</h3></div><span v-if="releasePolicyLoading" class="release-gate-result">加载中…</span><span v-else-if="releasePolicyError" class="release-gate-result">{{ releasePolicyError }}</span></div><div class="release-form"><label>错误率阈值（0-1）<input v-model.number="releaseConfigDraft.rolloutErrorThreshold" type="number" min="0" max="1" step="0.01" placeholder="例如 0.2" /></label><label>观察最小样本数<input v-model.number="releaseConfigDraft.rolloutMinSamples" type="number" min="0" step="1" placeholder="例如 5" /></label><label class="release-checkbox"><input v-model="releaseConfigDraft.autoRollback" type="checkbox" />错误率超阈值时自动回滚</label><button class="button button-subtle" :disabled="releasePolicyBusy || releaseConfigDraft.rolloutErrorThreshold == null" @click="saveReleasePolicy">{{ releasePolicyBusy ? '保存中…' : '保存发布策略' }}</button></div></section></div>
          <section class="harness-panel release-history"><div class="harness-panel-heading"><div><h3>发布运行</h3></div></div><div v-if="releaseRuns.length" class="release-history-list"><div v-for="row in releaseRuns" :key="row.run_id" class="release-history-row"><span>{{ row.created_at }}</span><strong>{{ row.name }}</strong><span>{{ row.base_version }} → {{ row.candidate_version || '—' }}</span><b>{{ row.status }}</b><code>{{ row.run_id }}</code></div></div><div v-else class="release-empty"><span>暂无发布记录</span></div></section>
          <section class="harness-panel release-history"><div class="harness-panel-heading"><div><h3>质量门禁记录</h3></div></div><div v-if="releaseGates.length" class="release-history-list"><div v-for="row in releaseGates.slice(0, 20)" :key="row.gate_id" class="release-history-row"><span>{{ row.created_at }}</span><strong>{{ row.name || '未命名版本' }}</strong><span>{{ row.eval_run_id || '未关联评测' }}</span><b>{{ row.passed ? '通过' : '未通过' }}</b><code>{{ row.gate_id }}</code></div></div><div v-else class="release-empty"><span>暂无门禁记录</span></div></section>
          <section class="harness-panel release-history"><div class="harness-panel-heading"><div><h3>线上指标</h3></div></div><div v-if="releaseMetrics.length" class="release-history-list"><div v-for="row in releaseMetrics.slice(0, 20)" :key="`${row.id}-${row.created_at}`" class="release-history-row"><span>{{ row.created_at }}</span><strong>{{ row.metric }}</strong><span>{{ row.name }} / {{ row.version }}</span><b>{{ row.value }}</b><code>{{ row.request_id || '—' }}</code></div></div><div v-else class="release-empty"><span>暂无线上指标</span></div></section>
          <footer class="page-footer"><span><i class="footer-health demo-health"></i>{{ releaseConnected ? '已连接发布目录' : '未连接发布 API' }}</span></footer>
        </section>
      </div></div>
      <div v-if="selectedCatalogName" class="modal-backdrop" @click.self="!catalogDetailBusy && (selectedCatalogName = '')">
        <section class="dialog skills-dialog" role="dialog" aria-modal="true" aria-labelledby="catalog-detail-title">
          <div class="dialog-heading"><div class="dialog-symbol"><Sparkles :size="19" /></div><button class="icon-button" type="button" :disabled="catalogDetailBusy" aria-label="关闭 Catalog 详情" @click="selectedCatalogName = ''"><X :size="18" /></button></div>
          <h2 id="catalog-detail-title">{{ selectedCatalogName }}</h2>
          <p>项目 {{ catalog.project }} · 绑定 {{ catalog.bindings.find(row => row.name === selectedCatalogName)?.version || '未绑定' }}</p>
          <label class="run-create-field"><span>查看版本</span><select v-model="catalogVersion" :disabled="catalogDetailBusy" @change="loadCatalogVersion"><option v-for="row in catalogVersions" :key="row.version" :value="row.version">{{ row.version }}</option></select></label>
          <p v-if="catalogDetailBusy" role="status">正在读取…</p><p v-if="catalogDetailError" role="alert">{{ catalogDetailError }}</p>
          <template v-if="catalogDetail"><p>{{ catalogDetail.description }} · {{ catalogDetail.created_at }}</p><h3>SKILL.md</h3><pre class="skill-detail-content">{{ catalogDetail.content }}</pre><p v-if="catalogDetail.truncated">正文预览展示前 12000 个字符。</p><h3>附加资源</h3><ul><li v-for="resource in catalogDetail.resources" :key="resource.path">{{ resource.path }} · {{ resource.chars }} 字符</li></ul><p v-if="!catalogDetail.resources.length">无附加资源</p></template>
          <label class="run-create-field"><span>比较基准</span><select v-model="catalogBaseVersion" :disabled="catalogDetailBusy" @change="catalogComparison = null"><option v-for="row in catalogVersions" :key="row.version" :value="row.version">{{ row.version }}</option></select></label>
          <button class="secondary-button" type="button" :disabled="catalogDetailBusy" @click="compareCatalogSkill">比较版本</button>
          <div class="harness-detail-block"><strong>项目绑定</strong><div class="harness-detail-actions"><label>灰度比例<input v-model.number="catalogBindPercentage" type="number" min="0" max="100" :disabled="catalogBindBusy" /></label><button class="button button-subtle" type="button" :disabled="catalogBindBusy" @click="bindSelectedCatalogVersion">{{ catalogBindBusy ? '处理中…' : '绑定到当前项目' }}</button><button class="button button-subtle" type="button" :disabled="catalogBindBusy" @click="unbindCurrentCatalogSkill">解除绑定</button></div><p v-if="catalogBindError" role="alert">{{ catalogBindError }}</p></div>
          <template v-if="catalogComparison"><p>{{ catalogComparison.baseVersion }} → {{ catalogComparison.version }}</p><pre class="skill-detail-content">{{ catalogComparison.diff || '正文无差异' }}</pre><p v-if="catalogComparison.truncated">差异内容超过展示上限。</p><ul><li v-for="change in catalogComparison.resourceChanges" :key="change.path">{{ change.change === 'added' ? '新增' : change.change === 'removed' ? '删除' : '修改' }} · {{ change.path }}</li></ul><p v-if="!catalogComparison.resourceChanges.length">附加资源无变化</p></template>
          <div class="dialog-actions"><button class="secondary-button" type="button" :disabled="catalogDetailBusy" @click="selectedCatalogName = ''">关闭</button></div>
        </section>
      </div>
      <div v-if="selectedSkill" class="modal-backdrop" @click.self="!skillChangingId && (selectedSkill = null)">
        <section class="dialog skills-dialog" role="dialog" aria-modal="true" aria-labelledby="skill-detail-title">
          <div class="dialog-heading"><div class="dialog-symbol"><Sparkles :size="19" /></div><button class="icon-button" type="button" :disabled="!!skillChangingId" aria-label="关闭 Skill 详情" @click="selectedSkill = null"><X :size="18" /></button></div>
          <h2 id="skill-detail-title">{{ selectedSkill.name }}</h2>
          <p>{{ selectedSkill.description || '暂无描述' }}</p>
          <p>本地安装包 · {{ selectedSkill.id }} · {{ selectedSkill.enabled ? '已启用' : '已停用' }}</p>
          <p>来源文件 {{ selectedSkill.sourceFile }} · 入口 {{ selectedSkill.entry }}</p>
          <p>安装时间 {{ selectedSkill.createdAt || '未记录' }}</p>
          <h3>SKILL.md</h3><pre class="skill-detail-content">{{ selectedSkill.content }}</pre>
          <p v-if="selectedSkill.truncated">正文超过预览上限，当前展示前 12000 个字符。</p>
          <p v-if="skillChangeError" role="alert">{{ skillChangeError }}</p>
          <div class="dialog-actions"><button class="secondary-button" type="button" :disabled="!!skillChangingId" @click="selectedSkill = null">关闭</button><button class="primary-button" type="button" :disabled="!!skillChangingId" @click="toggleInstalledSkill(selectedSkill)">{{ skillChangingId ? '处理中…' : selectedSkill.enabled ? '停用 Skill' : '启用 Skill' }}</button></div>
        </section>
      </div>
      <div v-if="showModelDialog" class="modal-backdrop" @click.self="!modelSaving && (showModelDialog = false)">
        <form class="dialog run-create-dialog" role="dialog" aria-modal="true" aria-labelledby="model-editor-title" @submit.prevent="saveModel">
          <div class="dialog-heading"><div class="dialog-symbol"><Network :size="19" /></div><button class="icon-button" type="button" :disabled="modelSaving" aria-label="关闭模型配置" @click="showModelDialog = false"><X :size="18" /></button></div>
          <h2 id="model-editor-title">{{ editingModel ? '模型路由详情与编辑' : '登记模型路由' }}</h2>
          <p v-if="editingModel">{{ editingModel.model_id }} · 修订 {{ editingModel.revision }} · 更新时间 {{ editingModel.updated_at }}</p>
          <div v-if="editingModel" class="harness-detail-block"><strong>回退链</strong><p v-if="!modelFallbackChain.length">该模型没有配置回退模型</p><div v-else class="harness-detail-rows"><div v-for="item in modelFallbackChain" :key="item.model_id" class="harness-detail-row"><span><strong>{{ item.name }}</strong> · {{ item.provider || '未指定提供商' }}</span><code>{{ item.model_id }}</code></div></div></div>
          <label class="run-create-field"><span>模型名称</span><input v-model="modelDraft.name" required maxlength="160" :disabled="modelSaving" /></label>
          <label class="run-create-field"><span>提供商标识</span><input v-model="modelDraft.provider" maxlength="160" :disabled="modelSaving" /></label>
          <label class="run-create-field"><span>路由用途</span><input v-model="modelDraft.route" required maxlength="160" :disabled="modelSaving" /></label>
          <label class="run-create-field"><span>备用模型</span><select v-model="modelDraft.fallback_model_id" :disabled="modelSaving"><option :value="null">无</option><option v-for="item in harnessModels.filter(row => row.model_id !== editingModel?.model_id)" :key="item.model_id" :value="item.model_id">{{ item.name }} · {{ item.model_id }}</option></select></label>
          <label class="run-create-field"><span>登记状态</span><input v-model="modelDraft.status" required maxlength="40" :disabled="modelSaving" /></label>
          <label class="run-create-field"><span>成本策略说明</span><textarea v-model="modelDraft.cost_policy" rows="4" maxlength="2000" :disabled="modelSaving"></textarea></label>
          <p v-if="modelError" role="alert">{{ modelError }}</p>
          <div class="dialog-actions"><button class="secondary-button" type="button" :disabled="modelSaving" @click="showModelDialog = false">取消</button><button class="primary-button" type="submit" :disabled="modelSaving">{{ modelSaving ? '保存中…' : '保存登记配置' }}</button></div>
        </form>
      </div>
      <div v-if="showToolDialog" class="modal-backdrop" @click.self="!toolSaving && (showToolDialog = false)">
        <form class="dialog run-create-dialog" role="dialog" aria-modal="true" aria-labelledby="tool-editor-title" @submit.prevent="saveTool">
          <div class="dialog-heading"><div class="dialog-symbol"><Wrench :size="19" /></div><button class="icon-button" type="button" :disabled="toolSaving" aria-label="关闭工具配置" @click="showToolDialog = false"><X :size="18" /></button></div>
          <h2 id="tool-editor-title">{{ editingTool ? '工具详情与编辑' : '登记工具' }}</h2>
          <p v-if="editingTool">{{ editingTool.tool_id }} · 修订 {{ editingTool.revision }} · 更新时间 {{ editingTool.updated_at }}</p>
          <label class="run-create-field"><span>工具名称</span><input v-model="toolDraft.name" required maxlength="160" :disabled="toolSaving" /></label>
          <label class="run-create-field"><span>来源标识</span><input v-model="toolDraft.source" required maxlength="160" :disabled="toolSaving" /></label>
          <label class="run-create-field"><span>权限范围</span><input v-model="toolDraft.scope" required maxlength="500" :disabled="toolSaving" /></label>
          <label class="run-create-field"><span>风险等级</span><select v-model="toolDraft.risk" :disabled="toolSaving"><option value="low">低</option><option value="medium">中</option><option value="high">高</option></select></label>
          <label class="run-create-field"><span>审批策略</span><select v-model="toolDraft.approval_policy" :disabled="toolSaving"><option value="risk-based">按风险等级审批</option><option value="always">每次调用审批</option></select></label>
          <label class="run-create-field"><span>登记状态</span><input v-model="toolDraft.status" required maxlength="40" :disabled="toolSaving" /></label>
          <label class="run-create-field"><span>说明</span><textarea v-model="toolDraft.description" rows="2" maxlength="2000" :disabled="toolSaving"></textarea></label>
          <label class="run-create-field"><span>参数 Schema JSON</span><textarea v-model="toolSchemaText" rows="6" spellcheck="false" :disabled="toolSaving"></textarea></label>
          <p v-if="toolError" role="alert">{{ toolError }}</p>
          <div class="dialog-actions"><button class="secondary-button" type="button" :disabled="toolSaving" @click="showToolDialog = false">取消</button><button class="primary-button" type="submit" :disabled="toolSaving">{{ toolSaving ? '保存中…' : '保存登记配置' }}</button></div>
        </form>
      </div>
      <div v-if="showAgentDialog" class="modal-backdrop" @click.self="!agentSaving && (showAgentDialog = false)">
        <form class="dialog run-create-dialog" role="dialog" aria-modal="true" aria-labelledby="agent-create-title" @submit.prevent="submitAgent">
          <div class="dialog-heading"><div class="dialog-symbol"><Bot :size="19" /></div><button class="icon-button" type="button" aria-label="关闭 Agent 配置" :disabled="agentSaving" @click="showAgentDialog = false"><X :size="18" /></button></div>
          <h2 id="agent-create-title">{{ editingAgent ? 'Agent 详情与编辑' : '新建 Agent' }}</h2>
          <p v-if="editingAgent">{{ editingAgent.agent_id }} · 状态 {{ editingAgent.status }} · 修订 {{ editingAgent.revision }} · 更新时间 {{ editingAgent.updated_at }}</p>
          <label class="run-create-field"><span>名称</span><input v-model="agentDraft.name" required maxlength="120" :disabled="agentSaving" /></label>
          <label class="run-create-field"><span>版本标签</span><input v-model="agentDraft.version" required maxlength="40" :disabled="agentSaving" /></label>
          <label class="run-create-field"><span>模型路由</span><input v-model="agentDraft.model" required maxlength="120" :disabled="agentSaving" /></label>
          <label class="run-create-field"><span>说明</span><textarea v-model="agentDraft.description" rows="3" maxlength="500" :disabled="agentSaving"></textarea></label>
          <label class="run-create-field"><span>运行策略 JSON</span><textarea v-model="agentPolicyText" rows="5" spellcheck="false" :disabled="agentSaving"></textarea></label>
          <template v-if="editingAgent">
            <div class="harness-detail-block"><strong>版本历史</strong><p v-if="agentVersionsBusy" role="status">正在读取版本历史…</p><div v-else-if="agentVersions.length" class="harness-detail-rows"><div v-for="item in agentVersions" :key="item.version_id" class="harness-detail-row"><span><strong>{{ item.version }}</strong> · {{ item.enabled ? '启用' : '停用' }} · {{ item.created_at }}</span><code>{{ item.version_id }}</code></div></div><div v-else class="release-empty"><span>暂无版本快照</span></div><div class="harness-detail-actions"><select v-model="agentDiffBase" :disabled="agentDiffBusy"><option value="">基准版本</option><option v-for="item in agentVersions" :key="item.version_id" :value="item.version_id">{{ item.version }} · {{ item.created_at }}</option></select><select v-model="agentDiffTarget" :disabled="agentDiffBusy"><option value="">对比版本</option><option v-for="item in agentVersions" :key="item.version_id" :value="item.version_id">{{ item.version }} · {{ item.created_at }}</option></select><button class="button button-subtle" type="button" :disabled="agentDiffBusy || !agentDiffBase || !agentDiffTarget" @click="compareAgentVersions">{{ agentDiffBusy ? '比较中…' : '对比版本' }}</button></div><p v-if="agentDiffError" role="alert">{{ agentDiffError }}</p><div v-if="agentDiff" class="harness-detail-rows"><div v-for="item in agentDiff.changed" :key="`changed-${item.field}`" class="harness-detail-row"><span>{{ item.field }}</span><span>{{ formatDiffValue(item.base) }} → {{ formatDiffValue(item.target) }}</span></div><div v-for="item in agentDiff.added" :key="`added-${item.field}-${item.value}`" class="harness-detail-row"><span>新增 {{ item.field }}</span><span>{{ formatDiffValue(item.value) }}</span></div><div v-for="item in agentDiff.removed" :key="`removed-${item.field}-${item.value}`" class="harness-detail-row"><span>移除 {{ item.field }}</span><span>{{ formatDiffValue(item.value) }}</span></div><div v-if="!agentDiff.changed.length && !agentDiff.added.length && !agentDiff.removed.length" class="release-empty"><span>两个版本没有差异</span></div></div></div>
            <div class="harness-detail-block"><strong>绑定 Skill</strong><div class="harness-detail-rows"><div v-for="skillId in editingAgent.skills || []" :key="skillId" class="harness-detail-row"><code>{{ skillId }}</code><button class="text-action" type="button" :disabled="agentSkillBusy" @click="unbindAgentSkill(skillId)">解绑</button></div><div v-if="!(editingAgent.skills || []).length" class="release-empty"><span>尚未绑定 Skill</span></div></div><div class="harness-detail-actions"><select v-model="agentSkillPick" :disabled="agentSkillBusy"><option value="">选择已安装 Skill</option><option v-for="item in harnessSkills" :key="item.id" :value="item.id">{{ item.name }} · {{ item.id }}</option></select><input v-model="agentSkillInput" placeholder="或手工输入 skillId" :disabled="agentSkillBusy" /><button class="button button-subtle" type="button" :disabled="agentSkillBusy || !pendingAgentSkillId" @click="bindAgentSkill">{{ agentSkillBusy ? '处理中…' : '绑定 Skill' }}</button></div><p v-if="agentSkillError" role="alert">{{ agentSkillError }}</p></div>
            <div class="harness-detail-block"><strong>关联运行</strong><p v-if="agentRunsBusy" role="status">正在读取关联运行…</p><div v-else-if="agentRuns.length" class="harness-detail-rows"><div v-for="item in agentRuns" :key="item.run_id" class="harness-detail-row"><span><strong>{{ item.run_id }}</strong> · {{ item.status }}</span><span>{{ item.query || '无任务' }} · {{ item.created_at || '—' }}</span></div></div><div v-else class="release-empty"><span>暂无关联运行</span></div><p v-if="agentRunsError" role="alert">{{ agentRunsError }}</p></div>
          </template>
          <p v-if="agentError" role="alert">{{ agentError }}</p>
          <div class="dialog-actions"><button class="secondary-button" type="button" :disabled="agentSaving" @click="showAgentDialog = false">取消</button><button class="primary-button" type="submit" :disabled="agentSaving">{{ agentSaving ? '保存中…' : editingAgent ? '保存配置' : '创建 Agent' }}</button></div>
        </form>
      </div>
      <div v-if="showWorkspaceDialog" class="modal-backdrop" @click.self="!workspaceSaving && (showWorkspaceDialog = false)">
        <form class="dialog run-create-dialog" role="dialog" aria-modal="true" aria-labelledby="workspace-create-title" @submit.prevent="submitWorkspace">
          <div class="dialog-heading"><div class="dialog-symbol"><Layers3 :size="19" /></div><button class="icon-button" type="button" aria-label="关闭工作空间配置" :disabled="workspaceSaving" @click="showWorkspaceDialog = false"><X :size="18" /></button></div>
          <h2 id="workspace-create-title">{{ editingWorkspace ? '工作空间详情与编辑' : '新建工作空间' }}</h2>
          <p v-if="editingWorkspace">{{ editingWorkspace.workspace_id }} · 状态 {{ editingWorkspace.status }} · 修订 {{ editingWorkspace.revision }} · 更新时间 {{ editingWorkspace.updated_at }}</p>
          <label class="run-create-field"><span>名称</span><input v-model="workspaceDraft.name" required maxlength="120" :disabled="workspaceSaving" /></label>
          <label class="run-create-field"><span>仓库标识</span><input v-model="workspaceDraft.repository" maxlength="500" :disabled="workspaceSaving" /></label>
          <label class="run-create-field"><span>分支</span><input v-model="workspaceDraft.branch" required maxlength="200" :disabled="workspaceSaving" /></label>
          <template v-if="editingWorkspace">
            <div class="harness-detail-block"><strong>仓库检出</strong><div class="harness-detail-actions"><button class="button button-subtle" type="button" :disabled="checkoutBusy" @click="runWorkspaceCheckout">{{ checkoutBusy ? '检出中…' : '检出仓库' }}</button></div><p v-if="checkoutError" role="alert">{{ checkoutError }}</p><div v-if="workspaceCheckout" class="harness-detail-rows"><div class="harness-detail-row"><span>分支 / 提交</span><span>{{ workspaceCheckout.branch || '—' }} · {{ workspaceCheckout.commit ? workspaceCheckout.commit.slice(0, 8) : '—' }}</span></div><div class="harness-detail-row"><span>检出目录</span><code>{{ workspaceCheckout.checkoutDir || '—' }}</code></div><div class="harness-detail-row"><span>检出时间</span><span>{{ workspaceCheckout.checkedAt || '—' }}</span></div></div></div>
            <div class="harness-detail-block"><strong>仓库快照</strong><div class="harness-detail-actions"><button class="button button-subtle" type="button" :disabled="workspaceSnapshotBusy" @click="createWorkspaceSnapshot">{{ workspaceSnapshotBusy ? '创建中…' : '创建快照' }}</button></div><p v-if="workspaceSnapshotError" role="alert">{{ workspaceSnapshotError }}</p><div v-if="workspaceSnapshots.length" class="harness-detail-rows"><div v-for="item in workspaceSnapshots" :key="item.snapshot_id" class="harness-detail-row"><span><strong>{{ item.branch || '未记录分支' }}</strong> · {{ item.file_count }} 个文件 · {{ item.size_bytes }} 字节</span><code>{{ item.snapshot_id }} · {{ item.created_at }}</code></div></div><div v-else class="release-empty"><span>暂无快照</span></div></div>
            <div class="harness-detail-block"><strong>文件变更</strong><div class="harness-detail-actions"><select v-model="workspaceSelectedSnapshotId" @change="loadWorkspaceChanges(editingWorkspace.workspace_id, workspaceSelectedSnapshotId)"><option value="">选择快照</option><option v-for="item in workspaceSnapshots" :key="item.snapshot_id" :value="item.snapshot_id">{{ item.branch || '未记录分支' }} · {{ item.created_at }}</option></select></div><p v-if="workspaceChangesError" role="alert">{{ workspaceChangesError }}</p><div v-if="workspaceChanges.length" class="harness-detail-rows"><div v-for="item in workspaceChanges" :key="item.change_id" class="harness-detail-row"><code>{{ item.path }}</code><span>{{ item.change_type }}</span></div></div><div v-else class="release-empty"><span>该快照没有文件变更记录</span></div></div>
            <div class="harness-detail-block"><strong>关联运行</strong><div v-if="workspaceRuns.length" class="harness-detail-rows"><div v-for="item in workspaceRuns" :key="item.run_id" class="harness-detail-row"><span><strong>{{ item.run_id }}</strong> · {{ item.status }}</span><span>{{ item.query || '无任务' }} · {{ item.created_at || '—' }}</span></div></div><div v-else class="release-empty"><span>暂无关联运行</span></div><p v-if="workspaceRunsError" role="alert">{{ workspaceRunsError }}</p></div>
          </template>
          <p v-if="workspaceError" role="alert">{{ workspaceError }}</p>
          <div class="dialog-actions"><button class="secondary-button" type="button" :disabled="workspaceSaving" @click="showWorkspaceDialog = false">取消</button><button class="primary-button" type="submit" :disabled="workspaceSaving">{{ workspaceSaving ? '保存中…' : editingWorkspace ? '保存登记信息' : '创建工作空间' }}</button></div>
        </form>
      </div>
      <div v-if="selectedEvaluationDataset" class="modal-backdrop" @click.self="selectedEvaluationDataset = null"><section class="dialog dataset-detail-dialog" role="dialog" aria-modal="true" aria-labelledby="dataset-detail-title"><div class="dialog-heading"><div class="dialog-symbol"><Gauge :size="19" /></div><button class="icon-button" type="button" aria-label="关闭测评集详情" @click="selectedEvaluationDataset = null"><X :size="18" /></button></div><h2 id="dataset-detail-title">{{ selectedEvaluationDataset.name }}</h2><p>{{ selectedEvaluationDataset.description || '维护输入、期望结果和评分规则。' }} · {{ selectedEvaluationDataset.case_count }} 条样本</p><div class="dataset-detail-toolbar"><strong>样本列表</strong><div class="dataset-detail-actions"><button class="button button-subtle" @click="openImportCasesDialog"><ArrowDownToLine :size="14" />批量导入样本</button><button class="button button-subtle" :disabled="snapshotBusy" @click="saveDatasetSnapshot"><Archive :size="14" />{{ snapshotBusy ? '保存中…' : '保存版本快照' }}</button><button class="button button-subtle" @click="openCaseDialog()"><Plus :size="14" />新增样本</button></div></div><div class="dataset-case-list"><article v-for="item in selectedEvaluationDataset.cases" :key="item.case_id" class="dataset-case-row"><div><strong>{{ item.case_id }}</strong><p>{{ item.input_text }}</p><small>期望输出：{{ item.expected_output || '未设置' }}</small></div><div class="dataset-case-actions"><button class="text-action" @click="openCaseDialog(item)">编辑</button><button v-if="item.case_id" class="text-action danger" @click="deleteDatasetCase(item)">删除</button></div></article><div v-if="!selectedEvaluationDataset.cases.length" class="release-empty"><span>暂无样本</span></div></div><div class="dataset-snapshot-list"><strong>版本快照</strong><div v-if="evalSnapshots.length" class="release-history-list"><div v-for="item in evalSnapshots" :key="item.snapshot_id" class="release-history-row"><span>{{ item.created_at || '—' }}</span><strong>v{{ item.version }}</strong><span>{{ item.payload?.name || selectedEvaluationDataset.name }}</span><b>{{ item.payload?.case_count ?? 0 }} 条样本</b><code>{{ item.snapshot_id }}</code></div></div><div v-else class="release-empty"><span>暂无版本快照</span><small>保存快照后可回溯测评集版本</small></div></div><div class="dialog-actions"><button class="secondary-button" type="button" @click="selectedEvaluationDataset = null">关闭</button></div></section></div>
      <div v-if="showCaseDialog" class="modal-backdrop" @click.self="showCaseDialog = false"><section class="dialog run-create-dialog" role="dialog" aria-modal="true" aria-labelledby="case-create-title"><div class="dialog-heading"><div class="dialog-symbol"><FileText :size="19" /></div><button class="icon-button" type="button" aria-label="关闭样本编辑" @click="showCaseDialog = false"><X :size="18" /></button></div><h2 id="case-create-title">{{ caseDraft.caseId ? '编辑测评样本' : '新增测评样本' }}</h2><label class="run-create-field"><span>测试输入</span><textarea v-model="caseDraft.input" rows="4" placeholder="输入要回放的问题或任务" autofocus></textarea></label><label class="run-create-field"><span>期望输出</span><textarea v-model="caseDraft.expectedOutput" rows="3" placeholder="可选，填写期望结果"></textarea></label><label class="run-create-field"><span>评分规则 JSON</span><textarea v-model="caseDraft.rubric" rows="4" spellcheck="false"></textarea></label><div class="dialog-actions"><button class="secondary-button" type="button" @click="showCaseDialog = false">取消</button><button class="primary-button" type="button" @click="saveCase">保存样本</button></div></section></div>
      <div v-if="showImportDialog" class="modal-backdrop" @click.self="showImportDialog = false"><section class="dialog run-create-dialog" role="dialog" aria-modal="true" aria-labelledby="import-cases-title"><div class="dialog-heading"><div class="dialog-symbol"><FileText :size="19" /></div><button class="icon-button" type="button" aria-label="关闭批量导入" @click="showImportDialog = false"><X :size="18" /></button></div><h2 id="import-cases-title">批量导入样本</h2><p>粘贴 JSON 数组，每项必须包含非空的 input 字段，可选 expectedOutput 和 rubric。</p><label class="run-create-field"><span>样本数组 JSON</span><textarea v-model="importCasesText" rows="10" spellcheck="false" placeholder='[{"input":"问题","expectedOutput":"期望","rubric":{}}]'></textarea></label><div class="dialog-actions"><button class="secondary-button" type="button" @click="showImportDialog = false">取消</button><button class="primary-button" type="button" :disabled="importBusy" @click="submitImportCases">{{ importBusy ? '导入中…' : '开始导入' }}</button></div></section></div>
      <div v-if="showDatasetDialog" class="modal-backdrop" @click.self="showDatasetDialog = false"><section class="dialog run-create-dialog" role="dialog" aria-modal="true" aria-labelledby="dataset-create-title"><div class="dialog-heading"><div class="dialog-symbol"><Gauge :size="19" /></div><button class="icon-button" type="button" aria-label="关闭新建测评集" @click="showDatasetDialog = false"><X :size="18" /></button></div><h2 id="dataset-create-title">新建测评集</h2><p>测评集只保存测试输入、期望结果和评分规则，不会创建执行任务。</p><label class="run-create-field"><span>测评集名称</span><input v-model="datasetDraft.name" placeholder="例如：客服全链路回归集" autofocus /></label><label class="run-create-field"><span>类型</span><select v-model="datasetDraft.datasetType"><option>通用</option><option>端到端</option><option>RAG</option><option>Tool calling</option><option>Memory</option></select></label><label class="run-create-field"><span>说明</span><textarea v-model="datasetDraft.description" rows="3" placeholder="描述测评集覆盖的能力范围"></textarea></label><div class="dialog-actions"><button class="secondary-button" type="button" @click="showDatasetDialog = false">取消</button><button class="primary-button" type="button" @click="submitDataset">创建测评集</button></div></section></div>
      <div v-if="showRunDialog" class="modal-backdrop" @click.self="showRunDialog = false"><section class="dialog run-create-dialog" role="dialog" aria-modal="true" aria-labelledby="run-create-title"><div class="dialog-heading"><div class="dialog-symbol"><Play :size="19" /></div><button class="icon-button" type="button" aria-label="关闭新建运行" @click="showRunDialog = false"><X :size="18" /></button></div><h2 id="run-create-title">新建执行任务</h2><p>提交一个独立的 Agent 运行。运行创建后只在“执行任务”页面管理。</p><label class="run-create-field"><span>执行模式</span><select v-model="runDraft.agent"><option value="chat">对话助手</option><option value="file">文件问答</option><option value="ppt">PPT 生成</option><option value="deep">深度研究</option><option value="skills">技能助手</option></select></label><label class="run-create-field"><span>任务内容</span><textarea v-model="runDraft.query" rows="5" placeholder="描述要执行的任务" autofocus></textarea></label><label class="run-create-field"><span>会话编号</span><input v-model="runDraft.conversationId" placeholder="可选，默认自动生成" /></label><label v-if="runDraft.agent === 'file' || runDraft.agent === 'skills'" class="run-create-field"><span>文件编号</span><input v-model="runDraft.fileId" placeholder="填写已上传文件或文档的 fileId" /></label><label class="run-create-field"><span>关联 Agent</span><select v-model="runDraft.agentId"><option value="">不关联</option><option v-for="item in harnessAgents" :key="item.agent_id" :value="item.agent_id">{{ item.name }}{{ item.enabled ? '' : '（已停用）' }}</option></select></label><label class="run-create-field"><span>关联工作空间</span><select v-model="runDraft.workspaceId"><option value="">不关联</option><option v-for="item in harnessWorkspaces" :key="item.workspace_id" :value="item.workspace_id">{{ item.name }} · {{ item.branch }}</option></select></label><div class="dialog-actions"><button class="secondary-button" type="button" @click="showRunDialog = false">取消</button><button class="primary-button" type="button" :disabled="runSubmitBusy" @click="submitRun">{{ runSubmitBusy ? '提交中…' : '提交运行' }}</button></div></section></div>
      <div v-if="evalRunDetail" class="modal-backdrop" @click.self="evalRunDetail = null">
        <section class="dialog dataset-detail-dialog" role="dialog" aria-modal="true" aria-labelledby="eval-run-detail-title">
          <div class="dialog-heading"><div class="dialog-symbol"><Gauge :size="19" /></div><button class="icon-button" type="button" aria-label="关闭测评运行详情" @click="evalRunDetail = null"><X :size="18" /></button></div>
          <h2 id="eval-run-detail-title">{{ evalRunDetail.eval_run_id }}</h2>
          <p>{{ evalStatusLabel(evalRunDetail.status) }} · {{ evalRunDetail.created_at || '—' }} · 测评集 {{ evalRunDetail.dataset_id || '—' }} · 代理 {{ evalRunDetail.agent || '—' }}</p>
          <p v-if="evalRunDetail.error" role="alert">{{ evalRunDetail.error }}</p>
          <p v-if="evalRunDetail.summary">通过率 {{ evalPassRateText }} · 通过 {{ evalRunDetail.summary.passedCount }} / 样本 {{ evalRunDetail.summary.caseCount }}</p>
          <div class="dataset-detail-toolbar"><strong>样本级结果</strong></div>
          <div class="dataset-case-list">
            <article v-for="item in evalRunCases" :key="item.result_id" class="dataset-case-row">
              <div><strong>{{ item.case_id }} · {{ evalVerdictLabel(item.verdict) }} · 得分 {{ item.score }}</strong><p>输入：{{ evalCaseInput(item.case_id) }}</p><small>期望输出：{{ evalCaseExpected(item.case_id) }}<br>实际输出：{{ item.actual_output || '无输出' }}<br>判定说明：{{ item.detail || '无' }}</small></div>
              <button v-if="item.verdict === 'failed' || item.verdict === 'timeout'" class="text-action" type="button" :disabled="evalRunBusy" @click="replayEvalCase(evalRunDetail.eval_run_id, item.case_id)">回放</button>
            </article>
            <div v-if="!evalRunCases.length" class="release-empty"><span>该测评运行没有样本结果</span></div>
          </div>
          <div class="dialog-actions"><button class="secondary-button" type="button" @click="evalRunDetail = null">关闭</button></div>
        </section>
      </div>
      <div v-if="approvalDetail" class="modal-backdrop" @click.self="approvalDetail = null">
        <section class="dialog run-create-dialog" role="dialog" aria-modal="true" aria-labelledby="approval-detail-title">
          <div class="dialog-heading"><div class="dialog-symbol"><ShieldCheck :size="19" /></div><button class="icon-button" type="button" aria-label="关闭审批详情" @click="approvalDetail = null"><X :size="18" /></button></div>
          <h2 id="approval-detail-title">{{ approvalDetail.request_id }}</h2>
          <p>工具 {{ approvalDetail.tool }} · 风险 {{ approvalDetail.risk }} · 状态 {{ approvalDetail.status }}</p>
          <p>运行 {{ approvalDetail.run_id }} · 创建 {{ approvalDetail.created_at || '—' }} · 超时 {{ approvalDetail.expires_at || '—' }}</p>
          <p>{{ approvalDetail.detail || '无补充说明' }}</p>
          <p v-if="approvalDetail.decided_at">决定于 {{ approvalDetail.decided_at }} · 操作者 {{ approvalDetail.operator || '—' }} · 理由 {{ approvalDetail.reason || '—' }}</p>
          <div class="dialog-actions"><button class="secondary-button" type="button" @click="approvalDetail = null">关闭</button><button v-if="approvalDetail.status === 'pending'" class="primary-button" type="button" :disabled="approvalBusy" @click="decideApproval(approvalDetail, 'approved'); approvalDetail = null">批准</button><button v-if="approvalDetail.status === 'pending'" class="secondary-button" type="button" @click="openRejectDialog(approvalDetail); approvalDetail = null">拒绝</button></div>
        </section>
      </div>
      <div v-if="rejectDialog" class="modal-backdrop" @click.self="rejectDialog = null">
        <section class="dialog run-create-dialog" role="dialog" aria-modal="true" aria-labelledby="reject-approval-title">
          <div class="dialog-heading"><div class="dialog-symbol"><ShieldCheck :size="19" /></div><button class="icon-button" type="button" aria-label="关闭拒绝理由" @click="rejectDialog = null"><X :size="18" /></button></div>
          <h2 id="reject-approval-title">拒绝审批</h2>
          <p>{{ rejectDialog.request_id }} · {{ rejectDialog.tool }}</p>
          <label class="run-create-field"><span>拒绝理由</span><textarea v-model="rejectReason" rows="3" placeholder="说明拒绝原因，会写入审计记录"></textarea></label>
          <div class="dialog-actions"><button class="secondary-button" type="button" @click="rejectDialog = null">取消</button><button class="primary-button" type="button" @click="submitRejectApproval">确认拒绝</button></div>
        </section>
      </div>
      <div v-if="toast" class="toast-message"><Check :size="15" />{{ toast }}</div>
    </main>
  </div>
</template>
