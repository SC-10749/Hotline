// 测评中心：测评集、样本、评测配置、门禁与历史报告。
import { computed, ref } from 'vue'
import { usePageState } from '../../composables/usePageState'
import { datasetCardView } from '../evaluation/readability'
import { compareEvaluationRuns, downloadEvaluationRun } from '../../api'
import { createEvaluationDataset, createEvaluationRun, checkEvaluationGates, getEvaluationConfig, getEvaluationDatasets, getEvaluationRuns, getEvaluationSemanticMetrics, saveEvaluationConfig, getEvaluationDataset, addEvaluationCase, updateEvaluationCase, deleteEvaluationCase, importEvaluationCases, createEvaluationSnapshot, getEvaluationSnapshots, getEvaluationRun, replayEvaluationRun } from '../../api'

export function useEvaluations({ props, notify }) {
  const evaluationTab = usePageState('evaluation-tab', 'overview', ['overview', 'datasets', 'config', 'agent', 'rag', 'bird', 'load', 'reports'])
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
  const caseDraft = ref({ caseId: '', input: '', expectedOutput: '', rubric: '{}', turns: '', userProfile: '', semanticMetric: '' })
  const semanticMetricTemplates = ref([])
  const semanticMetricHint = computed(() => semanticMetricTemplates.value.find(item => item.metric === caseDraft.value.semanticMetric) || null)
  function applySemanticTemplate() {
    const metric = caseDraft.value.semanticMetric
    if (!metric) return
    const template = semanticMetricTemplates.value.find(item => item.metric === metric)
    const expect = {}
    for (const key of template?.required || []) expect[key] = []
    caseDraft.value.rubric = JSON.stringify({ type: 'semantic', metric, expect }, null, 2)
  }
  const datasetBusy = ref('')
  const evalRunItems = ref([])
  const evalRunDetail = ref(null)
  const evalRunCases = ref([])
  const evalRunBusy = ref(false)
  const evalPolling = ref(false)
  const evalRunStatus = ref('')
  const evalRuns = ref([])
  const evalGateReport = ref(null)
  const evalGateCheckError = ref('')
  const evalRunDataset = ref(null)
  const evalProgress = ref('')
  const evalReplayRuns = ref({})
  const evalSnapshots = ref([])
  const snapshotBusy = ref(false)
  const showImportDialog = ref(false)
  const importCasesText = ref('')
  const importBusy = ref(false)
  const evalCompareBase = ref('')
  const evalCompareTarget = ref('')
  const evalComparison = ref(null)
  const evalComparisonBusy = ref(false)
  const evalComparisonError = ref('')
  const evalExportRunId = ref('')
  async function refreshEvaluationData({ silent = false } = {}) {
    try {
      const [datasets, config, reports, metrics] = await Promise.all([
        getEvaluationDatasets(props.apiBase),
        getEvaluationConfig(props.apiBase),
        getEvaluationRuns(props.apiBase),
        getEvaluationSemanticMetrics(props.apiBase),
      ])
      semanticMetricTemplates.value = metrics?.items || []
      const items = (datasets?.items || []).map(item => {
        // 最近一次运行由后端一起返回，页面不再自己猜通过率与状态。
        const view = datasetCardView(item, item.lastRun)
        return { name: item.name, type: item.dataset_type, cases: String(item.case_count || 0), caseCount: Number(item.case_count || 0), pass: view.pass, delta: '', state: view.state, updated: view.updated, datasetId: item.dataset_id }
      })
      evalDatasets.value = items
      if (items.length && !items.some(item => item.datasetId === selectedEvaluationDatasetId.value)) selectedEvaluationDatasetId.value = items[0].datasetId || ''
      const nextConfig = config?.config
      if (nextConfig) {
        evaluationConfig.value = {
          ...evaluationConfig.value,
          ...nextConfig,
          dimensions: Array.isArray(nextConfig.dimensions) ? nextConfig.dimensions : evaluationConfig.value.dimensions,
          gates: Array.isArray(nextConfig.gates) ? nextConfig.gates : evaluationConfig.value.gates,
        }
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
    await loadEvalGateCheck()
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
  const evalNotPassedCount = computed(() => {
    const summary = latestEvalSummary.value
    if (!summary) return null
    const total = Number(summary.resultCount ?? summary.caseCount)
    const passed = Number(summary.passedCount ?? 0)
    return Number.isFinite(total) ? Math.max(0, total - passed) : null
  })
  const dimensionOptions = computed(() => {
    const configured = new Map((evaluationConfig.value.dimensions || []).filter(item => item && (item.label || item.name)).map(item => [item.label || item.name, item]))
    const labels = configured.size ? [...configured.keys()] : defaultDimensionLabels
    return labels.map(label => ({ label, enabled: configured.get(label)?.enabled !== false }))
  })
  const gateMetricOptions = [
    { value: 'passRate', label: '通过率' },
    { value: 'passAtK', label: '全对率' },
    { value: 'flakyRate', label: '不稳定率' },
    { value: 'avgLatencyMs', label: '平均耗时(ms)' },
    { value: 'avgTurns', label: '平均轮数' },
    { value: 'avgTokens', label: '平均token' },
    { value: 'failedCount', label: '失败条数' },
    { value: 'caseCount', label: '样本数' },
    { value: 'passedCount', label: '通过条数' },
    { value: 'resultCount', label: '结果条数' },
    { value: 'tokensUsed', label: '消耗token' },
    { value: 'skippedCount', label: '跳过条数' },
  ]
  const gateOpOptions = [
    { value: '>=', label: '≥' },
    { value: '<=', label: '≤' },
    { value: '>', label: '>' },
    { value: '<', label: '<' },
    { value: '==', label: '=' },
  ]
  const gateMetricLabels = Object.fromEntries(gateMetricOptions.map(item => [item.value, item.label]))
  const gateOpLabels = Object.fromEntries(gateOpOptions.map(item => [item.value, item.label]))
  function formatGateValue(value) {
    if (value === null || value === undefined || value === '') return '—'
    const num = Number(value)
    return Number.isFinite(num) ? String(num) : String(value)
  }
  const evalGateChecks = computed(() => {
    const checks = evalGateReport.value?.checks
    if (!Array.isArray(checks)) return []
    return checks.map(item => ({
      label: item?.label || gateMetricLabels[item?.metric] || item?.metric || '门禁',
      op: gateOpLabels[item?.op] || item?.op || '≥',
      value: formatGateValue(item?.value),
      actual: formatGateValue(item?.actual),
      passed: item?.passed,
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
    const rubric = caseItem?.rubric || {}
    caseDraft.value = {
      caseId: caseItem?.case_id || '',
      input: caseItem?.input_text || '',
      expectedOutput: caseItem?.expected_output || '',
      rubric: JSON.stringify(rubric, null, 2),
      turns: Array.isArray(caseItem?.turns) ? caseItem.turns.map(item => String(item)).join('\n') : '',
      userProfile: caseItem?.user_profile || '',
      semanticMetric: rubric.type === 'semantic' ? String(rubric.metric || '') : '',
    }
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
        turns: Array.isArray(item.turns) ? item.turns.map(line => String(line)) : [],
        userProfile: item.userProfile == null ? '' : String(item.userProfile),
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
      const payload = {
        input: caseDraft.value.input.trim(),
        expectedOutput: caseDraft.value.expectedOutput,
        rubric,
        turns: (caseDraft.value.turns || '').split('\n').map(line => line.trim()).filter(Boolean),
        userProfile: (caseDraft.value.userProfile || '').trim(),
      }
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

  async function loadEvalGateCheck() {
    const target = latestEvalRun.value?.eval_run_id
    if (!target) {
      evalGateReport.value = null
      evalGateCheckError.value = ''
      return
    }
    try {
      const payload = await checkEvaluationGates(props.apiBase, { target })
      evalGateReport.value = payload?.report || payload || null
      evalGateCheckError.value = ''
    } catch (error) {
      evalGateReport.value = null
      evalGateCheckError.value = error.message || '门禁判定失败'
    }
  }

  function addEvalGate() {
    if (!Array.isArray(evaluationConfig.value.gates)) evaluationConfig.value.gates = []
    evaluationConfig.value.gates.push({ label: '新门禁', metric: 'passRate', op: '>=', value: 0.9 })
  }

  function removeEvalGate(index) {
    if (!Array.isArray(evaluationConfig.value.gates)) return
    evaluationConfig.value.gates.splice(index, 1)
  }

  async function saveEvalConfig() {
    const gates = (evaluationConfig.value.gates || []).map(gate => ({
      label: String(gate.label || '').trim(),
      metric: gate.metric || 'passRate',
      op: gate.op || '>=',
      value: Number.isFinite(Number(gate.value)) ? Number(gate.value) : 0,
    }))
    try {
      await saveEvaluationConfig(props.apiBase, {
        ...evaluationConfig.value,
        dimensions: Array.isArray(evaluationConfig.value.dimensions) ? evaluationConfig.value.dimensions : [],
        gates,
      })
      evaluationConfig.value = { ...evaluationConfig.value, gates }
      evaluationConnected.value = true
      notify('评测配置已保存')
    } catch (error) {
      notify(`保存评测配置失败：${error.message || '测评服务不可用'}`)
    }
  }

  function toggleDimension(label, enabled) {
    if (!Array.isArray(evaluationConfig.value.dimensions) || !evaluationConfig.value.dimensions.length) {
      evaluationConfig.value.dimensions = defaultDimensionLabels.map(item => ({ label: item, enabled: item === label ? enabled : true }))
      return
    }
    const existing = evaluationConfig.value.dimensions.find(item => item.label === label)
    if (existing) existing.enabled = enabled
    else evaluationConfig.value.dimensions.push({ label, enabled })
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

  function selectEvaluationTab(tab) {
    evaluationTab.value = tab
  }

  // Harness 弹窗统一按 DOM 定位，只在 .harness-shell 内查找，不影响 App 自身弹窗

  return {
    addEvalGate,
    applySemanticTemplate,
    caseDraft,
    compareEvalRuns,
    datasetBusy,
    datasetDraft,
    deleteDatasetCase,
    dimensionOptions,
    evalCaseExpected,
    evalCaseInput,
    evalCaseTotal,
    evalCompareBase,
    evalCompareTarget,
    evalComparison,
    evalComparisonBusy,
    evalComparisonError,
    evalDatasets,
    evalExportRunId,
    evalGateCheckError,
    evalGateChecks,
    evalGateReport,
    evalNotPassedCount,
    evalPassRateText,
    evalProgress,
    evalReports,
    evalRunBusy,
    evalRunCases,
    evalRunDetail,
    evalRuns,
    evalSnapshots,
    evalStatusLabel,
    evalVerdictLabel,
    evaluationConfig,
    evaluationConnected,
    evaluationError,
    evaluationTab,
    exportEvalRunSamples,
    formatPercentNumber,
    gateMetricOptions,
    gateOpOptions,
    importBusy,
    importCasesText,
    latestEvalRun,
    latestEvalSummary,
    openCaseDialog,
    openDatasetDialog,
    openEvalRun,
    openImportCasesDialog,
    refreshEvaluationData,
    removeEvalGate,
    removeEvaluationDataset,
    replayEvalCase,
    runEvaluation,
    saveCase,
    saveDatasetSnapshot,
    saveEvalConfig,
    selectEvaluationDataset,
    selectEvaluationTab,
    selectedEvaluationDataset,
    semanticMetricHint,
    semanticMetricTemplates,
    showCaseDialog,
    showDatasetDialog,
    showImportDialog,
    snapshotBusy,
    submitDataset,
    submitImportCases,
    toggleDimension,
  }
}
