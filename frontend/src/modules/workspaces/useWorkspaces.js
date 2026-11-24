import { computed, reactive, ref } from 'vue'
import { getHarnessWorkspaces, getWorkspaceFiles, importWorkspace, updateHarnessWorkspace } from '../../api'
import { workspacePathAllowed } from './paths'
import { makeId } from '../app/ids'

// 文件面板里的示例变更清单：面板只有一份静态数据，先按原样保留。
const changedFiles = [
  { path: 'frontend/src/App.vue', status: 'M', detail: '+ 24  − 8', tone: 'modified' },
  { path: 'frontend/src/style.css', status: 'M', detail: '+ 126  − 12', tone: 'modified' },
  { path: 'frontend/src/components/AgentTimeline.vue', status: 'A', detail: '+ 84', tone: 'added' },
]

export function useWorkspaces(ctx) {
  const showProjectNameDialog = ref(false)
  const projectNameDraft = ref('')
  const projectNameOriginal = ref('')
  const projectFiles = ref([])
  const projectUploadBusy = ref(false)
  const pendingWorkspaceImport = ref(false)
  const pendingWorkspaceFiles = ref([])
  const pendingWorkspaceEntries = ref([])
  const pendingWorkspaceFolderName = ref('')
  const folderImportOpen = ref(false)
  const folderImportSkipped = ref(0)
  const folderImportProgress = ref({ done: 0, total: 0, current: '' })

  // ===== 工作区文件夹导入：文件清单与上传进度 =====
  const folderImportTotalSize = computed(() => pendingWorkspaceEntries.value.reduce((sum, entry) => sum + (entry.size || 0), 0))
  const folderImportPercent = computed(() => {
    const { done, total } = folderImportProgress.value
    return total ? Math.min(100, Math.round((done / total) * 100)) : 0
  })

  async function openProjectView() {
    ctx.activePage = 'home'
    ctx.showWorkspacePanel = true
    ctx.workspacePanelTab = 'files'
    ctx.mobileSidebarOpen = false
    const workspaceId = ctx.selectedProjectId
    projectFiles.value = []
    if (!workspaceId) return
    try {
      const result = await getWorkspaceFiles(ctx.backendUrl, workspaceId)
      if (ctx.selectedProjectId === workspaceId) projectFiles.value = result.files || []
      if (result.truncated) ctx.showToast('工作区较大，文件面板展示前 5000 项')
    } catch (error) {
      ctx.showToast(error.message || '工作区文件读取失败')
    }
  }

  async function refreshWorkspaces() {
    try {
      const result = await getHarnessWorkspaces(ctx.backendUrl)
      ctx.projectGroups = (result.items || []).map(workspace => ({ ...workspace,
        id: workspace.workspace_id, child: '', tasks: ctx.projectGroups.find(item => item.id === workspace.workspace_id)?.tasks || [],
      }))
      ctx.selectedProjectName = ctx.projectGroups.find(item => item.id === ctx.selectedProjectId)?.name || ''
    } catch (error) {
      ctx.showToast(error.message || '工作区读取失败')
    }
  }

  function addWorkspace() {
    if (projectUploadBusy.value) return
    pendingWorkspaceImport.value = true
    // The browser owns directory access prompts; Hotline confirms the upload afterward.
    if (typeof window.showDirectoryPicker === 'function') {
      pickWorkspaceDirectory()
      return
    }
    ctx.hooks.pickWorkspaceFolder()
  }

  async function pickWorkspaceDirectory() {
    try {
      const handle = await window.showDirectoryPicker({ id: 'hotline-workspace', mode: 'read' })
      const entries = []
      await collectDirectoryEntries(handle, handle.name, entries)
      if (!entries.length) {
        resetWorkspaceImport()
        ctx.showToast('这个文件夹里没有可上传的文件')
        return
      }
      prepareWorkspaceImport(entries, handle.name)
    } catch (error) {
      resetWorkspaceImport()
      if (error?.name !== 'AbortError') ctx.showToast(error.message || '读取文件夹失败')
    }
  }

  async function collectDirectoryEntries(handle, prefix, output) {
    for await (const entry of handle.values()) {
      if (!workspacePathAllowed(`${prefix}/${entry.name}`)) continue
      if (entry.kind === 'file') {
        const file = await entry.getFile()
        output.push({ file, name: entry.name, path: `${prefix}/${entry.name}`, size: file.size })
        continue
      }
      if (entry.kind === 'directory') await collectDirectoryEntries(entry, `${prefix}/${entry.name}`, output)
    }
  }

  function prepareWorkspaceImport(entries, folderName) {
    const supported = entries.filter((entry) => workspacePathAllowed(entry.path) && entry.size <= 50 * 1024 * 1024)
    const skipped = entries.length - supported.length
    if (skipped) ctx.showToast(`已跳过 ${skipped} 个私密、依赖或超过 50 MB 的文件`)
    if (!supported.length) {
      resetWorkspaceImport()
      ctx.showToast('没有可上传的文件')
      return
    }
    pendingWorkspaceEntries.value = supported
    pendingWorkspaceFiles.value = supported.map((entry) => entry.file)
    pendingWorkspaceFolderName.value = folderName
    folderImportSkipped.value = skipped
    folderImportProgress.value = { done: 0, total: supported.length, current: '' }
    folderImportOpen.value = true
  }

  function resetWorkspaceImport() {
    pendingWorkspaceImport.value = false
    pendingWorkspaceFiles.value = []
    pendingWorkspaceEntries.value = []
    pendingWorkspaceFolderName.value = ''
    folderImportSkipped.value = 0
    folderImportProgress.value = { done: 0, total: 0, current: '' }
  }

  function cancelFolderImport() {
    if (projectUploadBusy.value) return
    folderImportOpen.value = false
    resetWorkspaceImport()
  }

  async function startFolderUpload() {
    if (projectUploadBusy.value) return
    const entries = pendingWorkspaceEntries.value
    const folderName = pendingWorkspaceFolderName.value || '新工作区'
    if (!entries.length) {
      cancelFolderImport()
      return
    }
    projectUploadBusy.value = true
    folderImportProgress.value = { done: 0, total: entries.length, current: '' }
    try {
      const result = await importWorkspace(ctx.backendUrl, folderName, entries)
      const workspace = result.workspace
      ctx.projectGroups.push({ ...workspace, id: workspace.workspace_id, child: '', tasks: [] })
      ctx.selectedProjectName = workspace.name
      ctx.selectedProjectId = workspace.workspace_id
      projectFiles.value = entries.map((entry) => ({ name: entry.path, size: entry.size }))
      folderImportProgress.value = { done: entries.length, total: entries.length, current: '' }
      folderImportOpen.value = false
      resetWorkspaceImport()
      ctx.showWorkspacePanel = true
      ctx.workspacePanelTab = 'files'
      ctx.showToast(`已导入工作区「${workspace.name}」中的 ${result.files} 个文件`)
      openProjectNameDialog(ctx.selectedProjectName)
    } catch (error) {
      ctx.showToast(error.message || '文件夹上传失败，请检查文件服务')
    } finally {
      projectUploadBusy.value = false
    }
  }

  function addWorkspaceTask(project) {
    ctx.selectedProjectName = project.name
    ctx.selectedProjectId = project.id
    if (!project.tasks) project.tasks = []
    project.tasks.unshift({ id: makeId(), title: '新任务' })
    ctx.hooks.newSession()
    ctx.showToast(`已在工作区「${project.name}」中新建任务`)
  }

  function openProjectNameDialog(name) {
    projectNameOriginal.value = name
    projectNameDraft.value = name
    showProjectNameDialog.value = true
  }

  async function saveProjectName() {
    const name = projectNameDraft.value.trim() || projectNameOriginal.value || '新工作区'
    const project = ctx.projectGroups.find((item) => item.id === ctx.selectedProjectId)
    if (project?.id) {
      try {
        const result = await updateHarnessWorkspace(ctx.backendUrl, project.id, {
          name, repository: project.repository, branch: project.branch || 'main', revision: project.revision,
        })
        Object.assign(project, result.workspace)
      } catch (error) {
        ctx.showToast(error.message || '工作区重命名失败')
        return
      }
    }
    if (project) project.name = name
    if (ctx.selectedProjectName === projectNameOriginal.value) ctx.selectedProjectName = name
    showProjectNameDialog.value = false
    ctx.showToast(`项目已命名为「${name}」`)
  }

  async function onProjectFolderPicked(event) {
    const files = Array.from(event.target.files || [])
    event.target.value = ''
    if (!files.length) {
      resetWorkspaceImport()
      return
    }
    const folderName = files[0].webkitRelativePath?.split('/')[0] || '新工作区'
    const entries = files.map((file) => ({
      file,
      name: file.name,
      path: file.webkitRelativePath || file.name,
      size: file.size,
    }))
    prepareWorkspaceImport(entries, folderName)
  }

  const state = reactive({
    showProjectNameDialog, projectNameDraft, projectNameOriginal,
    projectFiles, projectUploadBusy,
    pendingWorkspaceImport, pendingWorkspaceFiles, pendingWorkspaceEntries, pendingWorkspaceFolderName,
    folderImportOpen, folderImportSkipped, folderImportProgress,
    folderImportTotalSize, folderImportPercent, changedFiles,
  })

  const actions = {
    openProjectView, refreshWorkspaces, addWorkspace, pickWorkspaceDirectory,
    prepareWorkspaceImport, resetWorkspaceImport, cancelFolderImport, startFolderUpload,
    addWorkspaceTask, openProjectNameDialog, saveProjectName, onProjectFolderPicked,
  }

  return { state, actions }
}
