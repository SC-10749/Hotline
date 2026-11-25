<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Play, Square, RefreshCw } from 'lucide-vue-next'
import { cancelBenchmark, getBenchmarkRun, getBenchmarkRuns, getBenchmarkTools, startBenchmark } from '../../api'

const props = defineProps({ kind: { type: String, required: true }, apiBase: { type: String, default: '' } })
const names = { rag: 'RAG 评测', bird: 'BIRD SQL', load: '并发压测' }
const labels = { queued: '等待启动', running: '运行中', completed: '已完成', failed: '失败', cancelled: '已取消', interrupted: '已中断' }
const tools = ref(null)
const runs = ref([])
const selected = ref(null)
const ownedId = ref('')
const busy = ref(false)
const loading = ref(true)
const error = ref('')
const draft = ref({ input: '', collect: false, databases: '', predictions: '', limit: 10,
  evidence: true, profile: 'http', users: 2, duration: 15, spawnRate: 1, target: 'python' })
const active = computed(() => runs.value.find(r => ['queued', 'running'].includes(r.status)))
const ready = computed(() => tools.value?.items?.find(t => t.kind === props.kind)?.ready)
const resultRows = computed(() => {
  const s = selected.value?.summary || {}
  const rows = []
  const add = (key, label, unit = '') => {
    if (s[key] !== undefined && s[key] !== null) rows.push({ label, value: unit === '%' ? `${(s[key] * 100).toFixed(2)}%` : `${s[key]}${unit}` })
  }
  add('sampleCount', '样本数'); add('scoredCases', '已评分'); add('unscoredCases', '未评分')
  add('executionAccuracy', 'SQL 执行准确率', '%')
  add('requestCount', '完成请求'); add('failureCount', '失败请求'); add('errorRate', '错误率', '%')
  add('requestsPerSecond', '每秒请求'); add('p50Ms', 'P50 延迟', ' ms'); add('p95Ms', 'P95 延迟', ' ms'); add('p99Ms', 'P99 延迟', ' ms')
  const metricNames = { faithfulness: '忠实度', context_precision: '上下文精度', answer_relevancy: '答案相关性' }
  for (const [variant, metrics] of Object.entries(s.variants || {})) {
    for (const [key, metric] of Object.entries(metrics)) rows.push({ label: `${variant} · ${metricNames[key] || key}`, value: `${metric.mean}（${metric.n} 条）` })
  }
  if (s.retrieval?.labelledCases) {
    rows.push({ label: 'Recall@5', value: s.retrieval.recallAt5.toFixed(4) }, { label: 'MRR@5', value: s.retrieval.mrrAt5.toFixed(4) })
  }
  const streamNames = { firstEventMs: '首事件 P95', firstTextMs: '首段回答 P95', completionMs: '完成时间 P95' }
  for (const [key, metric] of Object.entries(s.stream?.timings || {})) {
    rows.push({ label: streamNames[key] || key, value: metric.p95 === null ? '无样本' : `${metric.p95} ms` })
  }
  return rows
})
let timer
let disposed = false

async function refresh() {
  try {
    const response = await getBenchmarkRuns(props.apiBase, props.kind)
    if (disposed) return
    runs.value = response.items
    if (selected.value) selected.value = runs.value.find(r => r.id === selected.value.id) || selected.value
    if (ownedId.value) {
      const run = await getBenchmarkRun(props.apiBase, ownedId.value)
      if (disposed) return
      selected.value = run
      if (!['queued', 'running'].includes(run.status)) ownedId.value = ''
    }
    error.value = ''
  } catch (cause) {
    if (!disposed) error.value = cause.message || '无法读取测试任务，请重试'
  } finally { loading.value = false }
}

async function checkTools() {
  try { tools.value = await getBenchmarkTools(props.apiBase) }
  catch (cause) { error.value = cause.message }
}

async function start() {
  busy.value = true
  error.value = ''
  try {
    const run = await startBenchmark(props.apiBase, { ...draft.value, kind: props.kind })
    if (disposed) {
      await cancelBenchmark(props.apiBase, run.id, true)
      return
    }
    ownedId.value = run.id
    selected.value = run
    await refresh()
  } catch (cause) { error.value = cause.message }
  finally { busy.value = false }
}

async function cancel(id) {
  busy.value = true
  try {
    await cancelBenchmark(props.apiBase, id)
    if (ownedId.value === id) ownedId.value = ''
    await refresh()
  } catch (cause) { error.value = cause.message }
  finally { busy.value = false }
}

function leave() {
  if (ownedId.value) cancelBenchmark(props.apiBase, ownedId.value, true).catch(() => {})
}
function formatTime(value) { return new Date(value).toLocaleString('zh-CN') }
onMounted(() => {
  refresh()
  checkTools()
  timer = setInterval(refresh, 3000)
  window.addEventListener('pagehide', leave)
})
onUnmounted(() => {
  disposed = true
  clearInterval(timer)
  window.removeEventListener('pagehide', leave)
  leave()
})
</script>

<template>
  <div class="benchmark-panel">
    <section class="harness-panel benchmark-setup">
      <div class="harness-panel-heading">
        <div><h3>{{ names[kind] }}</h3><p>点击开始后运行；离开本页停止本页启动的测试。</p></div>
        <button class="button button-subtle" type="button" @click="checkTools"><RefreshCw :size="14" />检查环境</button>
      </div>
      <p v-if="!tools" class="benchmark-note">正在检查隔离测试环境…</p>
      <p v-else class="benchmark-note" :class="{ 'benchmark-error': !ready }">
        {{ ready ? '测试环境已就绪 · 当前空闲时无测试进程' : '测试环境未就绪，请按下方接入说明安装依赖' }}
        <span v-if="kind === 'rag' && tools.versions?.ragas"> · Ragas {{ tools.versions.ragas }}</span>
        <span v-if="kind === 'load' && tools.versions?.locust"> · Locust {{ tools.versions.locust }}</span>
        <span v-if="kind === 'bird' && tools.birdRevision"> · 官方版本 {{ tools.birdRevision.slice(0, 12) }}</span>
      </p>
      <form class="benchmark-form" @submit.prevent="start">
        <template v-if="kind !== 'load'">
          <label class="benchmark-wide">{{ kind === 'rag' ? (draft.collect ? '问题用例 JSONL' : '已采集样本 JSONL') : 'BIRD 题目 JSON / JSONL' }}
            <input v-model.trim="draft.input" required maxlength="240" :placeholder="kind === 'rag' ? 'rag/samples.jsonl' : 'bird/mini_dev_sqlite.json'" />
            <small>填写相对 data/benchmarks 的路径，数据仅保存在本地。</small>
          </label>
          <label>样本上限<input v-model.number="draft.limit" type="number" min="1" max="500" required /></label>
        </template>
        <template v-if="kind === 'rag'">
          <label class="benchmark-check"><input v-model="draft.collect" type="checkbox" />先调用当前检索链采集答案</label>
          <p class="benchmark-note benchmark-wide">指标：忠实度、上下文精度；配置 Embedding 后计算答案相关性。提供 relevant_ids / retrieved_ids 后计算 Recall@5 和 MRR@5。</p>
        </template>
        <template v-if="kind === 'bird'">
          <label>SQLite 数据库目录<input v-model.trim="draft.databases" required placeholder="bird/dev_databases" /></label>
          <label class="benchmark-wide">已有预测 JSON（可选）<input v-model.trim="draft.predictions" placeholder="bird/predictions.json" /><small>按 question_id 映射 SQL；留空则调用当前模型生成，消耗模型额度。</small></label>
          <label class="benchmark-check"><input v-model="draft.evidence" type="checkbox" />生成 SQL 时提供官方 Evidence</label>
          <p class="benchmark-note benchmark-wide">SQLite · 官方 EX 执行准确率。样本需覆盖三个难度；结果标明数据指纹与工具版本。仅单次 SQL 生成，不代表完整 SQL Agent。</p>
        </template>
        <template v-if="kind === 'load'">
          <label>测试场景<select v-model="draft.profile" aria-label="测试场景"><option value="http">HTTP 健康接口</option><option value="sse">Agent SSE 真实任务</option></select></label>
          <label>请求入口<select v-model="draft.target" aria-label="请求入口"><option value="python">Python 本机 8888</option><option value="java">Java 本机 8080</option></select></label>
          <label>并发用户<input v-model.number="draft.users" type="number" min="1" max="100" required /></label>
          <label>持续时间（秒）<input v-model.number="draft.duration" type="number" min="5" max="600" required /></label>
          <label>每秒新增用户<input v-model.number="draft.spawnRate" type="number" min="1" max="20" required /></label>
          <p class="benchmark-note benchmark-wide">HTTP 场景不调用模型。SSE 场景会创建真实对话并消耗模型额度，检查成功终态、首事件与首段回答时间；停止时取消尚未完成的任务。</p>
        </template>
        <div class="benchmark-actions benchmark-wide">
          <button class="button button-primary" type="submit" :disabled="busy || !ready || !!active"><Play :size="14" />{{ busy ? '处理中…' : kind === 'load' ? '开始压测' : '开始测评' }}</button>
          <button v-if="active" class="button button-subtle" type="button" :disabled="busy" @click="cancel(active.id)"><Square :size="14" />取消运行</button>
          <span v-if="active" role="status">{{ labels[active.status] }}</span>
        </div>
      </form>
      <p v-if="error" class="benchmark-error" role="alert">{{ error }}</p>
      <details class="benchmark-help"><summary>接入说明与数据格式</summary>
        <p>在仓库根目录安装隔离环境，安装完成后点击「检查环境」。常规启动不会加载测试框架。</p>
        <pre>uv venv eval/.venv --python 3.13
uv pip install --python eval/.venv/Scripts/python.exe -r eval/requirements-tools.txt
.venv/Scripts/python.exe eval/setup_tools.py</pre>
        <p v-if="kind === 'rag'">已采集样本每行包含 id、question、answer、contexts（字符串数组），可选 reference、relevant_ids、retrieved_ids。采集模式使用 question、source_id，连接本地检索存储；判分使用本地 EVAL_JUDGE_* 与可选 EVAL_EMBEDDING_* 配置。送入判分器前会进行脱敏。</p>
        <p v-if="kind === 'bird'">题目使用官方 question_id、db_id、question、evidence、SQL、difficulty 字段。数据库按目录 / db_id / db_id.sqlite 放置。先自行下载官方数据集；安装脚本仅下载评分工具。外部预测模式的 Evidence 由预测生成方负责一致性。</p>
        <p>结果写入 data/evaluations/benchmarks。异常关闭页面后，心跳失联约 30 秒自动停止。一次只运行一个基准任务。</p>
      </details>
    </section>
    <section class="harness-panel benchmark-history">
      <div class="harness-panel-heading"><h3>运行记录</h3><button class="text-action" type="button" @click="refresh">刷新</button></div>
      <p v-if="loading" role="status">正在读取运行记录…</p>
      <p v-else-if="!runs.length" class="benchmark-note">暂无运行。配置输入后开始首次测试。</p>
      <div v-else class="benchmark-table-wrap"><table class="ui-table-real benchmark-table"><thead><tr><th>开始时间</th><th>运行编号</th><th>状态</th><th>操作</th></tr></thead>
        <tbody><tr v-for="run in runs" :key="run.id"><td>{{ formatTime(run.createdAt) }}</td><td><code>{{ run.id.slice(0, 12) }}</code></td><td>{{ labels[run.status] || run.status }}</td><td><button class="text-action" type="button" @click="selected = run">查看结果</button></td></tr></tbody>
      </table></div>
      <div v-if="selected" class="benchmark-result" aria-live="polite">
        <h4>{{ labels[selected.status] }} · {{ selected.id.slice(0, 12) }}</h4>
        <p v-if="selected.error" class="benchmark-error">{{ selected.error }}</p>
        <template v-if="Object.keys(selected.summary || {}).length">
          <p v-if="selected.summary.scope" class="benchmark-note">{{ selected.summary.scope }}</p>
          <dl class="benchmark-metrics"><div v-for="row in resultRows" :key="row.label"><dt>{{ row.label }}</dt><dd>{{ row.value }}</dd></div></dl>
          <details><summary>完整指标与版本信息</summary><pre>{{ JSON.stringify(selected.summary, null, 2) }}</pre></details>
        </template>
        <p v-else class="benchmark-note">{{ ['queued', 'running'].includes(selected.status) ? '任务执行中，结果会自动更新。' : '本次未产出指标。' }}</p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.benchmark-panel { display: grid; gap: 20px; }
.benchmark-setup, .benchmark-history { padding: 20px; min-width: 0; }
.benchmark-form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; margin-top: 20px; }
.benchmark-form label { display: grid; gap: 6px; color: var(--text); font-size: 13px; }
.benchmark-form input:not([type=checkbox]), .benchmark-form select { width: 100%; min-height: 38px; padding: 8px 10px; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); color: var(--text); box-sizing: border-box; }
.benchmark-form input:focus-visible, .benchmark-form select:focus-visible, summary:focus-visible { outline: 2px solid var(--text); outline-offset: 2px; }
.benchmark-wide { grid-column: 1 / -1; }
.benchmark-form .benchmark-check { display: flex; align-items: center; gap: 8px; }
.benchmark-note, .benchmark-form small, .benchmark-help { color: var(--text-secondary); font-size: 13px; line-height: 1.7; overflow-wrap: anywhere; }
.benchmark-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
.benchmark-error { color: var(--error); overflow-wrap: anywhere; }
.benchmark-help { margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--line-soft); }
.benchmark-help summary { cursor: pointer; color: var(--text); }
.benchmark-panel pre { padding: 14px; background: var(--surface-subtle); color: var(--text); border-radius: 8px; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 12px; }
.benchmark-table-wrap { overflow-x: auto; }
.benchmark-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.benchmark-table th, .benchmark-table td { text-align: left; padding: 12px 10px; border-bottom: 1px solid var(--line-soft); white-space: nowrap; }
.benchmark-table th { color: var(--text-secondary); font-weight: 500; }
.benchmark-result { margin-top: 20px; }
.benchmark-metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin: 16px 0 24px; }
.benchmark-metrics dt { color: var(--text-secondary); font-size: 13px; }
.benchmark-metrics dd { margin: 4px 0 0; color: var(--text); font-size: 17px; font-variant-numeric: tabular-nums; }
@media (max-width: 600px) { .benchmark-form { grid-template-columns: minmax(0, 1fr); } .benchmark-setup, .benchmark-history { padding: 14px; } }
</style>
