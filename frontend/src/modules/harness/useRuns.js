// 执行任务与运行总览：运行列表、详情事件流与运行创建。
import { computed, onUnmounted, ref, watch } from 'vue'
import { useRunEvents } from '../execution/useRunEvents'
import { getHarnessOverview } from '../../api'
import { cancelExecutionRun, createExecutionRun, getExecutionRuns, retryExecutionRun } from '../../api'

export function useRuns({ props, notify, activeSection, activeView }) {
  const runs = ref([])
  const filter = ref('全部任务')
  const search = ref('')
  const selectedRunId = ref('')
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
  const showParallelPanel = ref(false)
  const runDraft = ref({ conversationId: '', agent: 'chat', query: '', fileId: '', agentId: '', workspaceId: '' })
  let executionRefreshTimer
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

  const runDetail = ref(null)
  const overviewStats = ref(null)
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


  // 运行列表定时刷新：与原壳内的 5 秒轮询行为保持一致。
  function startExecutionRefresh() {
    executionRefreshTimer = window.setInterval(() => {
      if (['overview', 'runs'].includes(activeSection.value) && !executionLoading.value && !runSubmitBusy.value && !runActionBusy.value) refreshExecutionRuns({ silent: true })
    }, 5000)
  }

  onUnmounted(() => {
    runListGeneration += 1
    window.clearInterval(executionRefreshTimer)
  })

  return {
    changeRunPage,
    duplicateSelectedRun,
    eventsError,
    eventsLoading,
    eventsStreamState,
    executionConnected,
    executionError,
    executionLoaded,
    executionLoading,
    executionTotal,
    filter,
    formatTokenCount,
    loadOverviewStats,
    openCreateRun,
    overviewStats,
    refreshExecutionRuns,
    refreshSelectedRunEvents,
    retrySelectedRun,
    runActionBusy,
    runDraft,
    runEvents,
    runOffset,
    runOutput,
    runPageSize,
    runSubmitBusy,
    runs,
    search,
    selectRun,
    selectedRun,
    showParallelPanel,
    showRunDialog,
    startExecutionRefresh,
    statusFilters,
    statusLabels,
    stopSelectedRun,
    submitRun,
  }
}
