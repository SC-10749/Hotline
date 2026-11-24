// 发布治理：灰度、门禁阈值、发布记录与线上指标。
import { computed, ref } from 'vue'
import { getReleaseObservations, observeReleaseRollout } from '../../api'
import { getReleaseSummary, promoteRelease, evaluateReleaseGate, getReleaseGates, rollbackRelease, getReleaseRecords, advanceRollout, getReleaseConfig, saveReleaseConfig, getReleaseGateThresholds, saveReleaseGateThresholds } from '../../api'

export function useReleases({ props, notify }) {
  const releaseRollouts = ref([])
  const releaseRuns = ref([])
  const releaseMetrics = ref([])
  const releaseConnected = ref(false)
  const releaseError = ref('')
  const releaseDraft = ref({ project: 'hotline-agent', name: '', version: '', percentage: 10 })
  const releaseGateDraft = ref({ e2ePassRate: 0.917, ragFaithfulness: 0.91, highRiskErrors: 0, evalRunId: '' })
  const releaseGateResult = ref(null)
  const releaseGates = ref([])
  const releaseRecords = ref([])
  const releaseObservations = ref([])
  const observationsBusy = ref(false)
  const observationBusy = ref('')
  const observationError = ref('')
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
  function readNumberField(value) {
    if (value === null || value === undefined || value === '') return null
    const num = Number(value)
    return Number.isFinite(num) ? num : null
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


  return {
    advanceRolloutRow,
    checkReleaseGate,
    loadReleaseObservations,
    observationBusy,
    observationError,
    observationsBusy,
    observeRollout,
    promoteCurrentRelease,
    refreshReleaseData,
    releaseConfigDraft,
    releaseConnected,
    releaseDraft,
    releaseError,
    releaseGateDraft,
    releaseGateResult,
    releaseGates,
    releaseMetrics,
    releaseObservations,
    releasePolicyBusy,
    releasePolicyError,
    releasePolicyLoading,
    releaseRecordRows,
    releaseRecords,
    releaseRecordsBusy,
    releaseRecordsError,
    releaseRollouts,
    releaseRuns,
    releaseThresholdsBusy,
    releaseThresholdsDraft,
    rollbackReleaseByRow,
    rolloutAdvanceDrafts,
    rolloutBusy,
    rolloutKey,
    saveReleasePolicy,
    saveReleaseThresholds,
  }
}
