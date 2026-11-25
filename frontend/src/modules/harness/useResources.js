// 运行治理资源：机器节点、待审批队列与通知。
import { computed, ref } from 'vue'
import { getApprovalNotifications, getMachineErrors } from '../../api'
import { getHarnessMachines, getHarnessApprovals, decideHarnessApproval, getHarnessObservabilityRuns, getHarnessApproval, decideHarnessApprovalsBatch, drainHarnessMachine } from '../../api'

export function useResources({ props, notify }) {
  const resourceConnected = computed(() => machinesConnected.value || approvalsConnected.value || traceConnected.value)
  const resourceError = ref('')
  const harnessMachines = ref([])
  const harnessApprovals = ref([])
  const harnessTraceRuns = ref([])
  const machinesConnected = ref(false)
  const approvalsConnected = ref(false)
  const traceConnected = ref(false)
  const machineBusy = ref('')
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
  const approvalNotifications = ref([])
  const notificationsBusy = ref(false)
  const notificationsError = ref('')
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
  const pendingApprovalRows = computed(() => approvalRows.value.filter(row => row.status === 'pending'))
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

  async function refreshResourceData({ silent = false } = {}) {
    const [machines, approvals, traceRuns] = await Promise.allSettled([
      getHarnessMachines(props.apiBase),
      getHarnessApprovals(props.apiBase, 'pending'),
      getHarnessObservabilityRuns(props.apiBase),
    ])
    // 连接标志按请求各自成败记录：某一类失败不影响其余类型的展示
    machinesConnected.value = machines.status === 'fulfilled'
    harnessMachines.value = machines.status === 'fulfilled' ? machines.value?.items || [] : []
    approvalsConnected.value = approvals.status === 'fulfilled'
    harnessApprovals.value = approvals.status === 'fulfilled' ? approvals.value?.items || [] : []
    traceConnected.value = traceRuns.status === 'fulfilled'
    harnessTraceRuns.value = traceRuns.status === 'fulfilled' ? traceRuns.value?.items || [] : []
    const failure = [machines, approvals, traceRuns].find(item => item.status === 'rejected')?.reason
    resourceError.value = failure ? failure.message || '资源目录服务暂不可用' : ''
    if (failure && !silent) notify(`资源目录刷新失败：${resourceError.value}`)
    loadApprovalNotifications()
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


  return {
    approvalBusy,
    approvalDetail,
    approvalNotifications,
    approvalRows,
    approvalSelection,
    approvalsConnected,
    decideApproval,
    decideApprovalBatch,
    formatWorkerSeen,
    harnessMachines,
    harnessTraceRuns,
    loadApprovalNotifications,
    loadMachineErrors,
    machineBusy,
    machineErrorWorker,
    machineErrors,
    machineErrorsBusy,
    machineErrorsError,
    machineRows,
    machinesConnected,
    notificationsBusy,
    notificationsError,
    onlineWorkerCount,
    openApprovalDetail,
    openRejectDialog,
    pendingApprovalRows,
    refreshResourceData,
    rejectDialog,
    rejectReason,
    resourceConnected,
    submitRejectApproval,
    toggleMachineDrain,
    traceConnected,
  }
}
