// 追踪与日志：运行 Trace、事件、指标、趋势与导出。
import { computed, ref } from 'vue'
import { getObservabilityExports, getObservabilityTrends } from '../../api'
import { getHarnessTrace, getHarnessObservabilityMetrics } from '../../api'

export function useTraces({ props, notify, harnessTraceRuns }) {
  const selectedTraceRunId = ref('')
  const traceEvents = ref([])
  const traceEventsBusy = ref(false)
  const traceEventsError = ref('')
  const traceFilters = ref({ level: '', tool: '', hasError: false, since: '', until: '', type: '' })
  const traceMetrics = ref(null)
  const traceTrendBucket = ref('hour')
  const traceTrends = ref([])
  const trendsBusy = ref(false)
  const trendsError = ref('')
  const exportFrom = ref('')
  const exportTo = ref('')
  const exportRunId = ref('')
  const exportBusy = ref(false)
  const exportError = ref('')
  const traceRunRows = computed(() => harnessTraceRuns.value)
  const selectedTraceRun = computed(() => traceRunRows.value.find(row => row.run_id === selectedTraceRunId.value) || traceRunRows.value[0] || null)
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


  return {
    exportBusy,
    exportError,
    exportFrom,
    exportObservabilityEvents,
    exportRunId,
    exportTo,
    loadTraceEvents,
    loadTraceMetrics,
    loadTraceTrends,
    selectedTraceRun,
    selectedTraceRunId,
    traceEvents,
    traceEventsBusy,
    traceEventsError,
    traceFilters,
    traceMetrics,
    traceRunRows,
    traceTrendBucket,
    traceTrends,
    trendsBusy,
    trendsError,
  }
}
