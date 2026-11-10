<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js/lib/core'
import bash from 'highlight.js/lib/languages/bash'
import css from 'highlight.js/lib/languages/css'
import java from 'highlight.js/lib/languages/java'
import javascript from 'highlight.js/lib/languages/javascript'
import json from 'highlight.js/lib/languages/json'
import markdown from 'highlight.js/lib/languages/markdown'
import python from 'highlight.js/lib/languages/python'
import sql from 'highlight.js/lib/languages/sql'
import typescript from 'highlight.js/lib/languages/typescript'
import xml from 'highlight.js/lib/languages/xml'
import 'highlight.js/styles/github-dark.css'
import {
  Activity, AlertCircle, ArrowUp, Check, CheckCircle2, ChevronDown,
  ChevronRight, Eye, File, FileText, FlaskConical, FolderOpen, Link2, LoaderCircle,
  MessageCircle, MoreHorizontal, Paperclip, Plus, Puzzle, Search, Settings2,
  Home, Workflow, Bell, PanelLeft, FileCode2, GitCompare, CircleDot,
  Sparkles, Square, Trash2, ToggleLeft, ToggleRight, X, Copy, ExternalLink, Download, Bot, Archive,
  UserRound, KeyRound, Palette, Smile, Headset, CircleUserRound, CalendarClock,
  LibraryBig, GitBranch, History, MessagesSquare, ShieldCheck, Upload, Map as MapIcon,
} from 'lucide-vue-next'
import { apiUrl, bindBotSession, compensateDocuments, createBot, createSchedule, deleteBot, deleteCredential, deleteSchedule, getAllSessions, getBots, getCredential, getDocumentPreview, getDocumentVersions, getDocuments, getProfile, getSchedules, getSession, getSessions, getSkills, removeDocument, removeSession, removeSkill, runSchedule, saveCredential, saveProfile, setSkillEnabled, stopAgent, streamUrl, testBackend, testCredential, updateBot, updateSchedule, uploadDocument, uploadFile, uploadSkill, vectorizeDocument } from './api'
import HarnessApp from './HarnessApp.vue'
import CodeMapPage from './modules/artifacts/CodeMapPage.vue'
import { getHarnessWorkspaces, getWorkspaceFiles, importWorkspace, updateHarnessWorkspace } from './api'
import { workspacePathAllowed } from './modules/workspaces/paths'
import { appendProgressEvent, finishProgress, progressEntryLabel, progressLabel } from './modules/execution/progress'

marked.setOptions({ breaks: true, gfm: true })
Object.entries({ bash, css, java, javascript, json, markdown, python, sql, typescript, xml }).forEach(([name, language]) => hljs.registerLanguage(name, language))

const modes = [
  { id: 'chat', label: '对话助手', icon: MessageCircle, description: '日常问答与创作' },
  { id: 'file', label: '文件问答', icon: FolderOpen, description: '基于上传内容提问' },
  { id: 'ppt', label: 'PPT 生成', icon: FileText, description: '整理主题并生成演示文稿' },
  { id: 'deep', label: '深度研究', icon: FlaskConical, description: '结合检索进行深入分析' },
  { id: 'skills', label: '技能助手', icon: Puzzle, description: '调用已安装的技能处理任务' },
]
const quickPrompts = [
  { icon: Sparkles, text: '介绍一下你自己' },
  { icon: Search, text: '帮我分析一个问题' },
  { icon: FileText, text: '帮我整理一份汇报大纲' },
]
const projectGroups = ref([])
const changedFiles = [
  { path: 'frontend/src/App.vue', status: 'M', detail: '+ 24  − 8', tone: 'modified' },
  { path: 'frontend/src/style.css', status: 'M', detail: '+ 126  − 12', tone: 'modified' },
  { path: 'frontend/src/components/AgentTimeline.vue', status: 'A', detail: '+ 84', tone: 'added' },
]
const supportedExtensions = new Set(['pdf', 'doc', 'docx', 'txt', 'png', 'jpg', 'jpeg'])
const backendUrl = ref(localStorage.getItem('dodo-api-base') || import.meta.env.VITE_API_BASE_URL || '')
const settingsDraft = ref(backendUrl.value)
const activeMode = ref('chat')
const activePage = ref('home')
const profileSection = ref('basics')
const exportingHistory = ref(false)
const sessions = ref([])
const activeId = ref(null)
const input = ref('')
const selectedFile = ref(null)
const uploadedFileId = ref(null)
// A library document can ground answers just like an uploaded file.
const docSource = ref(null)
const uploadBusy = ref(false)
const sending = ref(false)
const loadingHistory = ref(false)
const connectionState = ref('checking')
const connectionMessage = ref('')
const toast = ref('')
const showSettings = ref(false)
const permissionRequest = ref(null)
const showProjectNameDialog = ref(false)
const projectNameDraft = ref('')
const projectNameOriginal = ref('')
const deletingId = ref(null)
const mobileSidebarOpen = ref(false)
const sidebarCollapsed = ref(false)
const showWorkspacePanel = ref(false)
const workspacePanelTab = ref('files')
const selectedProjectName = ref('')
const selectedProjectId = ref('')
const projectFiles = ref([])
const projectUploadBusy = ref(false)
const pendingWorkspaceImport = ref(false)
const pendingWorkspaceFiles = ref([])
const pendingWorkspaceEntries = ref([])
const pendingWorkspaceFolderName = ref('')
const folderImportOpen = ref(false)
const folderImportSkipped = ref(0)
const folderImportProgress = ref({ done: 0, total: 0, current: '' })
const fileInput = ref(null)
const projectFolderInput = ref(null)
const messageList = ref(null)
// 用户主动上滑后不再强制回到底部，回到底部时自动恢复跟随
const autoScroll = ref(true)
const composer = ref(null)
const searchText = ref('')
const searchOpen = ref(false)
const busySettings = ref(false)
const showSkills = ref(false)
const skills = ref([])
const petOptions = [
  { id: 'smile', label: '微笑伙伴', icon: Smile },
  { id: 'bot', label: '机器人伙伴', icon: Bot },
  { id: 'sparkle', label: '闪耀伙伴', icon: Sparkles },
]
const schedules = ref([])
const scheduleBusy = ref(false)
const showScheduleForm = ref(false)
const scheduleDraft = ref({ name: '', prompt: '', agent: 'chat', intervalMinutes: 60 })
const bots = ref([])
const botBusy = ref(false)
const showBotForm = ref(false)
const botDraft = ref({ botId: '', name: '', instruction: '', skills: [], enabled: true })
const profileDraft = ref({ nickname: '', bio: '', answerStyle: 'default', theme: 'system' })
const profileBusy = ref(false)
const credentialDraft = ref({ provider: '', baseUrl: '', model: '', apiKey: '' })
const credentialBusy = ref(false)
const credentialMask = ref('')
const petEnabled = ref(localStorage.getItem('hotline-pet-enabled') === '1')
const petChoice = ref(localStorage.getItem('hotline-pet') || 'smile')
const petIcon = computed(() => petOptions.find(item => item.id === petChoice.value)?.icon || Smile)
const petLabel = computed(() => petOptions.find(item => item.id === petChoice.value)?.label || '虚拟伙伴')
const skillBusy = ref(false)
const skillMessage = ref(null)
const skillEntries = ref([])
const skillEntryChoice = ref('')
const deletingSkill = ref(null)
const skillInput = ref(null)
const showDocs = ref(false)
const docs = ref([])
const docBusy = ref(false)
const docMessage = ref(null)
const deletingDoc = ref(null)
const expandingDoc = ref(null)
const docVersions = ref({})
const docInput = ref(null)
const showDocPreview = ref(false)
const previewDoc = ref(null)
const docPreview = ref(null)
const docPreviewBusy = ref(false)
const docPreviewError = ref('')
const docPreviewTab = ref('chunks')
let pendingSkillFile = null
let readerController = null
let toastTimer
let keydownHandler
let docPollTimer

const currentSession = computed(() => sessions.value.find((session) => session.id === activeId.value) || null)
const isWelcome = computed(() => activePage.value === 'home' && currentSession.value?.messages.length === 0 && !loadingHistory.value)
// 弹窗统一按 DOM 定位：App 的遮罩挂在 body 上，不会误伤 Harness 内嵌弹窗
const appDialogCount = computed(() => [
  showSettings.value, showSkills.value, showDocs.value, showDocPreview.value,
  folderImportOpen.value, permissionRequest.value, showProjectNameDialog.value,
].filter(Boolean).length)
let appDialogReturnFocus
function appDialogBackdrops() {
  return Array.from(document.body.children).filter(element => element.classList.contains('modal-backdrop'))
}
function appTopDialog() {
  const backdrops = appDialogBackdrops()
  return backdrops[backdrops.length - 1]?.querySelector('[role="dialog"], [role="alertdialog"]') || null
}
function appDialogControls(dialog) {
  return Array.from(dialog?.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], summary, [tabindex="0"]') || []).filter(element => element.getClientRects().length)
}
watch(appDialogCount, async (count, previousCount) => {
  if (count > 0) {
    if (previousCount === 0) appDialogReturnFocus = document.activeElement
    await nextTick()
    // 模板里的 autofocus 优先，保留各弹窗原本的落点意图
    const controls = appDialogControls(appTopDialog())
    ;(controls.find(element => element.hasAttribute('autofocus')) || controls[0])?.focus()
  } else if (previousCount > 0) {
    if (appDialogReturnFocus?.isConnected) appDialogReturnFocus.focus()
    appDialogReturnFocus = null
  }
})
const visibleSessions = computed(() => sessions.value.filter((session) => !session.isDraft && session.title.toLowerCase().includes(searchText.value.toLowerCase())))
const runningItem = computed(() => (sending.value && currentSession.value && !currentSession.value.isDraft ? [currentSession.value] : []))
const recentList = computed(() => visibleSessions.value.filter((session) => !runningItem.value.includes(session)))
const canSend = computed(() => !sending.value && !uploadBusy.value && (input.value.trim() || uploadedFileId.value))
const activeModeInfo = computed(() => modes.find((mode) => mode.id === activeMode.value) || modes[0])
const draftSessions = () => sessions.value.filter((session) => session.isDraft)
const enabledSkills = computed(() => skills.value.filter((skill) => skill.enabled))
const docCounts = computed(() => {
  const counts = { waiting: 0, vectorized: 0, failed: 0 }
  for (const doc of docs.value) {
    if (doc.status === 'VECTORIZED') counts.vectorized += 1
    else if (doc.status === 'FAILED') counts.failed += 1
    else if (['PENDING', 'CONVERTING', 'CONVERTED', 'VECTORIZING'].includes(doc.status)) counts.waiting += 1
  }
  return counts
})

// ===== 工作区文件夹导入：文件清单与上传进度 =====
const folderImportTotalSize = computed(() => pendingWorkspaceEntries.value.reduce((sum, entry) => sum + (entry.size || 0), 0))
const folderImportPercent = computed(() => {
  const { done, total } = folderImportProgress.value
  return total ? Math.min(100, Math.round((done / total) * 100)) : 0
})

function makeId() {
  return `chat_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`
}

// ===== 任务卡与时间线：状态点、等宽耗时、相对时间 =====
const runStartedAt = ref(0)
const nowTick = ref(Date.now())
let tickTimer = null
const runningElapsed = computed(() => fmtElapsed(nowTick.value - runStartedAt.value))
const modeBadges = {
  chat: { label: '对话助手', cls: 'b-chat' },
  file: { label: '文件问答', cls: 'b-file' },
  ppt: { label: 'PPT 生成', cls: 'b-ppt' },
  deep: { label: '深度研究', cls: 'b-deep' },
  skills: { label: '技能助手', cls: 'b-skill' },
}

function badgeInfo(agentType) {
  return modeBadges[agentType] || modeBadges.chat
}

function fmtElapsed(ms) {
  const total = Math.max(0, Math.round(ms / 1000))
  if (total < 60) return `${total}s`
  return `${Math.floor(total / 60)}m${String(total % 60).padStart(2, '0')}s`
}

function fmtStep(ms) {
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  return fmtElapsed(ms)
}

function fmtRelTime(value) {
  if (!value) return ''
  const time = typeof value === 'number' ? value : Date.parse(value)
  if (Number.isNaN(time)) return ''
  const diff = Date.now() - time
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  if (diff < 172_800_000) return '昨天'
  return new Date(time).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
}

function startTick() {
  if (!tickTimer) tickTimer = setInterval(() => { nowTick.value = Date.now() }, 1000)
}

function stopTick() {
  if (tickTimer) { clearInterval(tickTimer); tickTimer = null }
}

function timelineSummary(message) {
  const count = message.timeline.length
  const duration = message.t0 && message.t1 ? fmtElapsed(message.t1 - message.t0) : ''
  return duration ? `${count} 步 · ${duration}` : `${count} 步`
}

function messageIsStreaming(message) {
  const active = sending.value && message === currentSession.value?.messages.at(-1)
  return !message.done && (active || !!message.pendingText) && !message.timeline?.some(entry => entry.type === 'error')
}

function showToast(message) {
  toast.value = message
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toast.value = '' }, 2600)
}

function titleFor(text) {
  const value = text.trim().replace(/\s+/g, ' ')
  return value.length > 28 ? `${value.slice(0, 28)}…` : value || '新对话'
}

function normalizeBrandText(value) {
  return String(value || '')
    .replace(/\bDodo Agent\b/gi, 'Hotline Agent')
    .replace(/豆豆助手|豆豆 Agent/g, 'Hotline Agent')
}

function newSession() {
  if (sending.value) return
  const existing = draftSessions()[0]
  if (existing) {
    activeId.value = existing.id
  } else {
    const session = { id: makeId(), title: '新对话', messages: [], isDraft: true, updatedAt: Date.now() }
    sessions.value.unshift(session)
    activeId.value = session.id
  }
  mobileSidebarOpen.value = false
  activeMode.value = 'chat'
  selectedFile.value = null
  uploadedFileId.value = null
  docSource.value = null
  input.value = ''
}

function toggleSidebar() {
  if (window.matchMedia('(max-width: 960px)').matches) {
    mobileSidebarOpen.value = !mobileSidebarOpen.value
    sidebarCollapsed.value = false
    return
  }
  sidebarCollapsed.value = !sidebarCollapsed.value
}

function openHome() {
  activePage.value = 'home'
  showWorkspacePanel.value = false
  mobileSidebarOpen.value = false
  if (!currentSession.value) newSession()
  nextTick(() => composer.value?.focus({ preventScroll: true }))
}

function openAutomation() {
  activePage.value = 'automation'
  showWorkspacePanel.value = false
  mobileSidebarOpen.value = false
  refreshSchedules()
}

function openPlugins() {
  activePage.value = 'plugins'
  showWorkspacePanel.value = false
  mobileSidebarOpen.value = false
  refreshSkills()
}

function openBotPage() {
  activePage.value = 'bot'
  showWorkspacePanel.value = false
  mobileSidebarOpen.value = false
  refreshBots()
}

function openDocsPage() {
  activePage.value = 'docs'
  showWorkspacePanel.value = false
  mobileSidebarOpen.value = false
}

function openHarnessPage() {
  activePage.value = 'harness'
  showWorkspacePanel.value = false
  mobileSidebarOpen.value = false
}

function openCodeMapPage() {
  activePage.value = 'code-map'
  showWorkspacePanel.value = false
  mobileSidebarOpen.value = false
}

function openExportPage() {
  activePage.value = 'export'
  showWorkspacePanel.value = false
  mobileSidebarOpen.value = false
}

async function exportChatHistory() {
  if (exportingHistory.value) return
  exportingHistory.value = true
  try {
    const records = await getAllSessions(backendUrl.value)
    const conversations = []
    for (let start = 0; start < records.length; start += 8) {
      const batch = await Promise.all(records.slice(start, start + 8).map(async (record) => {
        const detail = await getSession(backendUrl.value, record.conversationId)
        return {
          conversationId: record.conversationId,
          title: titleFor(record.question || ''),
          agentType: detail.agentType || record.agentType || 'chat',
          createTime: record.createTime || null,
          messages: (detail.messages || []).map((row) => ({
            question: row.question || '', answer: row.answer || '', thinking: row.thinking || '',
            reference: parseArray(row.reference), recommend: parseArray(row.recommend),
            fileId: row.fileid || null, createTime: row.createTime || null,
          })),
        }
      }))
      conversations.push(...batch)
    }
    const payload = { format: 'dodo-chat-history', version: 1, exportedAt: new Date().toISOString(), conversations }
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `dodo-chat-history-${new Date().toISOString().slice(0, 10)}.json`
    link.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    showToast(`已导出 ${conversations.length} 个历史会话`)
  } catch (error) {
    showToast(error.message || '聊天记录导出失败')
  } finally {
    exportingHistory.value = false
  }
}

async function openProjectView() {
  activePage.value = 'home'
  showWorkspacePanel.value = true
  workspacePanelTab.value = 'files'
  mobileSidebarOpen.value = false
  const workspaceId = selectedProjectId.value
  projectFiles.value = []
  if (!workspaceId) return
  try {
    const result = await getWorkspaceFiles(backendUrl.value, workspaceId)
    if (selectedProjectId.value === workspaceId) projectFiles.value = result.files || []
    if (result.truncated) showToast('工作区较大，文件面板展示前 5000 项')
  } catch (error) {
    showToast(error.message || '工作区文件读取失败')
  }
}

async function refreshWorkspaces() {
  try {
    const result = await getHarnessWorkspaces(backendUrl.value)
    projectGroups.value = (result.items || []).map(workspace => ({ ...workspace,
      id: workspace.workspace_id, child: '', tasks: projectGroups.value.find(item => item.id === workspace.workspace_id)?.tasks || [],
    }))
    selectedProjectName.value = projectGroups.value.find(item => item.id === selectedProjectId.value)?.name || ''
  } catch (error) {
    showToast(error.message || '工作区读取失败')
  }
}

function requestPermission(request) {
  permissionRequest.value = request
}

function addWorkspace() {
  if (projectUploadBusy.value) return
  pendingWorkspaceImport.value = true
  // The browser owns directory access prompts; Hotline confirms the upload afterward.
  if (typeof window.showDirectoryPicker === 'function') {
    pickWorkspaceDirectory()
    return
  }
  projectFolderInput.value?.click()
}

async function pickWorkspaceDirectory() {
  try {
    const handle = await window.showDirectoryPicker({ id: 'hotline-workspace', mode: 'read' })
    const entries = []
    await collectDirectoryEntries(handle, handle.name, entries)
    if (!entries.length) {
      resetWorkspaceImport()
      showToast('这个文件夹里没有可上传的文件')
      return
    }
    prepareWorkspaceImport(entries, handle.name)
  } catch (error) {
    resetWorkspaceImport()
    if (error?.name !== 'AbortError') showToast(error.message || '读取文件夹失败')
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
  if (skipped) showToast(`已跳过 ${skipped} 个私密、依赖或超过 50 MB 的文件`)
  if (!supported.length) {
    resetWorkspaceImport()
    showToast('没有可上传的文件')
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

function openFilePicker() {
  if (uploadBusy.value || sending.value) return
  requestPermission({
    kind: 'file-read',
    icon: FileText,
    title: '允许 Hotline 读取这个文件？',
    description: 'Hotline 会读取这份文件并上传到当前对话，用于回答你的问题。',
    scope: ['只读取你主动选择的文件', '文件会用于当前对话', '单个文件不超过 50 MB'],
    confirmLabel: '允许读取文件',
  })
}

function requestTextEdit(file) {
  requestPermission({
    kind: 'text-edit',
    icon: FileCode2,
    title: '允许 Hotline 编辑这份文本？',
    description: 'Hotline 会先展示修改内容，只有你允许后才会写入文件。',
    scope: [`文件：${file.path}`, '修改前会展示变更内容', '你可以随时取消这次操作'],
    confirmLabel: '允许编辑文本',
    target: file.path,
  })
}

function cancelPermission() {
  permissionRequest.value = null
}

function confirmPermission() {
  const request = permissionRequest.value
  permissionRequest.value = null
  if (!request) return
  if (request.kind === 'file-read') {
    fileInput.value?.click()
  } else if (request.kind === 'text-edit') {
    showToast(`已允许编辑「${request.target}」`)
  }
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
    const result = await importWorkspace(backendUrl.value, folderName, entries)
    const workspace = result.workspace
    projectGroups.value.push({ ...workspace, id: workspace.workspace_id, child: '', tasks: [] })
    selectedProjectName.value = workspace.name
    selectedProjectId.value = workspace.workspace_id
    projectFiles.value = entries.map((entry) => ({ name: entry.path, size: entry.size }))
    folderImportProgress.value = { done: entries.length, total: entries.length, current: '' }
    folderImportOpen.value = false
    resetWorkspaceImport()
    showWorkspacePanel.value = true
    workspacePanelTab.value = 'files'
    showToast(`已导入工作区「${workspace.name}」中的 ${result.files} 个文件`)
    openProjectNameDialog(selectedProjectName.value)
  } catch (error) {
    showToast(error.message || '文件夹上传失败，请检查文件服务')
  } finally {
    projectUploadBusy.value = false
  }
}

function addWorkspaceTask(project) {
  selectedProjectName.value = project.name
  selectedProjectId.value = project.id
  if (!project.tasks) project.tasks = []
  project.tasks.unshift({ id: makeId(), title: '新任务' })
  newSession()
  showToast(`已在工作区「${project.name}」中新建任务`)
}

function openProjectNameDialog(name) {
  projectNameOriginal.value = name
  projectNameDraft.value = name
  showProjectNameDialog.value = true
}

async function saveProjectName() {
  const name = projectNameDraft.value.trim() || projectNameOriginal.value || '新工作区'
  const project = projectGroups.value.find((item) => item.id === selectedProjectId.value)
  if (project?.id) {
    try {
      const result = await updateHarnessWorkspace(backendUrl.value, project.id, {
        name, repository: project.repository, branch: project.branch || 'main', revision: project.revision,
      })
      Object.assign(project, result.workspace)
    } catch (error) {
      showToast(error.message || '工作区重命名失败')
      return
    }
  }
  if (project) project.name = name
  if (selectedProjectName.value === projectNameOriginal.value) selectedProjectName.value = name
  showProjectNameDialog.value = false
  showToast(`项目已命名为「${name}」`)
}

function showNotifications() {
  showToast('暂无新通知')
}

function openMore() {
  activePage.value = 'profile'
  profileSection.value = 'basics'
  showWorkspacePanel.value = false
  mobileSidebarOpen.value = false
  refreshProfile()
  refreshCredential()
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

function sidebarToggleLabel() {
  if (window.matchMedia('(max-width: 960px)').matches) {
    return mobileSidebarOpen.value ? '关闭会话栏' : '打开会话栏'
  }
  return sidebarCollapsed.value ? '展开会话栏' : '收起会话栏'
}

function sidebarIsExpanded() {
  return window.matchMedia('(max-width: 960px)').matches ? mobileSidebarOpen.value : !sidebarCollapsed.value
}

async function refreshSessions() {
  try {
    const previous = new Map(sessions.value.map((session) => [session.id, session]))
    const records = await getSessions(backendUrl.value)
    const drafts = draftSessions()
    sessions.value = [
      ...drafts,
      ...records.map((item) => ({
        id: item.conversationId,
        title: previous.get(item.conversationId)?.title || titleFor(item.question || ''),
        agentType: item.agentType,
        fileId: item.fileid,
        workspaceId: previous.get(item.conversationId)?.workspaceId || item.workspaceId || '',
        updatedAt: item.createTime ? new Date(item.createTime).getTime() : 0,
        messages: previous.get(item.conversationId)?.messages || [],
        loaded: previous.get(item.conversationId)?.loaded || false,
      })),
    ]
    connectionState.value = 'online'
    connectionMessage.value = ''
  } catch (error) {
    connectionState.value = 'offline'
    connectionMessage.value = error.name === 'TimeoutError'
      ? '连接超时，请确认 Python 服务已启动并检查服务地址'
      : (error.message || '无法连接 Python 服务')
  }
}

function parseArray(value) {
  if (!value) return []
  if (Array.isArray(value)) return value
  try {
    const parsed = JSON.parse(value)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function normalizeReferences(value) {
  return parseArray(value).filter(Boolean).map((ref) => {
    if (typeof ref === 'string') {
      try { ref = JSON.parse(ref) } catch { ref = { url: ref, title: ref } }
    }
    const url = ref.url || ref.link || ''
    return { url: /^https?:\/\//i.test(url) ? url : (url ? `https://${url}` : ''), title: ref.title || ref.url || ref.link || '无标题', content: ref.content || '' }
  }).filter((ref) => ref.url)
}

async function selectSession(id) {
  if (sending.value && id !== activeId.value) return
  activeId.value = id
  mobileSidebarOpen.value = false
  const session = sessions.value.find((item) => item.id === id)
  selectedProjectId.value = session?.workspaceId || ''
  selectedProjectName.value = projectGroups.value.find(item => item.id === session?.workspaceId)?.name || ''
  if (!session || session.isDraft || session.loaded) {
    await scrollToBottom()
    return
  }
  loadingHistory.value = true
  try {
    const detail = await getSession(backendUrl.value, id)
    const history = []
    for (const row of detail.messages || []) {
      if (row.question) history.push({ id: `user-${row.id}`, role: 'user', content: row.question, fileName: row.fileid ? '已上传文件' : '', createdAt: row.createTime })
      if (row.answer || row.thinking) {
        history.push({
          id: `assistant-${row.id}`, role: 'assistant', content: normalizeBrandText(row.answer), done: true,
          timeline: row.thinking ? [{ type: 'thinking', content: normalizeBrandText(row.thinking) }] : [],
          references: normalizeReferences(row.reference), recommend: parseArray(row.recommend),
          showTimeline: false, showReferences: false, createdAt: row.createTime,
        })
      }
    }
    session.messages = history
    session.workspaceId = detail.workspaceId || session.workspaceId || ''
    selectedProjectId.value = session.workspaceId
    selectedProjectName.value = projectGroups.value.find(item => item.id === session.workspaceId)?.name || ''
    session.loaded = true
    session.agentType = detail.agentType || session.agentType
    activeMode.value = ['chat', 'file', 'ppt', 'deep', 'skills'].includes(session.agentType) ? session.agentType : 'chat'
  } catch (error) {
    showToast(error.message || '会话记录加载失败')
  } finally {
    loadingHistory.value = false
    await scrollToBottom()
  }
}

async function deleteConversation(id) {
  if (!id || deletingId.value) return
  deletingId.value = id
  try {
    await removeSession(backendUrl.value, id)
    sessions.value = sessions.value.filter((session) => session.id !== id)
    if (activeId.value === id) {
      activeId.value = null
      newSession()
    }
    showToast('会话已删除')
  } catch (error) {
    showToast(error.message || '删除失败')
  } finally {
    deletingId.value = null
  }
}

function chooseMode(id) {
  if (sending.value) return
  activeMode.value = id
  if (id !== 'file') {
    selectedFile.value = null
    uploadedFileId.value = null
    docSource.value = null
  }
}

function choosePrompt(text) {
  input.value = text
  nextTick(() => composer.value?.focus())
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

async function onFilePicked(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  const ext = file.name.split('.').pop().toLowerCase()
  if (!supportedExtensions.has(ext)) {
    showToast('支持 PDF、Word、TXT、PNG、JPG 文件')
    return
  }
  if (file.size > 50 * 1024 * 1024) {
    showToast('文件不能超过 50 MB')
    return
  }
  selectedFile.value = file
  activeMode.value = 'file'
  uploadBusy.value = true
  try {
    const uploaded = await uploadFile(backendUrl.value, file)
    uploadedFileId.value = uploaded.fileId
    showToast('文件已上传并完成解析')
  } catch (error) {
    selectedFile.value = null
    uploadedFileId.value = null
    showToast(error.message || '文件上传失败，请检查文件服务')
  } finally {
    uploadBusy.value = false
  }
}

function removeSelectedFile() {
  selectedFile.value = null
  uploadedFileId.value = null
  docSource.value = null
}

function askFromDoc(doc) {
  selectedFile.value = null
  uploadedFileId.value = null
  docSource.value = { fileId: doc.fileId, fileName: doc.fileName, charCount: doc.charCount }
  activeMode.value = 'file'
  showDocs.value = false
}

const STREAM_TICK_MS = 33
// 短回答放慢像真人在打字，长回答加快，避免等待过久
function streamChunkSize(pending) {
  if (pending.length > 400) return 6
  if (pending.length > 160) return 4
  return 2
}

// 上游可能极快地把整段答案推来，这里按字符节奏逐段显示，保证阅读时是逐步输出
function queueStreamText(message, text) {
  if (!text) return
  message.pendingText = (message.pendingText || '') + text
  if (message.typTimer) return
  let ticks = 0
  message.typTimer = setInterval(() => {
    const pending = message.pendingText || ''
    const size = streamChunkSize(pending)
    const take = pending.slice(0, size)
    message.pendingText = pending.slice(size)
    if (take) {
      message.content += take
      ticks += 1
      // 每三帧滚一次，避免频繁读取 scrollHeight 造成卡顿
      if (ticks % 3 === 0) scrollToBottom()
    }
    if (message.pendingText) return
    clearInterval(message.typTimer)
    message.typTimer = null
    completeStreamMessage(message)
  }, STREAM_TICK_MS)
}

function completeStreamMessage(message) {
  if (!message.streamEnded || message.pendingText) return
  if (message.timeline.some((entry) => entry.type === 'error')) return
  if (!message.done) {
    message.done = true
    message.showTimeline = false
  }
  scrollToBottom()
}

function finishStreamText(message) {
  message.streamEnded = true
  completeStreamMessage(message)
}

function appendStreamEvent(data, message) {
  if (!data || typeof data !== 'object') return
  if (appendProgressEvent(message, data)) return
  const content = data.content
  if (data.type === 'text' && content) {
    // 品牌词替换放在渲染层做，逐块替换会被流式切分打断
    const chunk = String(content)
    queueStreamText(message, chunk)
    const pptLink = chunk.match(/(?:下载文件|Download):\s*(https?:\/\/\S+|\/generated\/\S+|\/harness\/artifacts\/[^\s/]+\/download)/i)
    if (pptLink) message.pptFile = pptLink[1].replace(/[)\]，。]+$/, '')
  } else if (data.type === 'reference') {
    let references = content
    if (typeof references === 'string') {
      try { references = JSON.parse(references) } catch { references = [] }
    }
    message.references = normalizeReferences(references)
  } else if (data.type === 'recommend') {
    message.recommend = parseArray(content)
  } else if (data.type === 'clarify') {
    const payload = content && typeof content === 'object' ? content : {}
    const options = Array.isArray(payload.options) ? payload.options : []
    message.clarify = {
      question: String(payload.question || ''),
      options: options.map((item) => ({
        intent: String(item?.intent || ''),
        label: String(item?.label || ''),
        hint: String(item?.hint || ''),
      })),
      sent: false,
    }
    message.clarifyText = ''
  } else if (data.type === 'error') {
    finishProgress(message, 'failed')
    message.timeline.push({ type: 'error', message: data.message || (typeof content === 'string' ? content : '任务执行失败'), detail: data.detail || '', t0: Date.now(), endedAt: Date.now() })
    message.showTimeline = true
  } else if (data.type === 'complete') {
    finishProgress(message)
    finishStreamText(message)
    if (message.timeline.some((entry) => entry.type === 'error')) message.showTimeline = true
  }
}

async function sendMessage() {
  if (!canSend.value || !currentSession.value) return
  if (connectionState.value !== 'online') {
    showToast('Python 服务未连接，请先检查服务地址')
    return
  }
  const text = input.value.trim() || (uploadedFileId.value ? '请分析这个文件' : (docSource.value ? `请基于《${docSource.value.fileName}》回答` : ''))
  const fileId = uploadedFileId.value || docSource.value?.fileId || null
  const fileName = selectedFile.value?.name || docSource.value?.fileName || ''
  let session = currentSession.value
  const workspaceId = selectedProjectId.value
  const mode = activeMode.value
  if (session.messages.length && (session.workspaceId || '') !== workspaceId) {
    newSession()
    session = currentSession.value
    activeMode.value = mode
  }
  session.workspaceId = workspaceId
  session.isDraft = false
  session.loaded = true
  session.agentType = activeMode.value === 'skills' ? 'skills' : (fileId ? 'file' : activeMode.value)
  session.messages.push({ id: makeId(), role: 'user', content: text, fileName, createdAt: new Date().toISOString() })
  if (session.messages.filter((message) => message.role === 'user').length === 1) session.title = titleFor(text)
  session.messages.push({ id: makeId(), role: 'assistant', content: '', timeline: [], references: [], recommend: [], showTimeline: false, showReferences: false, done: false, t0: Date.now(), pendingText: '', typTimer: null, streamEnded: false, clarify: null, clarifyText: '' })
  // 取回响应式代理：直接写原始对象不会触发重渲染，流式增量就看不到
  const assistant = session.messages[session.messages.length - 1]
  appendProgressEvent(assistant, { type: 'step', stage: 'understanding', content: '正在理解问题', status: 'running' })
  input.value = ''
  removeSelectedFile()
  sending.value = true
  runStartedAt.value = Date.now()
  nowTick.value = Date.now()
  startTick()
  autoScroll.value = true
  await scrollToBottom()

  try {
    readerController = new AbortController()
    const response = await fetch(streamUrl(backendUrl.value, activeMode.value, text, session.id, fileId, session.workspaceId), {
      headers: { Accept: 'text/event-stream', 'Cache-Control': 'no-cache' },
      signal: readerController.signal,
    })
    if (!response.ok) {
      let message = `请求失败（HTTP ${response.status}）`
      try { message = (await response.json()).message || message } catch {}
      throw new Error(message)
    }
    if (!response.body) throw new Error('浏览器不支持流式响应')
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
      let boundary
      while ((boundary = buffer.indexOf('\n\n')) >= 0) {
        const frame = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        const data = frame.split('\n').filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trimStart()).join('\n')
        if (!data || data.trim() === '[DONE]') continue
        try { appendStreamEvent(JSON.parse(data), assistant) } catch { /* Ignore an incomplete or non-JSON event. */ }
        await scrollToBottom()
      }
    }
    if (buffer.trim()) {
      const data = buffer.split('\n').filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trimStart()).join('\n')
      if (data && data !== '[DONE]') {
        try { appendStreamEvent(JSON.parse(data), assistant) } catch {}
      }
    }
    session.updatedAt = Date.now()
    await refreshSessions()
  } catch (error) {
    if (error.name !== 'AbortError') {
      finishProgress(assistant, 'failed')
      assistant.timeline.push({ type: 'error', message: error.message || '请求失败', detail: '请检查 Python 后端、跨域设置及所选模式依赖。', t0: Date.now(), endedAt: Date.now() })
      assistant.showTimeline = true
    }
  } finally {
    finishStreamText(assistant)
    sending.value = false
    readerController = null
    stopTick()
    runStartedAt.value = 0
    finishProgress(assistant)
    if (!assistant.t1) assistant.t1 = Date.now()
    await scrollToBottom()
  }
}

async function stopMessage() {
  if (!sending.value || !currentSession.value) return
  try {
    await stopAgent(backendUrl.value, currentSession.value.id)
  } catch (error) {
    showToast(error.message || '停止请求未能送达后端')
  }
}

function submitFromKeyboard(event) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    sendMessage()
  }
}

function renderMarkdown(text) {
  if (!text) return ''
  const html = marked.parse(text.replace(/\\n/g, '\n').replace(/\\r/g, '\r'))
  return DOMPurify.sanitize(html, { USE_PROFILES: { html: true } })
}

function highlightCode(event) {
  const blocks = event?.target?.querySelectorAll?.('pre code') || []
  blocks.forEach((block) => {
    if (!block.dataset.highlighted) hljs.highlightElement(block)
  })
}

const vHighlight = { mounted: highlightCode, updated: highlightCode }

function sendRecommendation(question) {
  input.value = question
  sendMessage()
}

// 澄清作答：把选中的方向或补充说明作为新一轮提问带上原问题上下文。
function answerClarify(message, option) {
  const clarify = message?.clarify
  if (!clarify || clarify.sent || sending.value) return
  const lines = [`原问题：${clarify.question}`]
  if (option) lines.push(`我想要的是：${option.label}${option.hint ? `（${option.hint}）` : ''}`)
  const extra = (message.clarifyText || '').trim()
  if (extra) lines.push(`补充说明：${extra}`)
  clarify.sent = true
  input.value = lines.join('\n')
  sendMessage()
}

function clarifyKeydown(message, event) {
  if (event.key !== 'Enter' || event.shiftKey) return
  event.preventDefault()
  answerClarify(message, null)
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    showToast('已复制到剪贴板')
  } catch {
    showToast('复制失败，请检查浏览器权限')
  }
}

function downloadHref(file) {
  return /^https?:\/\//i.test(file) ? file : apiUrl(backendUrl.value, file)
}

async function saveSettings() {
  const value = settingsDraft.value.trim().replace(/\/+$/, '')
  if (value && !/^https?:\/\//i.test(value)) {
    showToast('留空恢复同源地址，或输入以 http:// 开头的服务地址')
    return
  }
  busySettings.value = true
  try {
    backendUrl.value = value
    if (value) localStorage.setItem('dodo-api-base', value)
    else localStorage.removeItem('dodo-api-base')
    await testBackend(value)
    connectionState.value = 'online'
    connectionMessage.value = ''
    showSettings.value = false
    showToast(value ? '服务连接正常' : '已恢复同源服务地址')
    await refreshSessions()
  } catch (error) {
    connectionState.value = 'offline'
    connectionMessage.value = error.message
    showToast(`连接失败：${error.message}`)
  } finally {
    busySettings.value = false
  }
}

async function retryConnection() {
  connectionState.value = 'checking'
  await refreshSessions()
}

async function refreshSkills() {
  try {
    skills.value = await getSkills(backendUrl.value)
  } catch (error) {
    skills.value = []
    skillMessage.value = { type: 'error', text: `技能列表加载失败：${error.message}` }
  }
}

function clearSkillEntry() {
  skillEntries.value = []
  skillEntryChoice.value = ''
  pendingSkillFile = null
}

async function refreshSchedules() {
  try {
    schedules.value = (await getSchedules(backendUrl.value))?.items || []
  } catch (error) {
    schedules.value = []
  }
}

function openScheduleForm() {
  scheduleDraft.value = { name: '', prompt: '', agent: 'chat', intervalMinutes: 60 }
  showScheduleForm.value = true
}

async function submitSchedule() {
  if (scheduleBusy.value) return
  if (!scheduleDraft.value.name.trim() || !scheduleDraft.value.prompt.trim()) {
    showToast('请填写任务名称和任务内容')
    return
  }
  scheduleBusy.value = true
  try {
    await createSchedule(backendUrl.value, {
      name: scheduleDraft.value.name.trim(),
      prompt: scheduleDraft.value.prompt.trim(),
      agent: scheduleDraft.value.agent,
      intervalMinutes: Number(scheduleDraft.value.intervalMinutes) || 60,
    })
    showScheduleForm.value = false
    await refreshSchedules()
    showToast('定时任务已创建')
  } catch (error) {
    showToast(`创建失败：${error.message || '定时任务服务不可用'}`)
  } finally {
    scheduleBusy.value = false
  }
}

async function toggleSchedule(task) {
  if (scheduleBusy.value) return
  scheduleBusy.value = true
  try {
    await updateSchedule(backendUrl.value, task.task_id, { enabled: !task.enabled })
    await refreshSchedules()
  } catch (error) {
    showToast(`更新失败：${error.message || '定时任务服务不可用'}`)
  } finally {
    scheduleBusy.value = false
  }
}

async function runScheduleNow(task) {
  if (scheduleBusy.value) return
  scheduleBusy.value = true
  try {
    const result = await runSchedule(backendUrl.value, task.task_id)
    await refreshSchedules()
    showToast(result?.run?.run_id ? `已提交运行 ${result.run.run_id}` : '已提交执行')
  } catch (error) {
    showToast(`执行失败：${error.message || '执行服务不可用'}`)
  } finally {
    scheduleBusy.value = false
  }
}

async function removeSchedule(task) {
  if (!window.confirm(`删除定时任务 ${task.name}？`)) return
  try {
    await deleteSchedule(backendUrl.value, task.task_id)
    await refreshSchedules()
    showToast(`已删除 ${task.name}`)
  } catch (error) {
    showToast(`删除失败：${error.message || '定时任务服务不可用'}`)
  }
}

async function refreshBots() {
  try {
    bots.value = await getBots(backendUrl.value)
  } catch (error) {
    bots.value = []
  }
}

function openBotForm(bot) {
  botDraft.value = bot
    ? { botId: bot.bot_id, name: bot.name, instruction: bot.instruction || '', skills: [...(bot.skills || [])], enabled: bot.enabled }
    : { botId: '', name: '', instruction: '', skills: [], enabled: true }
  showBotForm.value = true
}

async function submitBot() {
  if (botBusy.value) return
  if (!botDraft.value.name.trim()) {
    showToast('请填写机器人名称')
    return
  }
  botBusy.value = true
  const payload = {
    name: botDraft.value.name.trim(),
    instruction: botDraft.value.instruction.trim(),
    skills: botDraft.value.skills,
    enabled: botDraft.value.enabled,
  }
  try {
    if (botDraft.value.botId) await updateBot(backendUrl.value, botDraft.value.botId, payload)
    else await createBot(backendUrl.value, payload)
    showBotForm.value = false
    await refreshBots()
    showToast('机器人已保存')
  } catch (error) {
    showToast(`保存失败：${error.message || '机器人服务不可用'}`)
  } finally {
    botBusy.value = false
  }
}

async function toggleBot(bot) {
  if (botBusy.value) return
  botBusy.value = true
  try {
    await updateBot(backendUrl.value, bot.bot_id, {
      name: bot.name,
      instruction: bot.instruction || '',
      skills: bot.skills || [],
      enabled: !bot.enabled,
    })
    await refreshBots()
  } catch (error) {
    showToast(`更新失败：${error.message || '机器人服务不可用'}`)
  } finally {
    botBusy.value = false
  }
}

async function removeBot(bot) {
  if (!window.confirm(`删除机器人 ${bot.name}？`)) return
  try {
    await deleteBot(backendUrl.value, bot.bot_id)
    await refreshBots()
    showToast(`已删除 ${bot.name}`)
  } catch (error) {
    showToast(`删除失败：${error.message || '机器人服务不可用'}`)
  }
}

async function bindBot(bot, conversationId) {
  if (!conversationId) return
  try {
    await bindBotSession(backendUrl.value, bot.bot_id, conversationId)
    showToast('已绑定会话，该会话的回答会使用这个人设')
  } catch (error) {
    showToast(`绑定失败：${error.message || '机器人服务不可用'}`)
  }
}

function applyTheme(theme) {
  const root = document.documentElement
  if (theme === 'light' || theme === 'dark') root.setAttribute('data-theme', theme)
  else root.removeAttribute('data-theme')
}

async function refreshProfile() {
  try {
    const profile = await getProfile(backendUrl.value)
    profileDraft.value = {
      nickname: profile.nickname || '',
      bio: profile.bio || '',
      answerStyle: profile.answerStyle || 'default',
      theme: profile.theme || 'system',
    }
    applyTheme(profileDraft.value.theme)
  } catch (error) {
    // 后端不可用时保持当前界面，不写入假的默认值。
  }
}

async function saveProfileBasics() {
  if (profileBusy.value) return
  profileBusy.value = true
  try {
    await saveProfile(backendUrl.value, {
      nickname: profileDraft.value.nickname.trim(),
      bio: profileDraft.value.bio.trim(),
    })
    showToast('个人资料已保存')
  } catch (error) {
    showToast(`保存失败：${error.message || '个人设置服务不可用'}`)
  } finally {
    profileBusy.value = false
  }
}

async function savePreferences() {
  if (profileBusy.value) return
  profileBusy.value = true
  try {
    await saveProfile(backendUrl.value, {
      answerStyle: profileDraft.value.answerStyle,
      theme: profileDraft.value.theme,
    })
    applyTheme(profileDraft.value.theme)
    showToast('偏好已保存')
  } catch (error) {
    showToast(`保存失败：${error.message || '个人设置服务不可用'}`)
  } finally {
    profileBusy.value = false
  }
}

async function refreshCredential() {
  try {
    const credential = await getCredential(backendUrl.value)
    credentialDraft.value = {
      provider: credential?.provider || '',
      baseUrl: credential?.base_url || '',
      model: credential?.model || '',
      apiKey: '',
    }
    credentialMask.value = credential?.apiKey || ''
  } catch (error) {
    credentialMask.value = ''
  }
}

function credentialPayload() {
  const payload = {
    provider: credentialDraft.value.provider.trim(),
    baseUrl: credentialDraft.value.baseUrl.trim(),
    model: credentialDraft.value.model.trim(),
  }
  if (credentialDraft.value.apiKey.trim()) payload.apiKey = credentialDraft.value.apiKey.trim()
  return payload
}

async function saveCredentialForm() {
  if (credentialBusy.value) return
  credentialBusy.value = true
  try {
    await saveCredential(backendUrl.value, credentialPayload())
    credentialDraft.value.apiKey = ''
    await refreshCredential()
    showToast('模型凭证已保存')
  } catch (error) {
    showToast(`保存失败：${error.message || '凭证服务不可用'}`)
  } finally {
    credentialBusy.value = false
  }
}

async function testCredentialForm() {
  if (credentialBusy.value) return
  credentialBusy.value = true
  try {
    const result = await testCredential(backendUrl.value, credentialPayload())
    showToast(result?.ok ? '模型连接正常' : (result?.message || '模型连接失败'))
  } catch (error) {
    showToast(`测试失败：${error.message || '凭证服务不可用'}`)
  } finally {
    credentialBusy.value = false
  }
}

async function removeCredential() {
  if (!window.confirm('删除已保存的模型凭证？')) return
  try {
    await deleteCredential(backendUrl.value)
    await refreshCredential()
    showToast('已删除模型凭证')
  } catch (error) {
    showToast(`删除失败：${error.message || '凭证服务不可用'}`)
  }
}

async function togglePlugin(skill) {
  try {
    await setSkillEnabled(backendUrl.value, skill.id, !skill.enabled)
    await refreshSkills()
    showToast(skill.enabled ? `已停用 ${skill.name}` : `已启用 ${skill.name}`)
  } catch (error) {
    showToast(`操作失败：${error.message || '技能服务不可用'}`)
  }
}

async function removePlugin(skill) {
  if (!window.confirm(`删除技能包 ${skill.name}？`)) return
  try {
    await removeSkill(backendUrl.value, skill.id)
    await refreshSkills()
    showToast(`已删除 ${skill.name}`)
  } catch (error) {
    showToast(`删除失败：${error.message || '技能服务不可用'}`)
  }
}

function togglePet() {
  petEnabled.value = !petEnabled.value
  localStorage.setItem('hotline-pet-enabled', petEnabled.value ? '1' : '0')
}

function choosePet(id) {
  petChoice.value = id
  localStorage.setItem('hotline-pet', id)
}

function openSkills() {
  showSkills.value = true
  skillMessage.value = null
  clearSkillEntry()
  refreshSkills()
}

function closeSkills() {
  showSkills.value = false
  skillMessage.value = null
  clearSkillEntry()
}

async function installSkill(file, entry) {
  skillBusy.value = true
  skillMessage.value = null
  try {
    const result = await uploadSkill(backendUrl.value, file, entry)
    if (result.success) {
      clearSkillEntry()
      skillMessage.value = { type: 'ok', text: `技能「${result.skill.name}」已安装并启用` }
      await refreshSkills()
    } else {
      skillMessage.value = { type: 'error', text: result.message }
      skillEntries.value = result.entries
      skillEntryChoice.value = ''
      pendingSkillFile = file
    }
  } catch (error) {
    skillMessage.value = { type: 'error', text: `上传失败：${error.message}` }
  } finally {
    skillBusy.value = false
  }
}

function chooseSkillZip(event) {
  const file = event.target.files[0]
  event.target.value = ''
  if (file) installSkill(file, '')
}

function confirmSkillEntry() {
  if (pendingSkillFile && skillEntryChoice.value) installSkill(pendingSkillFile, skillEntryChoice.value)
}

async function toggleSkill(skill) {
  try {
    await setSkillEnabled(backendUrl.value, skill.id, !skill.enabled)
    await refreshSkills()
  } catch (error) {
    skillMessage.value = { type: 'error', text: `操作失败：${error.message}` }
  }
}

async function confirmRemoveSkill(skill) {
  try {
    await removeSkill(backendUrl.value, skill.id)
    deletingSkill.value = null
    skillMessage.value = { type: 'ok', text: `技能「${skill.name}」已删除` }
    await refreshSkills()
  } catch (error) {
    skillMessage.value = { type: 'error', text: `删除失败：${error.message}` }
  }
}

const DOC_STATUS = {
  PENDING: '待转换', CONVERTING: '解析中', CONVERTED: '已转换',
  VECTORIZING: '向量化中', VECTORIZED: '已向量化', FAILED: '失败',
}

function docStatusLabel(status) {
  return DOC_STATUS[status] || status || '未知'
}

function docStatusClass(status) {
  if (status === 'FAILED') return 'bad'
  if (status === 'VECTORIZED') return 'on'
  if (['CONVERTING', 'VECTORIZING'].includes(status)) return 'working'
  return ''
}

function stopDocPolling() {
  clearTimeout(docPollTimer)
  docPollTimer = null
}

function scheduleDocPolling() {
  stopDocPolling()
  if (!showDocs.value || !docs.value.some((doc) => ['CONVERTING', 'VECTORIZING'].includes(doc.status))) return
  docPollTimer = setTimeout(() => refreshDocs(), 1400)
}

async function refreshDocs() {
  try {
    docs.value = await getDocuments(backendUrl.value)
  } catch (error) {
    docMessage.value = { type: 'error', text: `读取文档列表失败：${error.message}` }
  } finally {
    scheduleDocPolling()
  }
}

async function openDocs() {
  showDocs.value = true
  docMessage.value = null
  await refreshDocs()
}

function closeDocs() {
  showDocs.value = false
  docBusy.value = false
  stopDocPolling()
}

async function openDocPreview(doc) {
  showDocs.value = false
  stopDocPolling()
  previewDoc.value = doc
  docPreview.value = null
  docPreviewError.value = ''
  docPreviewTab.value = 'chunks'
  showDocPreview.value = true
  docPreviewBusy.value = true
  try {
    docPreview.value = await getDocumentPreview(backendUrl.value, doc.fileId)
  } catch (error) {
    docPreviewError.value = error.message || '读取预览失败'
  } finally {
    docPreviewBusy.value = false
  }
}

function closeDocPreview(returnToDocs = true) {
  showDocPreview.value = false
  previewDoc.value = null
  docPreview.value = null
  docPreviewError.value = ''
  if (returnToDocs) {
    showDocs.value = true
    refreshDocs()
  }
}

async function submitDocument(file) {
  docBusy.value = true
  docMessage.value = { type: 'info', text: `正在转换「${file.name}」… PDF/Word 要走 MinerU 解析，可能需要几分钟` }
  try {
    const record = await uploadDocument(backendUrl.value, file)
    const notes = record.errorMsg ? `；${record.errorMsg}` : ''
    docMessage.value = {
      type: 'ok',
      text: `「${record.fileName}」已转换为 Markdown：${record.imageCount} 张图已托管，${record.captionCount} 张有描述${notes}`,
    }
    await refreshDocs()
  } catch (error) {
    docMessage.value = { type: 'error', text: `转换失败：${error.message}` }
  } finally {
    docBusy.value = false
  }
}

function chooseDocFile(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (file) submitDocument(file)
}

async function runVectorize(doc) {
  docBusy.value = true
  docMessage.value = { type: 'info', text: `正在对「${doc.fileName}」做父子分段并向量化…` }
  try {
    const result = await vectorizeDocument(backendUrl.value, doc.fileId)
    if (result.alreadyVectorized) {
      docMessage.value = { type: 'ok', text: `「${doc.fileName}」已经完成向量化，无需重复操作` }
      await refreshDocs()
      return
    }
    if (result.inProgress) {
      docMessage.value = { type: 'info', text: `「${doc.fileName}」正在向量化，请稍后` }
      await refreshDocs()
      return
    }
    docMessage.value = { type: 'ok', text: `已向量化：${result.children} 个子分段（其中 ${result.parents} 个父分段存库不向量化）` }
    await refreshDocs()
  } catch (error) {
    docMessage.value = { type: 'error', text: `向量化失败：${error.message}` }
  } finally {
    docBusy.value = false
  }
}

async function runCompensation() {
  docBusy.value = true
  try {
    const outcomes = await compensateDocuments(backendUrl.value)
    docMessage.value = { type: 'ok', text: outcomes.length ? `兜底补偿检查了 ${outcomes.length} 个待处理文档` : '没有需要补偿的文档' }
    await refreshDocs()
  } catch (error) {
    docMessage.value = { type: 'error', text: `补偿失败：${error.message}` }
  } finally {
    docBusy.value = false
  }
}

async function toggleDocVersions(doc) {
  if (expandingDoc.value === doc.fileId) {
    expandingDoc.value = null
    return
  }
  expandingDoc.value = doc.fileId
  if (docVersions.value[doc.fileId]) return
  try {
    docVersions.value = { ...docVersions.value, [doc.fileId]: await getDocumentVersions(backendUrl.value, doc.fileId) }
  } catch (error) {
    docMessage.value = { type: 'error', text: `读取版本失败：${error.message}` }
  }
}

async function confirmRemoveDoc(doc) {
  try {
    await removeDocument(backendUrl.value, doc.fileId)
    deletingDoc.value = null
    docMessage.value = { type: 'ok', text: `「${doc.fileName}」已删除` }
    await refreshDocs()
  } catch (error) {
    docMessage.value = { type: 'error', text: `删除失败：${error.message}` }
  }
}

async function scrollToBottom() {
  await nextTick()
  const list = messageList.value
  if (!list || !autoScroll.value) return
  list.scrollTop = list.scrollHeight
}

function onUserScroll() {
  const list = messageList.value
  if (!list) return
  autoScroll.value = list.scrollHeight - list.scrollTop - list.clientHeight < 48
}

function toggleSearch() {
  searchOpen.value = !searchOpen.value
  if (!searchOpen.value) searchText.value = ''
}

watch(() => currentSession.value?.messages.length, () => scrollToBottom())
watch([input, composer], async () => {
  await nextTick()
  if (composer.value) {
    composer.value.style.height = 'auto'
    composer.value.style.height = `${Math.min(composer.value.scrollHeight, 180)}px`
  }
})

onMounted(() => {
  keydownHandler = (event) => {
    if (appTopDialog()) {
      if (event.key === 'Escape') {
        event.preventDefault()
        // 点遮罩复用各弹窗自己的关闭逻辑，保存或上传进行中不会被误关
        appDialogBackdrops().pop()?.click()
      } else if (event.key === 'Tab') {
        const controls = appDialogControls(appTopDialog())
        const first = controls[0]
        const last = controls[controls.length - 1]
        if (!first) event.preventDefault()
        else if (!controls.includes(document.activeElement) || (event.shiftKey && document.activeElement === first) || (!event.shiftKey && document.activeElement === last)) {
          event.preventDefault()
          const nextControl = event.shiftKey ? last : first
          nextControl.focus()
        }
      }
      return
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault()
      newSession()
    }
    if (event.key === 'Escape') mobileSidebarOpen.value = false
  }
  window.addEventListener('keydown', keydownHandler)
  newSession()
  refreshSessions()
  refreshWorkspaces()
  getSkills(backendUrl.value).then((list) => { skills.value = list }).catch(() => {})
  refreshProfile()
})

onUnmounted(() => {
  window.removeEventListener('keydown', keydownHandler)
  stopDocPolling()
})
</script>

<template>
  <div class="app-shell" :class="{ 'chat-page': activePage === 'home', 'sidebar-collapsed': sidebarCollapsed, 'standalone-page-active': activePage !== 'home' }">
    <div v-if="mobileSidebarOpen" class="drawer-backdrop" @click="mobileSidebarOpen = false"></div>
    <aside class="app-rail" aria-label="主导航">
      <button class="rail-button" :class="{ active: activePage === 'home' }" type="button" aria-label="首页" title="首页" @click="openHome"><Home :size="20" fill="currentColor" /></button>
      <button class="rail-button" :class="{ active: activePage === 'automation' }" type="button" aria-label="自动化" title="自动化" @click="openAutomation"><CalendarClock :size="20" /></button>
      <button class="rail-button" :class="{ active: activePage === 'plugins' }" type="button" aria-label="插件" title="插件" @click="openPlugins"><Puzzle :size="20" /></button>
      <button class="rail-button" :class="{ active: activePage === 'bot' }" type="button" aria-label="轻量机器人" title="轻量机器人" @click="openBotPage"><Bot :size="20" /></button>
      <button class="rail-button" :class="{ active: activePage === 'docs' }" type="button" aria-label="文档库" title="文档库" @click="openDocsPage"><LibraryBig :size="20" /></button>
      <button class="rail-button" :class="{ active: activePage === 'harness' }" type="button" aria-label="Harness 工程" title="Harness 工程" @click="openHarnessPage"><Workflow :size="20" /></button>
      <button class="rail-button" :class="{ active: activePage === 'code-map' }" type="button" aria-label="代码地图" title="代码地图" @click="openCodeMapPage"><MapIcon :size="20" /></button>
      <button class="rail-button" :class="{ active: activePage === 'export' }" type="button" aria-label="导出历史聊天" title="导出历史聊天" @click="openExportPage"><History :size="20" /></button>
      <button class="rail-profile" type="button" aria-label="用户设置" title="用户设置" @click="openMore"><CircleUserRound :size="19" :stroke-width="1.9" /></button>
    </aside>
    <aside id="conversation-sidebar" class="sidebar" :class="{ 'sidebar-open': mobileSidebarOpen }" aria-label="会话导航">
      <div class="sidebar-top">
        <div class="brand-row">
          <div class="brand-mark"><Headset :size="18" :stroke-width="2" /></div>
          <span class="brand-name">Hotline</span>
          <div class="brand-actions">
            <button class="icon-button" type="button" aria-label="通知" title="通知" @click="showNotifications"><Bell :size="17" /></button>
            <button class="icon-button" type="button" :aria-label="searchOpen ? '关闭搜索' : '搜索会话'" @click="toggleSearch"><Search :size="17" /></button>
            <button class="icon-button mobile-close" type="button" aria-label="关闭会话栏" @click="mobileSidebarOpen = false"><X :size="18" /></button>
          </div>
        </div>

        <nav class="quick-nav" aria-label="快捷入口">
          <button class="nav-item" type="button" @click="newSession"><Plus :size="18" /><span>新对话</span><kbd>Ctrl K</kbd></button>
        </nav>

        <section class="project-nav" aria-label="工作区">
          <h2 class="project-nav-heading"><span>工作区</span><button class="icon-button workspace-add" type="button" :disabled="projectUploadBusy" aria-label="添加工作区" title="添加工作区" @click="addWorkspace"><Plus :size="16" /></button></h2>
          <div v-for="project in projectGroups" :key="project.id" class="project-entry" :class="{ selected: selectedProjectId === project.id }">
            <div class="project-line">
              <button type="button" class="project-open" :aria-label="`打开工作区：${project.name}`" @click="selectedProjectName = project.name; selectedProjectId = project.id; openProjectView()"><FolderOpen :size="18" /><span>{{ project.name }}</span></button>
              <button class="project-add-task icon-button" type="button" :disabled="projectUploadBusy" :aria-label="`在工作区添加任务：${project.name}`" :title="`添加任务到 ${project.name}`" @click="addWorkspaceTask(project)"><Plus :size="15" /></button>
            </div>
            <div v-if="project.child" class="project-child">{{ project.child }}</div>
            <button v-for="task in project.tasks || []" :key="task.id" type="button" class="project-task" @click="selectedProjectName = project.name; selectedProjectId = project.id; openHome()"><CircleDot :size="11" /><span>{{ task.title }}</span></button>
          </div>
          <p v-if="!projectGroups.length" class="workspace-empty">暂无工作区，点击 + 添加文件夹</p>
        </section>
        <input ref="projectFolderInput" class="visually-hidden" type="file" webkitdirectory directory multiple @change="onProjectFolderPicked" />

        <label v-if="searchOpen" class="session-search"><Search :size="15" /><input v-model="searchText" autofocus placeholder="搜索会话" /><button class="icon-button" aria-label="清除搜索" @click="searchText = ''"><X :size="14" /></button></label>
      </div>

      <nav class="session-list" aria-label="历史会话">
        <template v-if="runningItem.length">
          <div class="session-heading"><span>运行中</span></div>
          <div v-for="session in runningItem" :key="session.id" class="session-item task-card running" :class="{ active: activeId === session.id }">
            <button class="session-select" type="button" @click="selectSession(session.id)">
              <span class="session-dot"><span class="dot run"></span></span>
              <span class="session-main">
                <span class="session-title-row"><span class="session-title">{{ session.title }}</span><span class="mono-time">{{ runningElapsed }}</span></span>
                <span class="session-meta"><span class="badge" :class="badgeInfo(session.agentType).cls">{{ badgeInfo(session.agentType).label }}</span><span class="meta-note">正在执行</span></span>
              </span>
            </button>
          </div>
        </template>
        <div class="session-heading recent-heading"><span>最近</span><ChevronDown :size="16" /><span class="recent-heading-actions"><button class="icon-button" type="button" aria-label="最近会话更多"><MoreHorizontal :size="17" /></button><button class="icon-button" type="button" aria-label="新建最近会话" @click="newSession"><Plus :size="17" /></button></span></div>
        <div v-for="session in recentList" :key="session.id" class="session-item task-card" :class="{ active: activeId === session.id }">
          <button class="session-select" type="button" @click="selectSession(session.id)">
            <span class="session-dot"><span class="dot ok"></span></span>
            <span class="session-main">
              <span class="session-title-row"><span class="session-title">{{ session.title }}</span></span>
              <span class="session-meta"><span class="badge" :class="badgeInfo(session.agentType).cls">{{ badgeInfo(session.agentType).label }}</span><span class="meta-note">{{ fmtRelTime(session.createTime || session.updatedAt) }}</span></span>
            </span>
          </button>
          <button v-if="!session.isDraft" class="session-delete icon-button" type="button" :disabled="!!deletingId" :aria-label="`删除会话：${session.title}`" @click.stop="deleteConversation(session.id)"><Trash2 :size="15" /></button>
        </div>
        <div v-if="recentList.length === 0" class="session-empty">{{ searchText ? '没有匹配的会话' : '还没有历史会话' }}</div>
      </nav>

    </aside>

    <main class="workspace" :class="{ 'workspace-panel-open': showWorkspacePanel, 'workspace-welcome': isWelcome, 'workspace-code-map': activePage === 'code-map' }">
      <template v-if="activePage === 'home'">
      <header class="topbar">
        <div class="topbar-left">
          <button class="icon-button sidebar-toggle" type="button" aria-controls="conversation-sidebar" :aria-expanded="sidebarIsExpanded()" :aria-label="sidebarToggleLabel()" :title="sidebarToggleLabel()" @click="toggleSidebar"><PanelLeft :size="19" /></button>
          <div v-if="currentSession && currentSession.title !== '新对话'" class="breadcrumb"><FolderOpen :size="21" /><strong>{{ currentSession.title }}</strong></div>
          <span v-else class="topbar-title">新对话</span>
        </div>
      </header>

      <section ref="messageList" class="message-list" aria-label="对话内容" @scroll="onUserScroll">
        <div v-if="loadingHistory" class="history-loading"><LoaderCircle :size="18" class="spin" /> 正在加载会话记录</div>

        <div v-if="isWelcome" class="welcome-state">
          <div class="welcome-mark"><Headset :size="24" :stroke-width="1.6" /></div>
          <h1>你好，我是 Hotline</h1>

        </div>

        <div v-for="message in currentSession?.messages || []" :key="message.id" class="message-row" :class="`message-${message.role}`">
          <div v-if="message.role === 'assistant'" class="assistant-avatar"><MessagesSquare :size="15" /></div>
          <div class="message-body">
            <div class="message-meta"><strong>{{ message.role === 'user' ? '你' : 'Hotline' }}</strong><time v-if="message.createdAt">{{ new Date(message.createdAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }}</time><span v-if="message.role === 'assistant' && message.showTimeline && messageIsStreaming(message)" class="stream-status" role="status" aria-live="polite"><span class="status-dot"></span>{{ progressLabel(message) }}</span></div>
            <div v-if="message.fileName" class="message-attachment"><File :size="15" /><span>{{ message.fileName }}</span></div>

            <section v-if="message.role === 'assistant' && message.timeline?.length" class="timeline-block">
              <button class="disclosure-button" type="button" :aria-expanded="message.showTimeline" @click="message.showTimeline = !message.showTimeline">
                <span class="tl-dot" :class="{ run: messageIsStreaming(message), err: message.timeline.some((entry) => entry.type === 'error'), ok: message.done && !message.timeline.some((entry) => entry.type === 'error') }"></span>
                <span>{{ message.timeline.some((entry) => entry.type === 'error') ? '执行记录 · 有异常' : (message.done ? '处理过程' : '处理进度') }}</span>
                <span class="timeline-count mono-time">{{ timelineSummary(message) }}</span>
                <component :is="message.showTimeline ? ChevronDown : ChevronRight" :size="15" class="disclosure-chevron" />
              </button>
              <div v-if="message.showTimeline" class="timeline-content">
                <div v-for="(entry, index) in message.timeline" :key="index" class="timeline-entry" :class="`entry-${entry.type}`">
                  <span class="timeline-marker" :class="{ 'is-error': entry.type === 'error' || ['failed', 'cancelled'].includes(entry.status) }"><AlertCircle v-if="entry.type === 'error' || ['failed', 'cancelled'].includes(entry.status)" :size="12" /><LoaderCircle v-else-if="entry.status === 'running' && entry.endedAt == null" :size="12" class="spin" /><Check v-else-if="entry.endedAt != null" :size="12" /><span v-else></span></span>
                  <div v-if="entry.type === 'thinking' || entry.type === 'step'" class="timeline-thinking"><span>{{ progressEntryLabel(entry) }}</span><ul v-if="entry.sources?.length" class="progress-sources"><li v-for="(source, sourceIndex) in entry.sources" :key="sourceIndex">{{ source }}</li></ul></div>
                  <div v-else-if="entry.type === 'error'" class="timeline-error"><strong>{{ entry.message }}</strong><span v-if="entry.detail">{{ entry.detail }}</span></div>
                  <div v-else class="timeline-tool"><span class="progress-entry-label">{{ progressEntryLabel(entry) }}</span><span>{{ ({ running: '运行中', completed: '已完成', failed: '调用失败', cancelled: '已停止' })[entry.status] || entry.status }}</span></div>
                  <span v-if="entry.endedAt && entry.t0" class="entry-duration">{{ fmtStep(entry.endedAt - entry.t0) }}</span>
                </div>
              </div>
            </section>

            <div v-if="message.content" v-highlight class="markdown-content" v-html="renderMarkdown(normalizeBrandText(message.content))"></div>
            <div v-else-if="message.role === 'assistant' && messageIsStreaming(message) && !message.timeline?.length" class="thinking-placeholder"><span></span><span></span><span></span></div>

            <section v-if="message.role === 'assistant' && message.clarify" class="clarify-card" aria-label="需求澄清">
              <div class="clarify-head"><MessageCircle :size="15" /><strong>需要先确认一下</strong><span>不确定你想要哪种结果，选一个方向，或在下面直接补充说明</span></div>
              <div class="clarify-options">
                <button v-for="option in message.clarify.options" :key="option.intent" type="button" class="clarify-option" :disabled="message.clarify.sent || sending" @click="answerClarify(message, option)">
                  <span class="clarify-option-label">{{ option.label }}</span>
                  <span class="clarify-option-hint">{{ option.hint }}</span>
                </button>
              </div>
              <div v-if="!message.clarify.sent" class="clarify-free">
                <textarea v-model="message.clarifyText" rows="2" placeholder="也可以直接写下你的想法…" aria-label="补充说明" @keydown="clarifyKeydown(message, $event)"></textarea>
                <button type="button" class="clarify-send" :disabled="sending || !message.clarifyText.trim()" @click="answerClarify(message, null)">按我的说明继续</button>
              </div>
              <p v-else class="clarify-note">已按你的选择继续提问。</p>
            </section>

            <section v-if="message.references?.length" class="references-block">
              <button class="disclosure-button" type="button" :aria-expanded="message.showReferences" @click="message.showReferences = !message.showReferences"><Link2 :size="15" /><span>参考来源</span><span class="timeline-count">{{ message.references.length }}</span><component :is="message.showReferences ? ChevronDown : ChevronRight" :size="15" class="disclosure-chevron" /></button>
              <div v-if="message.showReferences" class="reference-list">
                <a v-for="ref in message.references" :key="ref.url" :href="ref.url" target="_blank" rel="noopener noreferrer" class="reference-link"><span class="reference-copy"><strong>{{ ref.title }}</strong><small>{{ ref.url }}</small></span><ExternalLink :size="14" /></a>
              </div>
            </section>

            <a v-if="message.pptFile" class="download-link" :href="downloadHref(message.pptFile)" download><Download :size="16" /> 下载生成的 PPT</a>
            <div v-if="message.role === 'assistant' && message.recommend?.length" class="recommendations"><span class="recommend-label">接下来可以</span><button v-for="(question, index) in message.recommend" :key="index" type="button" @click="sendRecommendation(question)">{{ question }}<ArrowUp :size="13" /></button></div>
            <button v-if="message.role === 'assistant' && message.content" class="copy-message icon-button" type="button" aria-label="复制回答" title="复制回答" @click="copyText(normalizeBrandText(message.content))"><Copy :size="14" /></button>
          </div>
          <div v-if="message.role === 'user'" class="user-avatar">你</div>
        </div>
      </section>

      <footer class="composer-area">
        <div class="composer-wrap">
          <div class="mode-strip" role="tablist" aria-label="助手模式">
            <button v-for="mode in modes" :key="mode.id" class="mode-option" :class="{ selected: activeMode === mode.id }" role="tab" :aria-selected="activeMode === mode.id" type="button" :disabled="sending" @click="chooseMode(mode.id)">
              <component :is="mode.icon" :size="16" /><span>{{ mode.label }}</span><Check v-if="activeMode === mode.id" :size="13" class="mode-check" />
            </button>
          </div>

          <div class="composer-box" :class="{ 'composer-focused': input.length > 0 || selectedFile || docSource, 'composer-disabled': uploadBusy }">
            <div v-if="selectedFile" class="attachment-chip"><div class="attachment-icon"><FileText :size="16" /></div><div class="attachment-info"><strong>{{ selectedFile.name }}</strong><small>{{ uploadBusy ? '正在上传并解析' : `${formatBytes(selectedFile.size)} · 已就绪` }}</small></div><LoaderCircle v-if="uploadBusy" :size="16" class="spin attachment-spinner" /><button v-else class="icon-button" type="button" aria-label="移除文件" @click="removeSelectedFile"><X :size="16" /></button></div>
            <div v-else-if="docSource" class="attachment-chip"><div class="attachment-icon"><FileText :size="16" /></div><div class="attachment-info"><strong>{{ docSource.fileName }}</strong><small>文档库 · {{ docSource.charCount }} 字 · 按父子分段检索</small></div><button class="icon-button" type="button" aria-label="移除文档来源" @click="docSource = null"><X :size="16" /></button></div>
            <textarea ref="composer" v-model="input" rows="1" :disabled="sending || uploadBusy" :placeholder="docSource ? `想问《${docSource.fileName}》里的什么？` : selectedFile ? '描述你想了解文件的什么内容…' : activeMode === 'ppt' ? '描述你想制作的演示文稿…' : '给 Hotline 发消息…'" aria-label="输入消息" @keydown="submitFromKeyboard" />
            <div class="composer-bottom">
              <div class="composer-tools">
                <input ref="fileInput" class="visually-hidden" type="file" accept=".pdf,.doc,.docx,.txt,.png,.jpg,.jpeg" @change="onFilePicked" />
                <button class="attach-button icon-button" type="button" :disabled="uploadBusy || sending" aria-label="上传文件" title="上传文件" @click="openFilePicker"><Paperclip :size="17" /></button>
                <span class="composer-hint"><kbd>Enter</kbd> 发送 <span class="hint-divider"></span><kbd>Shift Enter</kbd> 换行</span>
              </div>
              <div class="send-actions">
                <span v-if="input.length" class="char-count">{{ input.length }}</span>
                <button v-if="sending" class="send-button stop-button" type="button" aria-label="停止生成" title="停止生成" @click="stopMessage"><Square :size="15" fill="currentColor" /></button>
                <button v-else class="send-button" type="button" aria-label="发送消息" title="发送消息" :disabled="!canSend" @click="sendMessage"><ArrowUp :size="18" /></button>
              </div>
            </div>
          </div>
          <div v-if="isWelcome" class="quick-prompts" aria-label="试试这些任务">
            <button v-for="prompt in quickPrompts" :key="prompt.text" class="quick-prompt" type="button" @click="choosePrompt(prompt.text)">
              <component :is="prompt.icon" :size="15" /><span>{{ prompt.text }}</span><ArrowUp :size="13" class="prompt-arrow" />
            </button>
          </div>
        </div>
      </footer>

      <aside v-if="showWorkspacePanel" class="changes-panel" aria-label="文件与变更">
        <header class="changes-panel-header">
          <div><strong>{{ selectedProjectName }}</strong><span>{{ projectUploadBusy ? '正在上传文件夹…' : '当前项目文件' }}</span></div>
          <button class="icon-button" type="button" aria-label="关闭文件面板" @click="showWorkspacePanel = false"><X :size="17" /></button>
        </header>
        <div class="changes-tabs" role="tablist">
          <button type="button" :class="{ active: workspacePanelTab === 'files' }" @click="workspacePanelTab = 'files'"><FileCode2 :size="15" />文件</button>
          <button type="button" :class="{ active: workspacePanelTab === 'changes' }" @click="workspacePanelTab = 'changes'"><GitCompare :size="15" />变更 <span>3</span></button>
        </div>
        <div v-if="workspacePanelTab === 'files'" class="workspace-tree">
          <div class="tree-root"><FolderOpen :size="15" /> {{ selectedProjectName }}</div>
          <template v-if="projectFiles.length">
            <div v-for="file in projectFiles" :key="file.name" class="tree-item"><File :size="14" /> {{ file.name }}</div>
          </template>
          <template v-else>
            <div class="tree-item folder"><FolderOpen :size="14" /> frontend</div>
            <div class="tree-item indent"><FileCode2 :size="14" /> src/App.vue</div>
            <div class="tree-item indent"><FileCode2 :size="14" /> src/style.css</div>
            <div class="tree-item folder"><FolderOpen :size="14" /> python_backend</div>
            <div class="tree-item"><File :size="14" /> README.md</div>
          </template>
        </div>
        <div v-else class="changes-list">
          <div class="changes-summary"><CircleDot :size="15" /> 3 个文件待审阅</div>
          <button v-for="file in changedFiles" :key="file.path" class="change-file" type="button" @click="requestTextEdit(file)">
            <span class="change-status" :class="file.tone">{{ file.status }}</span>
            <span class="change-file-copy"><strong>{{ file.path }}</strong><small>{{ file.detail }}</small></span>
            <ChevronRight :size="15" />
          </button>
        </div>
        <div class="changes-panel-footer"><button type="button" @click="workspacePanelTab = 'changes'"><GitCompare :size="15" />查看全部变更</button></div>
      </aside>
      </template>

      <CodeMapPage v-else-if="activePage === 'code-map'" :api-base="backendUrl" @home="openHome" />
      <section v-else class="standalone-page" :aria-labelledby="`${activePage}-page-title`">
        <aside class="page-sidebar">
          <header class="page-sidebar-header">
            <h2>{{ activePage === 'profile' ? '个人中心' : ({ automation: '自动化', plugins: '插件', bot: '轻量机器人', docs: '文档库', harness: 'Harness 工程', export: '历史聊天' })[activePage] }}</h2>
            <div v-if="activePage !== 'profile'" class="page-sidebar-actions"><button class="icon-button" type="button" aria-label="搜索"><Search :size="17" /></button><button class="icon-button" type="button" aria-label="筛选"><MoreHorizontal :size="17" /></button></div>
          </header>
          <nav v-if="activePage === 'profile'" class="profile-settings-nav" aria-label="个人设置">
            <button type="button" :class="{ active: profileSection === 'basics' }" @click="profileSection = 'basics'"><UserRound :size="17" />基础信息</button>
            <button type="button" :class="{ active: profileSection === 'api' }" @click="profileSection = 'api'"><KeyRound :size="17" />API Key</button>
            <button type="button" :class="{ active: profileSection === 'personalization' }" @click="profileSection = 'personalization'"><Palette :size="17" />个性化</button>
            <button type="button" :class="{ active: profileSection === 'pet' }" @click="profileSection = 'pet'"><Smile :size="17" />虚拟桌宠</button>
          </nav>
          <button v-else-if="activePage === 'automation'" class="page-create" type="button" disabled><Plus :size="18" />新建任务</button>
          <button v-else-if="activePage === 'plugins'" class="page-subitem active" type="button" @click="openSkills"><Puzzle :size="16" />技能<span>{{ skills.length }}</span></button>
          <button v-else-if="activePage === 'bot'" class="page-subitem active" type="button"><Bot :size="16" />轻量机器人<span>{{ bots.length }}</span></button>
          <button v-else-if="activePage === 'docs'" class="page-create" type="button" @click="openDocs"><Plus :size="18" />上传文档</button>
          <button v-else-if="activePage === 'harness'" class="page-subitem active" type="button" @click="openHarnessPage"><Workflow :size="16" />Harness 控制面<span>已接入</span></button>
          <button v-else class="page-create" type="button" :disabled="exportingHistory" @click="exportChatHistory"><LoaderCircle v-if="exportingHistory" :size="18" class="spin" /><Download v-else :size="18" />导出全部聊天</button>

        </aside>

        <div class="page-main">
          <header v-if="activePage !== 'harness'" class="standalone-header">
            <div>
              <h1 :id="`${activePage}-page-title`">{{ activePage === 'profile' ? ({ basics: '基础信息', api: 'API Key', personalization: '个性化', pet: '虚拟桌宠' })[profileSection] : ({ automation: '安排任务', plugins: '插件', bot: '轻量机器人', docs: '文档库', harness: 'Harness 工程', export: '导出历史聊天' })[activePage] }}</h1>
            </div>
            <button class="icon-button" type="button" aria-label="回到首页" title="回到首页" @click="openHome"><Home :size="18" /></button>
          </header>
          <section v-if="activePage === 'profile'" class="profile-settings-content" :aria-labelledby="`${activePage}-page-title`">
            <template v-if="profileSection === 'basics'">
              <div class="profile-settings-intro"><div class="profile-settings-avatar"><UserRound :size="25" /></div><div><h2>个人资料</h2></div></div>
              <div class="profile-form"><label>昵称<input v-model="profileDraft.nickname" class="text-field" maxlength="60" placeholder="输入昵称" /></label><label>个人简介<textarea v-model="profileDraft.bio" class="text-field" rows="3" maxlength="500" placeholder="介绍一下自己"></textarea></label><button class="primary-button" type="button" :disabled="profileBusy" @click="saveProfileBasics">{{ profileBusy ? '保存中…' : '保存资料' }}</button></div>
            </template>
            <template v-else-if="profileSection === 'api'">
              <div class="settings-section-copy"><KeyRound :size="22" /><div><h2>模型 API Key</h2></div></div>
              <div class="profile-form">
                <label>服务商<input v-model="credentialDraft.provider" class="text-field" placeholder="例如：openai-compatible" /></label>
                <label>Base URL<input v-model="credentialDraft.baseUrl" class="text-field" placeholder="https://api.example.com/v1" /></label>
                <label>模型名称<input v-model="credentialDraft.model" class="text-field" placeholder="模型 ID" /></label>
                <label class="api-key-field">API Key<input v-model="credentialDraft.apiKey" class="text-field" type="password" placeholder="sk-••••••••••••••••" /></label>
                <p v-if="credentialMask" class="settings-note">已保存密钥：{{ credentialMask }}（留空表示不修改）</p>
                <div class="dialog-actions">
                  <button class="secondary-button" type="button" :disabled="credentialBusy" @click="testCredentialForm">测试连接</button>
                  <button class="primary-button" type="button" :disabled="credentialBusy" @click="saveCredentialForm">{{ credentialBusy ? '处理中…' : '保存凭证' }}</button>
                  <button v-if="credentialMask" class="text-action danger" type="button" @click="removeCredential">删除凭证</button>
                </div>
              </div>
            </template>
            <template v-else-if="profileSection === 'personalization'">
              <div class="settings-section-copy"><Palette :size="22" /><div><h2>个性化偏好</h2></div></div>
              <div class="preference-row"><div><strong>回答风格</strong></div><select v-model="profileDraft.answerStyle"><option value="default">默认</option><option value="concise">简洁</option><option value="detailed">详尽</option><option value="friendly">亲切</option></select></div>
              <div class="preference-row"><div><strong>界面主题</strong></div><select v-model="profileDraft.theme"><option value="system">跟随系统</option><option value="light">浅色</option><option value="dark">深色</option></select></div>
              <button class="primary-button" type="button" :disabled="profileBusy" @click="savePreferences">{{ profileBusy ? '保存中…' : '保存偏好' }}</button>
            </template>
            <template v-else>
              <div class="pet-preview"><component :is="petIcon" :size="38" /><strong>{{ petLabel }}</strong></div>
              <div class="preference-row"><div><strong>桌宠状态</strong><small>开启后可在页面右下角显示虚拟伙伴</small></div><label class="switch"><input type="checkbox" :checked="petEnabled" @change="togglePet" /></label></div>
              <div class="pet-options"><button v-for="option in petOptions" :key="option.id" type="button" class="pet-option" :class="{ active: petChoice === option.id }" @click="choosePet(option.id)"><component :is="option.icon" :size="18" /><span>{{ option.label }}</span></button></div>
            </template>
          </section>
          <HarnessApp v-if="activePage === 'harness'" embedded :api-base="backendUrl" />
          <section v-if="activePage === 'automation'" class="plugins-page">
            <div class="settings-section-copy"><CalendarClock :size="22" /><div><h2>安排任务</h2></div><button class="primary-button" type="button" @click="openScheduleForm"><Plus :size="15" />新建任务</button></div>
            <form v-if="showScheduleForm" class="schedule-form" @submit.prevent="submitSchedule">
              <label>任务名称<input v-model="scheduleDraft.name" placeholder="例如：每日服务巡检" /></label>
              <label>任务内容<textarea v-model="scheduleDraft.prompt" rows="3" placeholder="每次触发时交给 Agent 的任务描述"></textarea></label>
              <label>执行模式<select v-model="scheduleDraft.agent"><option value="chat">对话助手</option><option value="file">文件问答</option><option value="deep">深度研究</option></select></label>
              <label>间隔（分钟）<input v-model.number="scheduleDraft.intervalMinutes" type="number" min="1" max="43200" /></label>
              <div class="dialog-actions"><button class="secondary-button" type="button" @click="showScheduleForm = false">取消</button><button class="primary-button" type="submit" :disabled="scheduleBusy">{{ scheduleBusy ? '创建中…' : '创建任务' }}</button></div>
            </form>
            <div v-if="schedules.length" class="plugin-list">
              <div v-for="task in schedules" :key="task.task_id" class="plugin-row">
                <div><strong>{{ task.name }}</strong><small>{{ task.prompt }}</small><small>每 {{ task.interval_minutes }} 分钟 · 上次运行 {{ task.last_run_at || '尚未执行' }}{{ task.last_run_id ? ' · ' + task.last_run_id : '' }}</small></div>
                <span class="plugin-state">{{ task.enabled ? '已启用' : '已停用' }}</span>
                <button class="text-action" type="button" :disabled="scheduleBusy" @click="runScheduleNow(task)">立即执行</button>
                <button class="text-action" type="button" :disabled="scheduleBusy" @click="toggleSchedule(task)">{{ task.enabled ? '停用' : '启用' }}</button>
                <button class="text-action danger" type="button" @click="removeSchedule(task)">删除</button>
              </div>
            </div>
            <div v-else class="page-empty-state"><div class="page-empty-icon"><CalendarClock :size="44" /></div><h2>安排任务</h2><p>暂无定时任务</p><button class="primary-button" type="button" @click="openScheduleForm"><Plus :size="15" />新建任务</button></div>
          </section>
          <section v-else-if="activePage === 'plugins'" class="plugins-page">
            <div class="settings-section-copy"><Puzzle :size="22" /><div><h2>已安装技能</h2></div><button class="primary-button" type="button" @click="openSkills"><Upload :size="15" />上传技能包</button></div>
            <div v-if="skills.length" class="plugin-list">
              <div v-for="skill in skills" :key="skill.id" class="plugin-row">
                <div><strong>{{ skill.name }}</strong><small>{{ skill.description || '暂无说明' }}</small><small>来源 {{ skill.sourceFile || '本地安装包' }} · 入口 {{ skill.entry || '—' }}</small></div>
                <span class="plugin-state">{{ skill.enabled ? '已启用' : '已停用' }}</span>
                <button class="text-action" type="button" @click="togglePlugin(skill)">{{ skill.enabled ? '停用' : '启用' }}</button>
                <button class="text-action danger" type="button" @click="removePlugin(skill)">删除</button>
              </div>
            </div>
            <div v-else class="page-empty-state"><div class="page-empty-icon"><Puzzle :size="44" /></div><h2>管理插件</h2><p>暂无已安装技能</p><button class="primary-button" type="button" @click="openSkills"><Plus :size="15" />上传技能包</button></div>
          </section>
          <section v-else-if="activePage === 'bot'" class="plugins-page">
            <div class="settings-section-copy"><Bot :size="22" /><div><h2>轻量机器人</h2></div><button class="primary-button" type="button" @click="openBotForm()"><Plus :size="15" />新建机器人</button></div>
            <form v-if="showBotForm" class="schedule-form" @submit.prevent="submitBot">
              <label>机器人名称<input v-model="botDraft.name" placeholder="例如：值班客服" /></label>
              <label>角色指令<textarea v-model="botDraft.instruction" rows="3" placeholder="你是一位只回答售后问题的客服，结论先行、语气克制"></textarea></label>
              <label>绑定技能<select v-model="botDraft.skills" multiple size="4"><option v-for="skill in skills" :key="skill.id" :value="skill.id">{{ skill.name }}</option></select></label>
              <div class="dialog-actions"><button class="secondary-button" type="button" @click="showBotForm = false">取消</button><button class="primary-button" type="submit" :disabled="botBusy">{{ botBusy ? '保存中…' : '保存机器人' }}</button></div>
            </form>
            <div v-if="bots.length" class="plugin-list">
              <div v-for="bot in bots" :key="bot.bot_id" class="bot-row">
                <div><strong>{{ bot.name }}</strong><small>{{ bot.instruction || '未设置角色指令' }}</small><small>技能：{{ bot.skills.length ? bot.skills.join('、') : '未绑定' }}</small></div>
                <span class="plugin-state">{{ bot.enabled ? '已启用' : '已停用' }}</span>
                <select class="bot-session-select" value="" @change="bindBot(bot, $event.target.value)"><option value="">绑定会话…</option><option v-for="session in visibleSessions" :key="session.id" :value="session.id">{{ session.title }}</option></select>
                <button class="text-action" type="button" :disabled="botBusy" @click="toggleBot(bot)">{{ bot.enabled ? '停用' : '启用' }}</button>
                <button class="text-action" type="button" :disabled="botBusy" @click="openBotForm(bot)">编辑</button>
                <button class="text-action danger" type="button" @click="removeBot(bot)">删除</button>
              </div>
            </div>
            <div v-else class="page-empty-state"><div class="page-empty-icon"><Bot :size="44" /></div><h2>轻量机器人</h2><p>暂无机器人</p><button class="primary-button" type="button" @click="openBotForm()"><Plus :size="15" />新建机器人</button></div>
          </section>
          <div v-else-if="activePage === 'docs' || activePage === 'export'" class="page-empty-state">
            <div class="page-empty-icon"><FileText v-if="activePage === 'docs'" :size="44" /><Archive v-else :size="44" /></div>
            <h2>{{ activePage === 'docs' ? '管理文档' : '导出历史聊天' }}</h2>
            <p v-if="activePage === 'export'">导出为 JSON 文件</p>
            <button v-if="activePage === 'docs'" class="primary-button" type="button" @click="openDocs"><Plus :size="15" />上传文档</button>
            <button v-else class="primary-button" type="button" :disabled="exportingHistory" @click="exportChatHistory"><LoaderCircle v-if="exportingHistory" :size="15" class="spin" /><Download v-else :size="15" />{{ exportingHistory ? '正在导出' : '导出 JSON' }}</button>
          </div>
        </div>
      </section>
    </main>

    <div v-if="petEnabled" class="page-pet" :title="petLabel"><component :is="petIcon" :size="22" /></div>
    <Transition name="toast"><div v-if="toast" class="toast-message" role="status"><CheckCircle2 :size="17" />{{ toast }}</div></Transition>

    <div v-if="connectionState === 'offline'" class="connection-banner" role="alert"><AlertCircle :size="17" /><span>{{ connectionMessage || 'Python 服务暂不可用' }}</span><button type="button" @click="retryConnection">重试</button><button class="icon-button" type="button" aria-label="设置服务地址" @click="settingsDraft = backendUrl; showSettings = true"><Settings2 :size="16" /></button></div>

    <Teleport to="body">
      <Transition name="modal">
        <div v-if="showSettings" class="modal-backdrop" @click.self="showSettings = false">
          <section class="dialog settings-dialog" role="dialog" aria-modal="true" aria-labelledby="settings-title">
            <div class="dialog-heading"><div class="dialog-symbol"><Settings2 :size="19" /></div><button class="icon-button" type="button" aria-label="关闭设置" @click="showSettings = false"><X :size="18" /></button></div>
            <h2 id="settings-title">服务连接</h2><p>填写运行 Python 后端的地址。地址只保存在当前浏览器中。</p>
            <label class="field-label" for="api-base">API 地址</label><input id="api-base" v-model="settingsDraft" class="text-field" placeholder="默认与页面同源，可填写其他后端地址" @keydown.enter="saveSettings" />
            <div class="settings-current"><span class="connection-indicator" :class="connectionState"></span><span>{{ connectionState === 'online' ? '当前服务已连接' : connectionState === 'checking' ? '正在检查连接' : '当前服务不可用' }}</span><code>{{ backendUrl }}</code></div>
            <div class="dialog-actions"><button class="secondary-button" type="button" @click="showSettings = false">取消</button><button class="primary-button" type="button" :disabled="busySettings" @click="saveSettings"><LoaderCircle v-if="busySettings" :size="15" class="spin" /><Activity v-else :size="15" />测试并保存</button></div>
          </section>
        </div>
      </Transition>
      <Transition name="modal">
        <div v-if="folderImportOpen" class="modal-backdrop folder-import-backdrop workspace-dialog-theme" @click.self="cancelFolderImport">
          <section class="dialog folder-import-dialog" role="dialog" aria-modal="true" aria-labelledby="folder-import-title" aria-describedby="folder-import-copy">
            <div class="folder-import-head">
              <div class="folder-import-icon"><FolderOpen :size="18" /></div>
              <div class="folder-import-headings">
                <h2 id="folder-import-title">添加工作区</h2>
                <p id="folder-import-copy">只读取你刚刚选中的这个文件夹，确认后开始上传。</p>
              </div>
              <button class="icon-button" type="button" aria-label="关闭上传确认框" :disabled="projectUploadBusy" @click="cancelFolderImport"><X :size="18" /></button>
            </div>

            <div class="folder-import-card">
              <div class="folder-import-card-icon"><FolderOpen :size="17" /></div>
              <div class="folder-import-card-copy">
                <strong>{{ pendingWorkspaceFolderName || '新工作区' }}</strong>
                <span>整个文件夹 · {{ pendingWorkspaceEntries.length }} 个文件 · {{ formatBytes(folderImportTotalSize) }}</span>
              </div>
            </div>

            <details class="folder-import-files" aria-label="待上传文件预览">
              <summary class="folder-import-files-heading"><span>文件预览</span><span>{{ pendingWorkspaceEntries.length }} 个文件</span><ChevronRight :size="14" /></summary>
              <ul>
                <li v-for="entry in pendingWorkspaceEntries.slice(0, 6)" :key="entry.path">
                  <File :size="15" /><span>{{ entry.path }}</span><small>{{ formatBytes(entry.size) }}</small>
                </li>
              </ul>
              <p v-if="pendingWorkspaceEntries.length > 6" class="folder-import-more">还有 {{ pendingWorkspaceEntries.length - 6 }} 个文件</p>
            </details>

            <p v-if="folderImportSkipped" class="folder-import-warning"><AlertCircle :size="14" /> 已跳过 {{ folderImportSkipped }} 个私密、依赖或超过 50 MB 的文件</p>

            <div v-if="projectUploadBusy" class="folder-import-progress">
              <div class="folder-import-progress-head"><span>正在上传 {{ folderImportProgress.done }} / {{ folderImportProgress.total }}</span><strong>{{ folderImportPercent }}%</strong></div>
              <div class="folder-import-track"><i :style="{ width: `${folderImportPercent}%` }"></i></div>
              <span class="folder-import-current">{{ folderImportProgress.current }}</span>
            </div>

            <p class="folder-import-note"><ShieldCheck :size="14" /> 不会读取其他目录，也不会修改你本地的文件。</p>

            <div class="dialog-actions">
              <button class="secondary-button" type="button" :disabled="projectUploadBusy" @click="cancelFolderImport">取消</button>
              <button class="primary-button folder-import-confirm" type="button" :disabled="projectUploadBusy" @click="startFolderUpload">
                <LoaderCircle v-if="projectUploadBusy" :size="15" class="spin" />
                <Upload v-else :size="15" />
                {{ projectUploadBusy ? '正在上传…' : '确认并上传' }}
              </button>
            </div>
          </section>
        </div>
      </Transition>
      <Transition name="modal">
        <div v-if="showProjectNameDialog" class="modal-backdrop project-name-backdrop workspace-dialog-theme" @click.self="showProjectNameDialog = false">
          <section class="dialog project-name-dialog" role="dialog" aria-modal="true" aria-labelledby="project-name-title" aria-describedby="project-name-copy">
            <div class="dialog-heading"><div class="dialog-symbol permission-symbol"><FolderOpen :size="19" /></div><button class="icon-button" type="button" aria-label="关闭项目命名框" @click="showProjectNameDialog = false"><X :size="18" /></button></div>
            <h2 id="project-name-title">给这个项目起个名字</h2>
            <p id="project-name-copy">文件夹已上传，可为项目命名。</p>
            <label class="project-name-field"><span>项目名称</span><input v-model="projectNameDraft" class="text-field" autofocus maxlength="80" @keydown.enter.prevent="saveProjectName" /></label>
            <div class="dialog-actions"><button class="secondary-button" type="button" @click="showProjectNameDialog = false">稍后再命名</button><button class="primary-button" type="button" @click="saveProjectName">保存项目名称</button></div>
          </section>
        </div>
      </Transition>
      <Transition name="modal">
        <div v-if="showSkills" class="modal-backdrop" @click.self="closeSkills">
          <section class="dialog skills-dialog" role="dialog" aria-modal="true" aria-labelledby="skills-title">
            <div class="dialog-heading"><div class="dialog-symbol"><Puzzle :size="19" /></div><button class="icon-button" type="button" aria-label="关闭技能管理" @click="closeSkills"><X :size="18" /></button></div>
            <h2 id="skills-title">技能管理</h2>
            <p>支持包含 SKILL.md 的 .zip 技能包。</p>
            <div class="skill-toolbar">
              <button class="primary-button" type="button" :disabled="skillBusy" @click="skillInput.click()"><LoaderCircle v-if="skillBusy" :size="15" class="spin" /><Plus v-else :size="15" />上传技能包</button>
              <input ref="skillInput" class="skill-file-input" type="file" accept=".zip" @change="chooseSkillZip" />
              <span class="skill-tally">{{ enabledSkills.length }} / {{ skills.length }} 已启用</span>
            </div>
            <div v-if="skillMessage" class="skill-feedback" :class="skillMessage.type"><AlertCircle v-if="skillMessage.type === 'error'" :size="15" /><Check v-else :size="15" /><span>{{ skillMessage.text }}</span></div>
            <div v-if="skillEntries.length" class="skill-picker">
              <span class="field-label">未自动定位到 SKILL.md，请手动选择技能文件</span>
              <div class="skill-picker-list">
                <label v-for="entry in skillEntries" :key="entry" class="skill-picker-item"><input v-model="skillEntryChoice" type="radio" name="skill-entry" :value="entry" /><span>{{ entry }}</span></label>
              </div>
              <div class="skill-picker-actions"><button class="secondary-button" type="button" @click="clearSkillEntry">取消</button><button class="primary-button" type="button" :disabled="!skillEntryChoice || skillBusy" @click="confirmSkillEntry">使用该文件</button></div>
            </div>
            <div class="skill-list">
              <div v-if="skills.length === 0" class="skill-empty">还没有安装技能。</div>
              <article v-for="skill in skills" :key="skill.id" class="skill-row" :class="{ off: !skill.enabled }">
                <div class="skill-row-main">
                  <div class="skill-row-name"><span>{{ skill.name }}</span><em :class="{ on: skill.enabled }">{{ skill.enabled ? '已启用' : '已停用' }}</em></div>
                  <p v-if="skill.description" class="skill-row-desc">{{ skill.description }}</p>
                  <div class="skill-row-meta"><code>{{ skill.entry }}</code><span>{{ skill.sourceFile }}</span></div>
                </div>
                <div class="skill-row-actions">
                  <button class="icon-button" type="button" :title="skill.enabled ? '停用' : '启用'" :aria-label="skill.enabled ? '停用技能' : '启用技能'" @click="toggleSkill(skill)"><ToggleRight v-if="skill.enabled" :size="20" /><ToggleLeft v-else :size="20" /></button>
                  <template v-if="deletingSkill === skill.id"><button class="secondary-button" type="button" @click="deletingSkill = null">取消</button><button class="danger-button" type="button" @click="confirmRemoveSkill(skill)"><Trash2 :size="14" />确认删除</button></template>
                  <button v-else class="icon-button" type="button" title="删除技能" aria-label="删除技能" @click="deletingSkill = skill.id"><Trash2 :size="17" /></button>
                </div>
              </article>
            </div>
            <div class="dialog-actions"><button class="secondary-button" type="button" @click="closeSkills">关闭</button></div>
          </section>
        </div>
      </Transition>
      <Transition name="modal">
        <div v-if="showDocs" class="modal-backdrop" @click.self="closeDocs">
          <section class="dialog skills-dialog docs-dialog" role="dialog" aria-modal="true" aria-labelledby="docs-title">
            <div class="dialog-heading"><div class="dialog-symbol"><FileText :size="19" /></div><button class="icon-button" type="button" aria-label="关闭文档库" @click="closeDocs"><X :size="18" /></button></div>
            <h2 id="docs-title">文档库</h2>
            <p>支持 Markdown、PDF 和 Word。</p>
            <div class="skill-toolbar">
              <button class="primary-button" type="button" :disabled="docBusy" @click="docInput.click()"><LoaderCircle v-if="docBusy" :size="15" class="spin" /><Plus v-else :size="15" />{{ docBusy ? '处理中' : '上传文档' }}</button>
              <input ref="docInput" class="skill-file-input" type="file" accept=".md,.markdown,.pdf,.docx,.doc" @change="chooseDocFile" />
              <button class="secondary-button" type="button" :disabled="docBusy" @click="runCompensation"><Activity :size="15" />兜底补偿</button>
              <span class="skill-tally">{{ docCounts.vectorized }} 已向量化 · {{ docCounts.waiting }} 待处理 · {{ docCounts.failed }} 失败</span>
            </div>
            <div v-if="docMessage" class="skill-feedback" :class="docMessage.type"><AlertCircle v-if="docMessage.type === 'error'" :size="15" /><Check v-else :size="15" /><span>{{ docMessage.text }}</span></div>
            <div class="skill-list">
              <div v-if="docs.length === 0" class="skill-empty">还没有上传文档。</div>
              <article v-for="doc in docs" :key="doc.fileId" class="skill-row" :class="{ off: doc.status === 'FAILED' }">
                <div class="skill-row-main">
                  <div class="skill-row-name"><span>{{ doc.fileName }}</span><em :class="docStatusClass(doc.status)"><LoaderCircle v-if="['CONVERTING', 'VECTORIZING'].includes(doc.status)" :size="10" class="spin" />{{ docStatusLabel(doc.status) }}</em></div>
                  <p class="skill-row-desc">{{ doc.convertedVia === 'mineru' ? 'MinerU 解析' : doc.convertedVia === 'markdown' ? 'Markdown 直通' : '尚未转换' }} · {{ doc.charCount }} 字 · {{ doc.imageCount }} 张图（{{ doc.captionCount }} 张有图注）</p>
                  <div class="skill-row-meta"><code>{{ doc.docType }}</code><a v-if="doc.markdownUrl" :href="downloadHref(doc.markdownUrl)" target="_blank" rel="noopener">Markdown v{{ doc.version }}</a></div>
                  <p v-if="doc.errorMsg" class="doc-error">{{ doc.errorMsg }}</p>
                  <div v-if="expandingDoc === doc.fileId" class="doc-versions">
                    <div v-for="item in docVersions[doc.fileId] || []" :key="item.version" class="doc-version"><b>v{{ item.version }}</b><code>{{ item.note }}</code><a :href="downloadHref(item.markdownUrl)" target="_blank" rel="noopener">{{ item.markdownUrl }}</a><span>{{ item.createTime }}</span></div>
                    <p v-if="!docVersions[doc.fileId]?.length" class="doc-version-empty">暂无版本记录</p>
                  </div>
                </div>
                <div class="skill-row-actions">
                  <button v-if="doc.markdownUrl" class="secondary-button" type="button" title="查看分段、字数和图片描述" @click="openDocPreview(doc)"><Eye :size="14" />预览</button>
                  <button v-if="doc.markdownUrl" class="secondary-button" type="button" title="就这份文档提问" @click="askFromDoc(doc)">提问</button>
                  <button class="secondary-button" type="button" :disabled="docBusy || !doc.markdownUrl || doc.status === 'VECTORIZED' || doc.status === 'VECTORIZING'" :title="doc.status === 'VECTORIZED' ? '这份文档已经完成向量化' : '按标题层级做父子分段并向量化'" @click="runVectorize(doc)">{{ doc.status === 'VECTORIZED' ? '已完成' : doc.status === 'VECTORIZING' ? '处理中' : '向量化' }}</button>
                  <button class="icon-button" type="button" title="版本记录" aria-label="版本记录" @click="toggleDocVersions(doc)"><ChevronRight :size="17" /></button>
                  <template v-if="deletingDoc === doc.fileId"><button class="secondary-button" type="button" @click="deletingDoc = null">取消</button><button class="danger-button" type="button" @click="confirmRemoveDoc(doc)"><Trash2 :size="14" />确认删除</button></template>
                  <button v-else class="icon-button" type="button" title="删除文档" aria-label="删除文档" @click="deletingDoc = doc.fileId"><Trash2 :size="17" /></button>
                </div>
              </article>
            </div>
            <div class="dialog-actions"><button class="secondary-button" type="button" @click="closeDocs">关闭</button></div>
          </section>
        </div>
      </Transition>
      <Transition name="modal">
        <div v-if="showDocPreview" class="modal-backdrop preview-backdrop" @click.self="closeDocPreview">
          <section class="dialog doc-preview-dialog" role="dialog" aria-modal="true" aria-labelledby="doc-preview-title">
            <div class="dialog-heading"><div class="dialog-symbol"><Eye :size="19" /></div><button class="icon-button" type="button" aria-label="关闭文档预览" @click="closeDocPreview"><X :size="18" /></button></div>
            <h2 id="doc-preview-title">分段预览</h2>
            <p>{{ previewDoc?.fileName }}</p>

            <div v-if="docPreviewBusy" class="preview-loading"><LoaderCircle :size="20" class="spin" /><span>正在分析 Markdown 分段…</span></div>
            <div v-else-if="docPreviewError" class="skill-feedback error"><AlertCircle :size="15" /><span>{{ docPreviewError }}</span></div>
            <template v-else-if="docPreview">
              <div class="preview-stats" aria-label="分段统计">
                <article><span>子分段</span><strong>{{ docPreview.summary.childCount }}</strong><small>{{ docPreview.summary.averageChunkChars }} 字 / 块（平均）</small></article>
                <article><span>章节</span><strong>{{ docPreview.summary.sectionCount }}</strong><small>{{ docPreview.summary.parentCount }} 个长章节保留父段</small></article>
                <article><span>分段范围</span><strong>{{ docPreview.summary.minChunkChars }}–{{ docPreview.summary.maxChunkChars }}</strong><small>目标 {{ docPreview.settings.chunkSize }} 字</small></article>
                <article><span>图片描述</span><strong>{{ docPreview.summary.captionCount }}/{{ docPreview.summary.imageCount }}</strong><small>有描述 / 图片总数</small></article>
              </div>
              <div class="preview-rule"><code>{{ docPreview.settings.chunkSize }}</code> 字目标块 · <code>{{ docPreview.settings.chunkOverlap }}</code> 字重叠 · {{ docPreview.settings.countingRule }}</div>
              <div class="preview-tabs" role="tablist" aria-label="预览内容">
                <button type="button" role="tab" :aria-selected="docPreviewTab === 'chunks'" :class="{ active: docPreviewTab === 'chunks' }" @click="docPreviewTab = 'chunks'">分段明细 {{ docPreview.summary.childCount }}</button>
                <button type="button" role="tab" :aria-selected="docPreviewTab === 'images'" :class="{ active: docPreviewTab === 'images' }" @click="docPreviewTab = 'images'">图片描述 {{ docPreview.summary.captionCount }}/{{ docPreview.summary.imageCount }}</button>
              </div>
              <div v-if="docPreviewTab === 'chunks'" class="preview-panel chunk-preview-list">
                <details v-for="section in docPreview.sections" :key="section.index" class="preview-section" :open="section.index === 1">
                  <summary><span><b>{{ section.heading }}</b><small>{{ section.charCount }} 字 · {{ section.chunkCount }} 块</small></span><em>{{ section.storedAsParent ? '父段保留全文' : '直接作为子段' }}</em></summary>
                  <div class="preview-chunks">
                    <article v-for="chunk in section.chunks" :key="chunk.index" class="preview-chunk">
                      <header><span>块 {{ chunk.index }}</span><code>{{ chunk.charCount }} 字</code></header>
                      <pre>{{ chunk.content }}</pre>
                    </article>
                  </div>
                </details>
              </div>
              <div v-else class="preview-panel image-preview-list">
                <div v-if="docPreview.images.length === 0" class="skill-empty">这份文档没有图片。</div>
                <article v-for="image in docPreview.images" :key="image.index" class="image-preview-item">
                  <a :href="downloadHref(image.src)" target="_blank" rel="noopener"><img :src="downloadHref(image.src)" :alt="image.alt || `文档图片 ${image.index}`" /></a>
                  <div><span>图片 {{ image.index }}<em v-if="image.caption">{{ image.captionSource === 'generated' ? 'AI 图注' : '原文说明' }}</em></span><strong>{{ image.alt || '无原始替代文本' }}</strong><p>{{ image.caption || '暂无多模态描述' }}</p></div>
                </article>
              </div>
            </template>
            <div class="dialog-actions"><button class="secondary-button" type="button" @click="closeDocPreview">关闭</button></div>
          </section>
        </div>
      </Transition>
      <Transition name="modal">
        <div v-if="permissionRequest" class="modal-backdrop permission-backdrop workspace-dialog-theme" @click.self="cancelPermission">
          <section class="dialog permission-dialog" role="dialog" aria-modal="true" aria-labelledby="permission-title" aria-describedby="permission-copy">
            <div class="dialog-heading">
              <div class="dialog-symbol permission-symbol"><component :is="permissionRequest.icon" :size="19" /></div>
              <button class="icon-button" type="button" aria-label="取消授权" @click="cancelPermission"><X :size="18" /></button>
            </div>
            <h2 id="permission-title">{{ permissionRequest.title }}</h2>
            <p id="permission-copy">{{ permissionRequest.description }}</p>
            <div class="permission-scope" aria-label="授权范围">
              <div v-for="item in permissionRequest.scope" :key="item" class="permission-scope-row"><Check :size="15" /><span>{{ item }}</span></div>
            </div>
            <p class="permission-note"><ShieldCheck :size="15" /> 你可以随时取消，Hotline 只会执行这次明确授权的操作。</p>
            <div class="dialog-actions">
              <button class="secondary-button" type="button" @click="cancelPermission">取消</button>
              <button class="primary-button permission-confirm" type="button" @click="confirmPermission">{{ permissionRequest.confirmLabel }}</button>
            </div>
          </section>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
