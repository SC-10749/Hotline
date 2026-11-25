<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ChevronRight, CircleCheck, CircleX, Play, RefreshCw } from 'lucide-vue-next'
import {
  checkEvaluationGates,
  createEvaluationRun,
  getEvaluationConfig,
  getEvaluationDataset,
  getEvaluationDatasets,
  getEvaluationMatrix,
  getEvaluationRun,
  getEvaluationRuns,
  getEvaluationTrace,
} from '../../api'
import { MATRIX_RUN_LIMIT, matrixCellText, matrixChangeLabel, matrixRunSelection } from './matrix'
import { failureKindLabel, runOptionLabel } from './readability'

const METRIC_LABELS = {
  topic_adherence: '话题贴合度',
  answer_relevance: '回答相关性',
  fact_consistency: '事实一致性',
  trajectory_quality: '轨迹质量',
}

const props = defineProps({ apiBase: { type: String, default: '' } })

const AGENTS = [
  { value: 'chat', label: '对话助手' },
  { value: 'skills', label: '技能助手' },
  { value: 'requirement', label: '需求助手' },
]
const VERDICTS = {
  passed: '通过',
  failed: '失败',
  timeout: '超时',
  skipped: '已跳过',
  not_scored: '未评分',
  invalid_rubric: '规则无效',
  scorer_unavailable: '评分器不可用',
}
const EVENT_TYPES = {
  text: '文本',
  step: '步骤',
  tool_start: '工具开始',
  tool_end: '工具结束',
  clarify: '澄清',
  usage: '用量',
  error: '错误',
  context_snapshot: '上下文快照',
}
const LEVELS = { info: '信息', warn: '警告', error: '错误' }
const RATE_METRICS = ['passRate', 'passAtK', 'flakyRate']
const TERMINAL_STATUS = ['completed', 'failed', 'cancelled', 'blocked']

const datasets = ref([])
const runs = ref([])
const matrixRunIds = ref([])
const matrix = ref(null)
const matrixBusy = ref(false)
const matrixError = ref('')
const selectedRunId = ref('')
const currentRun = ref(null)
const results = ref([])
const summary = ref({})
const selectedResult = ref(null)
const trace = ref(null)
const gates = ref([])
const gateReport = ref(null)
const datasetId = ref('')
const agent = ref('chat')
const epochs = ref(1)
const concurrency = ref(1)
const budgetTokens = ref(0)
const budgetSeconds = ref(0)
const budgetSamples = ref(0)
const pricePerMTok = ref(0)
const baselineRunId = ref('')
const busy = ref(false)
const running = ref(false)
const traceBusy = ref(false)
const gateBusy = ref(false)
const connected = ref(true)
const error = ref('')
const traceError = ref('')
const gateError = ref('')
let pollTimer = null
let disposed = false

const numberOrNull = (value) => {
  if (value === null || value === undefined || value === '') return null
  const num = Number(value)
  return Number.isFinite(num) ? num : null
}
const percentText = (value) => {
  const num = numberOrNull(value)
  if (num === null) return '—'
  return `${(num <= 1 ? num * 100 : num).toFixed(1)}%`
}
const formatMetric = (metric, value) => {
  const num = numberOrNull(value)
  if (num === null) return '—'
  return RATE_METRICS.includes(metric) ? percentText(num) : String(num)
}
const traceCount = (row, key) => {
  const num = numberOrNull(row?.trace?.counts?.[key])
  return num === null ? '—' : num
}
const traceNumber = (row, key) => {
  const num = numberOrNull(row?.trace?.[key])
  return num === null ? '—' : num
}
const metricRows = (row) => {
  const metrics = row?.metrics
  if (!metrics || typeof metrics !== 'object') return []
  return Object.entries(metrics).map(([metric, item]) => ({
    metric,
    label: item?.label || METRIC_LABELS[metric] || metric,
    score: numberOrNull(item?.score),
    detail: item?.detail || '',
    judge: item?.judge || '',
  }))
}
const asList = (payload, ...keys) => {
  if (Array.isArray(payload)) return payload
  for (const key of keys) if (Array.isArray(payload?.[key])) return payload[key]
  return []
}

const kpis = computed(() => {
  const source = summary.value || {}
  const flaky = numberOrNull(source.flakyRate)
  return [
    { label: '通过率', value: percentText(source.passRate), warn: false },
    { label: '全对率', value: percentText(source.passAtK), warn: false },
    { label: '不稳定率', value: percentText(source.flakyRate), warn: flaky !== null && flaky >= 0.1 },
    {
      label: '平均耗时',
      value: numberOrNull(source.avgLatencyMs) === null ? '—' : `${Math.round(numberOrNull(source.avgLatencyMs))} ms`,
      warn: false,
    },
    {
      label: '平均轮数',
      value: numberOrNull(source.avgTurns) === null ? '—' : numberOrNull(source.avgTurns).toFixed(1),
      warn: false,
    },
    {
      label: '预算消耗',
      value: numberOrNull(source.tokensUsed) === null
        ? '—'
        : `${Math.round(numberOrNull(source.tokensUsed))} / ${numberOrNull(source.budgetTokens) || '不限'}`,
      warn: Boolean(source.budgetExhausted),
      note: '预算或时限已用尽',
    },
    {
      label: '跳过样本',
      value: numberOrNull(source.skippedCount) === null ? '—' : String(numberOrNull(source.skippedCount)),
      warn: numberOrNull(source.skippedCount) > 0,
      note: '未执行',
    },
  ]
})

const budgetNote = computed(() => {
  const source = summary.value || {}
  if (!source.budgetExhausted) return ''
  const cost = numberOrNull(source.estimatedCostUsd)
  const parts = [`预算用尽，${numberOrNull(source.skippedCount) ?? 0} 个样本未执行`]
  if (cost !== null && cost > 0) parts.push(`估算成本 $${cost.toFixed(4)}`)
  return parts.join(' · ')
})

const failureRows = computed(() => {
  const source = summary.value?.failureKinds || {}
  const entries = Object.entries(source).filter(([, count]) => numberOrNull(count) !== null)
  const max = Math.max(1, ...entries.map(([, count]) => numberOrNull(count)))
  return entries.map(([kind, count]) => ({
    kind,
    label: failureKindLabel(kind),
    count: numberOrNull(count),
    width: Math.round((numberOrNull(count) / max) * 100),
  }))
})

const gateChecks = computed(() => {
  const report = gateReport.value || {}
  return asList(report, 'checks')
})

const traceEvents = computed(() => asList(trace.value, 'events'))

const matrixRuns = computed(() => matrix.value?.runs || [])
const matrixRows = computed(() => matrix.value?.rows || [])
const matrixCellClass = (cell) => {
  if (!cell?.verdict) return 'empty'
  if (cell.verdict === 'passed') return 'passed'
  if (cell.verdict === 'flaky') return 'flaky'
  return 'failed'
}
const matrixHeaderRuns = computed(() => matrixRuns.value.map((run) => ({
  ...run,
  coverageText: percentText(run.coverage),
  passRateText: percentText(run.passRate),
})))

const datasetNames = computed(() => {
  const names = {}
  for (const item of datasets.value || []) names[item.dataset_id] = item.name
  return names
})

const datasetCases = ref({})

async function loadDatasetCases(datasetId) {
  if (!datasetId || datasetCases.value[datasetId]) return
  try {
    const payload = await getEvaluationDataset(props.apiBase, datasetId)
    const cases = payload?.dataset?.cases || []
    datasetCases.value = { ...datasetCases.value, [datasetId]: Object.fromEntries(cases.map(item => [item.case_id, item])) }
  } catch {
    // 样本详情取不到就不展示期望，不影响其它阅读。
  }
}

const provenanceRows = computed(() => {
  const source = currentRun.value?.provenance || {}
  const rows = []
  if (source.model) rows.push({ label: '模型', value: source.model })
  if (source.commit) rows.push({ label: '代码提交', value: String(source.commit).slice(0, 7) })
  if (source.datasetVersion) rows.push({ label: '测评集版本', value: `v${source.datasetVersion}` })
  if (source.epochs) rows.push({ label: '重复轮数', value: String(source.epochs) })
  const skills = Object.entries(source.skills || {})
  if (skills.length) rows.push({ label: '技能摘要', value: skills.map(([name, sha]) => `${name}:${sha}`).join('  ') })
  return rows
})

const selectedCase = computed(() => {
  const caseId = selectedResult.value?.case_id
  if (!caseId) return null
  const cases = datasetCases.value[currentRun.value?.dataset_id || ''] || {}
  return cases[caseId] || null
})

const expectationText = computed(() => {
  const item = selectedCase.value
  if (!item) return ''
  const rubric = item.rubric && typeof item.rubric === 'object'
    ? JSON.stringify(item.rubric, null, 2)
    : String(item.rubric || '')
  const parts = []
  if (item.expected_output) parts.push(`期望输出：${item.expected_output}`)
  if (rubric && rubric !== '{}') parts.push(`评分规则：${rubric}`)
  return parts.join('\n') || '该样本没有登记期望输出与评分规则'
})

async function openMatrixCell(row, cell) {
  if (!cell?.runId) return
  if (selectedRunId.value !== cell.runId) await selectRun(cell.runId)
  const target = results.value.find(item => item.case_id === row.caseId)
  if (!target) {
    error.value = '这次运行里没有这个样本的结果'
    return
  }
  await openTrace(target)
}

function toggleMatrixRun(runId) {
  matrixRunIds.value = matrixRunSelection(matrixRunIds.value, runId)
}

async function loadMatrix() {
  if (matrixRunIds.value.length < 2) {
    matrixError.value = '矩阵至少需要勾选两个测评运行'
    return
  }
  matrixBusy.value = true
  matrixError.value = ''
  try {
    matrix.value = await getEvaluationMatrix(props.apiBase, matrixRunIds.value)
  } catch (cause) {
    matrix.value = null
    matrixError.value = cause.message || '读取评测矩阵失败'
  } finally {
    matrixBusy.value = false
  }
}

const traceTranscript = computed(() => {
  const items = asList(trace.value, 'transcript')
  return items.map(item => {
    if (typeof item === 'string') return item
    if (item && typeof item === 'object') return String(item.text ?? item.content ?? item.output ?? '')
    return String(item ?? '')
  })
})

function applyRunPayload(payload) {
  const run = payload?.run || payload || null
  currentRun.value = run
  summary.value = run?.summary || {}
  const rows = asList(payload, 'results')
  results.value = rows.length ? rows : asList(run, 'results')
  loadDatasetCases(run?.dataset_id)
}

async function loadDatasets() {
  const payload = await getEvaluationDatasets(props.apiBase)
  const list = asList(payload, 'items', 'datasets')
  datasets.value = list
  if (!datasetId.value && list.length) datasetId.value = list[0].dataset_id
}

async function loadRuns() {
  const payload = await getEvaluationRuns(props.apiBase)
  const list = asList(payload, 'items', 'runs')
  runs.value = list
  if (!selectedRunId.value && list.length) await selectRun(list[0].eval_run_id)
}

async function loadGates() {
  const payload = await getEvaluationConfig(props.apiBase)
  const config = payload?.config || payload || {}
  gates.value = asList(config, 'gates')
}

async function selectRun(runId) {
  if (!runId) return
  selectedRunId.value = runId
  selectedResult.value = null
  trace.value = null
  try {
    const payload = await getEvaluationRun(props.apiBase, runId)
    applyRunPayload(payload)
  } catch (cause) {
    error.value = cause.message || '读取测评运行失败'
  }
}

async function reloadCurrent() {
  if (!selectedRunId.value) return
  await selectRun(selectedRunId.value)
}

function stopPolling() {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = null
  running.value = false
}

async function pollRun(runId) {
  try {
    const payload = await getEvaluationRun(props.apiBase, runId)
    applyRunPayload(payload)
    if (TERMINAL_STATUS.includes(currentRun.value?.status)) {
      stopPolling()
      await loadRuns()
    }
  } catch (cause) {
    error.value = cause.message || '查询测评进度失败'
    stopPolling()
  }
}

async function startRun() {
  if (!datasetId.value) {
    error.value = '请先选择测评集'
    return
  }
  busy.value = true
  error.value = ''
  try {
    const payload = await createEvaluationRun(props.apiBase, {
      datasetId: datasetId.value,
      agent: agent.value,
      epochs: Math.min(10, Math.max(1, Number(epochs.value) || 1)),
      concurrency: Math.min(16, Math.max(1, Number(concurrency.value) || 1)),
      budgetTokens: Math.max(0, Number(budgetTokens.value) || 0),
      budgetSeconds: Math.max(0, Number(budgetSeconds.value) || 0),
      budgetSamples: Math.max(0, Number(budgetSamples.value) || 0),
      pricePerMTok: Math.max(0, Number(pricePerMTok.value) || 0),
    })
    const run = payload?.run || payload || null
    const runId = run?.eval_run_id
    if (!runId) throw new Error('测评服务未返回运行编号')
    selectedRunId.value = runId
    applyRunPayload(payload)
    selectedResult.value = null
    trace.value = null
    stopPolling()
    running.value = true
    pollTimer = setInterval(() => pollRun(runId), 2000)
  } catch (cause) {
    error.value = cause.message || '发起测评失败'
    running.value = false
  } finally {
    busy.value = false
  }
}

async function openTrace(row) {
  selectedResult.value = row
  trace.value = null
  traceError.value = ''
  traceBusy.value = true
  try {
    const payload = await getEvaluationTrace(props.apiBase, selectedRunId.value, row.case_id, row.epoch)
    trace.value = payload?.trace || payload || null
  } catch (cause) {
    traceError.value = cause.message || '读取轨迹失败'
  } finally {
    traceBusy.value = false
  }
}

async function checkGates() {
  if (!selectedRunId.value) {
    gateError.value = '请先选择测评运行'
    return
  }
  gateBusy.value = true
  gateError.value = ''
  try {
    const payload = { target: selectedRunId.value }
    const base = baselineRunId.value.trim()
    if (base) payload.base = base
    const report = await checkEvaluationGates(props.apiBase, payload)
    gateReport.value = report?.report || report || null
  } catch (cause) {
    gateError.value = cause.message || '门禁检查失败'
  } finally {
    gateBusy.value = false
  }
}

onMounted(async () => {
  const settled = await Promise.allSettled([loadDatasets(), loadRuns(), loadGates()])
  if (disposed) return
  connected.value = settled.every(item => item.status === 'fulfilled')
  const failure = settled.find(item => item.status === 'rejected')
  if (failure) error.value = failure.reason?.message || '未连接测评服务'
})

onUnmounted(() => {
  disposed = true
  stopPolling()
})
</script>

<template>
  <div class="eval-panel">
    <section class="harness-panel">
      <div class="harness-panel-heading">
        <div>
          <h3>发起测评</h3>
          <p>对 Agent 跑批，产出可断言的样本结果</p>
        </div>
        <button class="button button-subtle" type="button" @click="reloadCurrent"><RefreshCw :size="14" />刷新</button>
      </div>
      <div class="harness-detail-actions">
        <label class="eval-field">测评集
          <select v-model="datasetId">
            <option value="">请选择测评集</option>
            <option v-for="item in datasets" :key="item.dataset_id" :value="item.dataset_id">
              {{ item.name }} · {{ numberOrNull(item.case_count) ?? '—' }} 条样本
            </option>
          </select>
        </label>
        <label class="eval-field">Agent
          <select v-model="agent">
            <option v-for="item in AGENTS" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
        </label>
        <label class="eval-field">重复次数（稳定性）
          <input v-model.number="epochs" type="number" min="1" max="10" />
        </label>
        <label class="eval-field">并发度
          <input v-model.number="concurrency" type="number" min="1" max="16" />
        </label>
        <label class="eval-field">token 预算
          <input v-model.number="budgetTokens" type="number" min="0" placeholder="不限" />
        </label>
        <label class="eval-field">时限（秒）
          <input v-model.number="budgetSeconds" type="number" min="0" placeholder="不限" />
        </label>
        <label class="eval-field">样本上限
          <input v-model.number="budgetSamples" type="number" min="0" placeholder="不限" />
        </label>
        <label class="eval-field">单价 $/M token
          <input v-model.number="pricePerMTok" type="number" min="0" step="0.01" placeholder="不估算" />
        </label>
        <button class="button button-primary" type="button" :disabled="busy || running || !datasetId" @click="startRun">
          <Play :size="14" />{{ running ? '测评进行中…' : busy ? '发起中…' : '开始测评' }}
        </button>
        <span v-if="running" class="evaluation-progress">测评进行中，2 秒自动刷新一次</span>
      </div>
      <div class="harness-detail-actions">
        <label class="eval-field">历史运行
          <select :value="selectedRunId" @change="selectRun($event.target.value)">
            <option value="">暂无运行</option>
            <option v-for="item in runs" :key="item.eval_run_id" :value="item.eval_run_id">
              {{ runOptionLabel(item, datasetNames[item.dataset_id]) }}
            </option>
          </select>
        </label>
      </div>
      <p v-if="budgetNote" class="evaluation-progress" role="status">{{ budgetNote }}</p>
      <p v-if="error" class="eval-error" role="alert">{{ error }}</p>
    </section>

    <section v-if="!connected" class="harness-panel">
      <div class="ui-empty"><span>未连接测评服务</span><small>发起与结果读取需要后端测评接口可用</small></div>
    </section>

    <section class="evaluation-kpis">
      <div v-for="item in kpis" :key="item.label">
        <span>{{ item.label }}</span>
        <strong :class="{ 'stat-warn': item.warn }">{{ item.value }}</strong>
        <small v-if="item.warn">{{ item.note || '波动偏大，需关注' }}</small>
        <small v-else>{{ currentRun?.eval_run_id || '暂无运行' }}</small>
      </div>
    </section>

    <section v-if="provenanceRows.length" class="harness-panel">
      <div class="harness-panel-heading">
        <div>
          <h3>运行出处</h3>
          <p>这轮是在什么配置下跑出来的</p>
        </div>
      </div>
      <div class="eval-trace-summary">
        <span v-for="row in provenanceRows" :key="row.label">{{ row.label }} {{ row.value }}</span>
      </div>
    </section>

    <section class="harness-panel resource-table-panel">
      <div class="harness-panel-heading">
        <div>
          <h3>结果明细</h3>
          <p>{{ results.length }} 条样本结果 · 运行 {{ selectedRunId || '—' }}</p>
        </div>
      </div>
      <div v-if="results.length" class="ui-table ui-cols-eval-results">
        <div class="ui-table-head">
          <span>样本编号</span><span>重复轮次</span><span>判定</span><span>失败分类</span>
          <span>语义维度</span>
          <span>澄清轮次</span><span>工具错误</span><span>耗时(ms)</span><span>Tokens</span><span>操作</span>
        </div>
        <div v-for="row in results" :key="`${row.case_id}-${row.epoch}`" class="ui-row">
          <span><strong>{{ row.case_id || '—' }}</strong><small>{{ row.detail || '' }}</small></span>
          <span>{{ numberOrNull(row.epoch) ?? '—' }}</span>
          <span>{{ VERDICTS[row.verdict] || row.verdict || '—' }}</span>
          <span>{{ row.failure_kind ? failureKindLabel(row.failure_kind) : '—' }}</span>
          <span class="eval-metric-cell">
            <template v-if="metricRows(row).length">
              <small v-for="item in metricRows(row)" :key="item.metric" :title="`${item.detail}（评委 ${item.judge}）`">
                {{ item.label }} {{ item.score === null ? '—' : item.score.toFixed(2) }}
              </small>
            </template>
            <template v-else>—</template>
          </span>
          <span>{{ traceCount(row, 'clarify') }}</span>
          <span>{{ traceCount(row, 'tool_error') }}</span>
          <span>{{ traceNumber(row, 'latencyMs') }}</span>
          <span>{{ traceNumber(row, 'tokens') }}</span>
          <span><button class="text-action" type="button" @click="openTrace(row)">看轨迹<ChevronRight :size="13" /></button></span>
        </div>
      </div>
      <div v-else class="ui-empty"><span>暂无结果</span><small>选择测评集并发起一次测评</small></div>
    </section>

    <section class="harness-panel">
      <div class="harness-panel-heading">
        <div>
          <h3>评测矩阵</h3>
          <p>勾选多次测评运行并排看同一样本的判定，第一个是基线</p>
        </div>
        <button class="button button-subtle" type="button" :disabled="matrixBusy || matrixRunIds.length < 2" @click="loadMatrix">
          {{ matrixBusy ? '加载中…' : '生成矩阵' }}
        </button>
      </div>
      <div class="harness-detail-actions eval-matrix-picker">
        <label v-for="run in runs" :key="`mx-${run.eval_run_id}`" class="eval-matrix-run">
          <input type="checkbox" :checked="matrixRunIds.includes(run.eval_run_id)" @change="toggleMatrixRun(run.eval_run_id)" />
          <span>{{ runOptionLabel(run, datasetNames[run.dataset_id]) }}</span>
          <small v-if="matrixRunIds.indexOf(run.eval_run_id) === 0">基线</small>
        </label>
        <span v-if="!runs.length" class="eval-matrix-hint">暂无测评运行</span>
        <span v-else class="eval-matrix-hint">已选 {{ matrixRunIds.length }} / {{ MATRIX_RUN_LIMIT }} 个</span>
      </div>
      <p v-if="matrixError" class="eval-error" role="alert">{{ matrixError }}</p>
      <div v-if="matrix" class="eval-matrix">
        <p v-if="!matrix.sameDataset" class="evaluation-progress">所选运行来自不同测评集，横向对比仅供参考</p>
        <div class="eval-matrix-scroll">
          <table class="ui-table-real eval-matrix-table">
            <thead>
              <tr>
                <th>样本编号</th>
                <th v-for="run in matrixHeaderRuns" :key="`mxh-${run.runId}`">
                  {{ run.runId }}
                  <small>通过率 {{ run.passRateText }} · 覆盖率 {{ run.coverageText }}</small>
                </th>
                <th>同题择优</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in matrixRows" :key="`mxr-${row.caseId}`">
                <td>{{ row.caseId }}</td>
                <td v-for="cell in row.cells" :key="`mxc-${cell.runId}`" :class="['eval-matrix-cell', matrixCellClass(cell), { clickable: cell.verdict }]"
                    title="查看该样本" @click="openMatrixCell(row, cell)">
                  <span>{{ matrixCellText(cell) }}</span>
                  <small v-if="matrixChangeLabel(cell.change)">{{ matrixChangeLabel(cell.change) }}</small>
                </td>
                <td>{{ row.best?.runId || '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-if="!matrixRows.length" class="ui-empty"><span>矩阵没有样本</span></p>
      </div>
    </section>

    <section v-if="selectedResult" class="harness-panel">
      <div class="harness-panel-heading">
        <div>
          <h3>轨迹回放</h3>
          <p>样本 {{ selectedResult.case_id || '—' }} · 第 {{ numberOrNull(selectedResult.epoch) ?? '—' }} 轮</p>
        </div>
      </div>
      <div v-if="trace" class="eval-trace-summary">
        <span>Agent {{ trace.agent || '—' }}</span>
        <span>澄清轮次 {{ numberOrNull(trace.counts?.clarify) ?? '—' }}</span>
        <span>工具数 {{ Array.isArray(trace.tools) ? trace.tools.length : '—' }}</span>
        <span>Tokens {{ numberOrNull(trace.tokens) ?? '—' }}</span>
        <span>总耗时 {{ numberOrNull(trace.latencyMs) ?? '—' }} ms</span>
        <span>轮数 {{ numberOrNull(trace.turns) ?? '—' }}</span>
      </div>
      <p v-if="traceError" class="eval-error" role="alert">{{ traceError }}</p>
      <p v-if="traceBusy" class="evaluation-progress">正在读取轨迹…</p>
      <div v-if="!traceBusy && traceEvents.length" class="eval-trace-events" style="max-height: 320px; overflow: auto">
        <table class="ui-table-real eval-trace-table">
          <thead><tr><th>序号</th><th>时间</th><th>类型</th><th>级别</th><th>工具</th><th>摘要</th></tr></thead>
          <tbody>
            <tr v-for="(item, index) in traceEvents" :key="item.event_id ?? index">
              <td>{{ numberOrNull(item.event_id) ?? index + 1 }}</td>
              <td>{{ item.created_at || '—' }}</td>
              <td>{{ EVENT_TYPES[item.type] || item.type || '—' }}</td>
              <td>{{ LEVELS[item.level] || item.level || '—' }}</td>
              <td>{{ item.tool || '—' }}</td>
              <td>{{ item.summary || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else-if="!traceBusy && !traceError" class="ui-empty"><span>该样本暂无轨迹事件</span></div>
      <div v-if="traceTranscript.length" class="eval-trace-transcript">
        <strong>逐轮输出</strong>
        <ol>
          <li v-for="(item, index) in traceTranscript" :key="index">{{ item || '—' }}</li>
        </ol>
      </div>
    </section>

    <section v-if="selectedResult" class="harness-panel">
      <div class="harness-panel-heading">
        <div>
          <h3>期望与实际</h3>
          <p>样本 {{ selectedResult.case_id || '—' }} 期望什么、实际产出什么</p>
        </div>
      </div>
      <div class="eval-expect-grid">
        <div>
          <strong>期望</strong>
          <pre>{{ expectationText || '—' }}</pre>
        </div>
        <div>
          <strong>实际输出</strong>
          <pre>{{ selectedResult.actual_output || '（无输出）' }}</pre>
        </div>
        <div>
          <strong>评分说明</strong>
          <pre>{{ selectedResult.detail || '—' }}</pre>
        </div>
      </div>
    </section>

    <section class="harness-panel">
      <div class="harness-panel-heading">
        <div><h3>失败分类分布</h3><p>按失败原因统计样本条数</p></div>
      </div>
      <div v-if="failureRows.length" class="eval-failure-list">
        <div v-for="row in failureRows" :key="row.kind" class="eval-failure-row">
          <span class="eval-failure-label">{{ row.label }}</span>
          <span class="eval-failure-count">{{ row.count }}</span>
          <span class="eval-failure-track"><i :style="{ width: row.width + '%' }"></i></span>
        </div>
      </div>
      <div v-else class="ui-empty"><span>暂无失败样本</span></div>
    </section>

    <section class="harness-panel">
      <div class="harness-panel-heading">
        <div><h3>门禁检查</h3><p>按当前配置的门禁阈值校验本次运行</p></div>
        <span v-if="gateReport" class="ui-status" :class="gateReport.passed === true ? 'ok' : 'err'">{{ gateReport.passed === true ? '通过' : '未通过' }}</span>
      </div>
      <div v-for="gate in gates" :key="`${gate.label}-${gate.metric}`" class="gate-row">
        <span>{{ gate.label || gate.metric }} · 阈值 {{ gate.op || '>=' }} {{ formatMetric(gate.metric, gate.value) }}</span>
        <strong>{{ gate.metric }}</strong>
        <ChevronRight :size="14" />
      </div>
      <div v-if="!gates.length" class="ui-empty"><span>暂无门禁配置</span></div>
      <div class="harness-detail-actions">
        <label class="eval-field">基线运行编号（可选）
          <input v-model="baselineRunId" placeholder="留空表示不对比基线" />
        </label>
        <button class="button button-primary" type="button" :disabled="gateBusy || !selectedRunId" @click="checkGates">
          {{ gateBusy ? '检查中…' : '检查门禁' }}
        </button>
      </div>
      <p v-if="gateError" class="eval-error" role="alert">{{ gateError }}</p>
      <div v-for="check in gateChecks" :key="`${check.label}-${check.metric}`" class="gate-row" :class="{ failed: check.passed !== true }">
        <span>{{ check.label || check.metric }} · 阈值 {{ check.op || '>=' }} {{ formatMetric(check.metric, check.value) }} · 实际 {{ formatMetric(check.metric, check.actual) }}</span>
        <strong>{{ check.passed === true ? '通过' : check.passed === false ? '未通过' : '未评估' }}</strong>
        <CircleCheck v-if="check.passed === true" :size="14" />
        <CircleX v-else :size="14" />
      </div>
      <div v-if="gateReport && !gateChecks.length" class="ui-empty"><span>门禁检查未返回明细</span></div>
    </section>
  </div>
</template>

<style scoped>
.eval-panel { display: grid; min-width: 0; gap: 14px; }
.eval-field { display: grid; gap: 5px; color: var(--h-secondary); font-size: 11px; }
.eval-field select, .eval-field input { min-width: 150px; padding: 7px 9px; border: 1px solid var(--h-line); border-radius: 4px; color: var(--h-text); background: var(--surface); font: inherit; font-size: 11px; }
.eval-error { margin: 12px 17px; color: var(--h-error); overflow-wrap: anywhere; }
.eval-metric-cell { display: grid; gap: 3px; }
.eval-matrix-picker { flex-wrap: wrap; gap: 10px; }
.eval-matrix-run { display: flex; align-items: center; gap: 5px; color: var(--h-secondary); font-size: 11px; }
.eval-matrix-hint { color: var(--h-muted); font-size: 11px; }
.eval-matrix { padding: 0 17px 17px; }
.eval-matrix-scroll { overflow: auto; border: 1px solid var(--h-line-soft); border-radius: 5px; }
.eval-matrix-table { width: 100%; border-collapse: collapse; font-size: 11px; }
.eval-matrix-table th, .eval-matrix-table td { padding: 8px 10px; border-bottom: 1px solid var(--h-line-soft); text-align: left; white-space: nowrap; }
.eval-matrix-table th { position: sticky; top: 0; background: var(--surface); }
.eval-matrix-table th small { display: block; color: var(--h-muted); font-weight: 400; }
.eval-matrix-cell { display: grid; gap: 2px; }
.eval-matrix-cell.passed { color: var(--h-success); }
.eval-matrix-cell.failed { color: var(--h-error); }
.eval-matrix-cell.flaky { color: var(--h-warning); }
.eval-matrix-cell.empty { color: var(--h-muted); }
.eval-matrix-cell.clickable { cursor: pointer; }
.eval-matrix-cell.clickable:hover { text-decoration: underline; }
.eval-expect-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; padding: 0 17px 17px; }
.eval-expect-grid > div { display: grid; gap: 6px; min-width: 0; }
.eval-expect-grid strong { color: var(--h-text); font-size: 12px; }
.eval-expect-grid pre { margin: 0; padding: 8px 10px; max-height: 180px; overflow: auto; border: 1px solid var(--h-line-soft); border-radius: 5px; background: var(--surface); color: var(--h-secondary); font-size: 11px; white-space: pre-wrap; overflow-wrap: anywhere; }
.eval-trace-summary { display: flex; flex-wrap: wrap; gap: 14px; padding: 0 17px 12px; color: var(--h-secondary); font-size: 11px; }
.eval-trace-events { margin: 0 17px 17px; overflow: auto; border: 1px solid var(--h-line-soft); border-radius: 5px; }
.eval-trace-table { width: 100%; border-collapse: collapse; font-size: 11px; }
.eval-trace-table th, .eval-trace-table td { padding: 8px 10px; border-bottom: 1px solid var(--h-line-soft); text-align: left; white-space: nowrap; }
.eval-trace-table th { position: sticky; top: 0; color: var(--h-muted); background: var(--surface); }
.eval-failure-list { display: grid; gap: 10px; padding: 0 17px 17px; }
.eval-failure-row { display: grid; grid-template-columns: minmax(120px, 1fr) 40px minmax(120px, 2fr); align-items: center; gap: 10px; font-size: 11px; color: var(--h-secondary); }
.eval-failure-label { color: var(--h-text); }
.eval-failure-count { font-variant-numeric: tabular-nums; text-align: right; }
.eval-failure-track { height: 6px; overflow: hidden; border-radius: 5px; background: var(--surface-hover); }
.eval-failure-track i { display: block; height: 100%; border-radius: inherit; background: var(--h-warning); }
.eval-trace-transcript { display: grid; gap: 8px; margin: 0 17px 17px; }
.eval-trace-transcript strong { color: var(--h-text); font-size: 12px; }
.eval-trace-transcript ol { display: grid; gap: 6px; margin: 0; padding-left: 18px; color: var(--h-secondary); font-size: 11px; line-height: 1.6; }
</style>
