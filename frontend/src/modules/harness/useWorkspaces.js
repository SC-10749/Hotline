// 工作空间：目录、快照、变更与检出。
import { computed, ref } from 'vue'
import { getHarnessWorkspace, updateHarnessWorkspace } from '../../api'
import { checkoutWorkspace, getWorkspaceCheckout } from '../../api'
import { getHarnessWorkspaces, createHarnessWorkspace, getHarnessWorkspaceRuns, createHarnessWorkspaceSnapshot, getHarnessWorkspaceSnapshots, getHarnessWorkspaceChanges } from '../../api'

export function useWorkspaces({ props, notify }) {
  const harnessWorkspaces = ref([])
  const workspacesConnected = ref(false)
  const workspacesError = ref('')
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
  const workspaceDraft = ref({ name: '', repository: '', branch: 'main' })
  const workspaceCheckout = ref(null)
  const checkoutBusy = ref(false)
  const checkoutError = ref('')
  const workspaceRows = computed(() => harnessWorkspaces.value)
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


  return {
    checkoutBusy,
    checkoutError,
    createWorkspaceSnapshot,
    editingWorkspace,
    harnessWorkspaces,
    loadWorkspaceChanges,
    openWorkspaceDetails,
    openWorkspaceDialog,
    refreshWorkspaceData,
    runWorkspaceCheckout,
    showWorkspaceDialog,
    submitWorkspace,
    workspaceChanges,
    workspaceChangesError,
    workspaceCheckout,
    workspaceDraft,
    workspaceError,
    workspaceRows,
    workspaceRuns,
    workspaceRunsError,
    workspaceSaving,
    workspaceSelectedSnapshotId,
    workspaceSnapshotBusy,
    workspaceSnapshotError,
    workspaceSnapshots,
    workspacesConnected,
    workspacesError,
  }
}
