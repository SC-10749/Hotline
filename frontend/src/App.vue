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
  MessageCircle, MoreHorizontal, Paperclip, Plus, Puzzle, Search, Send, Settings2,
  Home, Workflow, Bell, PanelLeft, FileCode2, GitCompare, CircleDot,
  Sparkles, Square, Trash2, ToggleLeft, ToggleRight, X, Copy, ExternalLink, Download, Bot, Archive,
  UserRound, KeyRound, Palette, Smile, Headset, CircleUserRound, CalendarClock,
  LibraryBig, GitBranch, History, MessagesSquare,
} from 'lucide-vue-next'
import { apiUrl, compensateDocuments, getAllSessions, getDocumentPreview, getDocumentVersions, getDocuments, getSessions, getSession, getSkills, removeDocument, removeSession, removeSkill, setSkillEnabled, stopAgent, streamUrl, testBackend, uploadDocument, uploadFile, uploadSkill, vectorizeDocument } from './api'

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
const showDeleteConfirm = ref(false)
const deletingId = ref(null)
const mobileSidebarOpen = ref(false)
const sidebarCollapsed = ref(false)
const showWorkspacePanel = ref(false)
const workspacePanelTab = ref('files')
const selectedProjectName = ref('')
const projectFiles = ref([])
const projectUploadBusy = ref(false)
const pendingWorkspaceImport = ref(false)
const fileInput = ref(null)
const projectFolderInput = ref(null)
const messageList = ref(null)
const composer = ref(null)
const searchText = ref('')
const searchOpen = ref(false)
const busySettings = ref(false)
const showSkills = ref(false)
const skills = ref([])
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
function closeLastEntry(message) {
  const previous = message.timeline.at(-1)
  if (previous && !previous.endedAt) previous.endedAt = Date.now()
}
function timelineSummary(message) {
  const count = message.timeline.length
  const duration = message.t0 && message.t1 ? fmtElapsed(message.t1 - message.t0) : ''
  return duration ? `${count} 步 · ${duration}` : `${count} 步`
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
  nextTick(() => composer.value?.focus())
}

function openAutomation() {
  activePage.value = 'automation'
  showWorkspacePanel.value = false
  mobileSidebarOpen.value = false
}

function openPlugins() {
  activePage.value = 'plugins'
  showWorkspacePanel.value = false
  mobileSidebarOpen.value = false
}

function openBotPage() {
  activePage.value = 'bot'
  showWorkspacePanel.value = false
  mobileSidebarOpen.value = false
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

function openProjectView() {
  activePage.value = 'home'
  showWorkspacePanel.value = true
  workspacePanelTab.value = 'files'
  mobileSidebarOpen.value = false
}

function addWorkspace() {
  if (projectUploadBusy.value) return
  pendingWorkspaceImport.value = true
  projectFolderInput.value?.click()
}

function addWorkspaceTask(project) {
  selectedProjectName.value = project.name
  if (!project.tasks) project.tasks = []
  project.tasks.unshift({ id: makeId(), title: '新任务' })
  newSession()
  showToast(`已在工作区「${project.name}」中新建任务`)
}

function showNotifications() {
  showToast('暂无新通知')
}

function openMore() {
  activePage.value = 'profile'
  profileSection.value = 'basics'
  showWorkspacePanel.value = false
  mobileSidebarOpen.value = false
}

async function onProjectFolderPicked(event) {
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  if (!files.length) return
  const folderName = files[0].webkitRelativePath?.split('/')[0] || '新工作区'
  if (pendingWorkspaceImport.value) {
    if (!projectGroups.value.some((project) => project.name === folderName)) {
      projectGroups.value.push({ name: folderName, child: '', tasks: [] })
    }
    selectedProjectName.value = folderName
    pendingWorkspaceImport.value = false
  }
  const supported = files.filter((file) => file.size <= 50 * 1024 * 1024)
  if (supported.length !== files.length) showToast('已跳过超过 50 MB 的文件')
  projectFiles.value = supported.map((file) => ({ name: file.webkitRelativePath || file.name, size: file.size }))
  projectUploadBusy.value = true
  try {
    let uploaded = 0
    for (const file of supported) {
      await uploadFile(backendUrl.value, file)
      uploaded += 1
    }
    showWorkspacePanel.value = true
    workspacePanelTab.value = 'files'
    showToast(`已上传文件夹「${selectedProjectName.value}」中的 ${uploaded} 个文件`)
  } catch (error) {
    showToast(error.message || '文件夹上传失败，请检查文件服务')
  } finally {
    projectUploadBusy.value = false
  }
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
          id: `assistant-${row.id}`, role: 'assistant', content: normalizeBrandText(row.answer),
          timeline: row.thinking ? [{ type: 'thinking', content: normalizeBrandText(row.thinking) }] : [],
          references: normalizeReferences(row.reference), recommend: parseArray(row.recommend),
          showTimeline: false, showReferences: false, createdAt: row.createTime,
        })
      }
    }
    session.messages = history
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

function askDelete(id) {
  deletingId.value = id
  showDeleteConfirm.value = true
}

async function confirmDelete() {
  const id = deletingId.value
  showDeleteConfirm.value = false
  if (!id) return
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

function appendStreamEvent(data, message) {
  if (!data || typeof data !== 'object') return
  const content = data.content
  if (data.type === 'text' && content) {
    const chunk = normalizeBrandText(content)
    message.content += chunk
    const pptLink = chunk.match(/(?:下载文件|Download):\s*(https?:\/\/\S+|\/generated\/\S+)/i)
    if (pptLink) message.pptFile = pptLink[1].replace(/[)\]，。]+$/, '')
  } else if (data.type === 'thinking' && content) {
    const previous = message.timeline.at(-1)
    if (previous?.type === 'thinking') previous.content += String(content)
    else {
      closeLastEntry(message)
      message.timeline.push({ type: 'thinking', content: String(content), t0: Date.now() })
    }
  } else if (data.type === 'tool_start') {
    closeLastEntry(message)
    message.timeline.push({ type: 'tool', toolName: data.toolName || '工具', toolCallId: data.toolCallId || '', status: 'running', t0: Date.now() })
  } else if (data.type === 'tool_end') {
    const running = message.timeline.find((entry) => entry.type === 'tool' && entry.status === 'running' && entry.toolCallId === (data.toolCallId || ''))
    if (running) { running.status = 'completed'; running.endedAt = Date.now() }
    else { closeLastEntry(message); message.timeline.push({ type: 'tool', toolName: data.toolName || '工具', toolCallId: data.toolCallId || '', status: 'completed', t0: Date.now(), endedAt: Date.now() }) }
  } else if (data.type === 'reference') {
    let references = content
    if (typeof references === 'string') {
      try { references = JSON.parse(references) } catch { references = [] }
    }
    message.references = normalizeReferences(references)
    message.showReferences = message.references.length > 0
  } else if (data.type === 'recommend') {
    message.recommend = parseArray(content)
  } else if (data.type === 'error') {
    closeLastEntry(message)
    message.timeline.push({ type: 'error', message: data.message || (typeof content === 'string' ? content : '任务执行失败'), detail: data.detail || '', t0: Date.now(), endedAt: Date.now() })
    message.showTimeline = true
  } else if (data.type === 'complete') {
    closeLastEntry(message)
    message.done = true
    message.showTimeline = message.timeline.some((entry) => entry.type === 'error')
  }
}

async function sendMessage() {
  if (!canSend.value || !currentSession.value) return
  if (connectionState.value !== 'online') {
    showToast('Python 服务未连接，请先检查服务地址')
    return
  }
  const session = currentSession.value
  const text = input.value.trim() || (uploadedFileId.value ? '请分析这个文件' : (docSource.value ? `请基于《${docSource.value.fileName}》回答` : ''))
  const fileId = uploadedFileId.value || docSource.value?.fileId || null
  const fileName = selectedFile.value?.name || docSource.value?.fileName || ''
  session.isDraft = false
  session.loaded = true
  session.agentType = fileId ? 'file' : activeMode.value
  session.messages.push({ id: makeId(), role: 'user', content: text, fileName, createdAt: new Date().toISOString() })
  if (session.messages.filter((message) => message.role === 'user').length === 1) session.title = titleFor(text)
  const assistant = { id: makeId(), role: 'assistant', content: '', timeline: [], references: [], recommend: [], showTimeline: true, showReferences: false, done: false, t0: Date.now() }
  session.messages.push(assistant)
  input.value = ''
  removeSelectedFile()
  sending.value = true
  runStartedAt.value = Date.now()
  nowTick.value = Date.now()
  startTick()
  await scrollToBottom()

  try {
    readerController = new AbortController()
    const response = await fetch(streamUrl(backendUrl.value, activeMode.value, text, session.id, fileId), {
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
    if (!assistant.done && !assistant.timeline.some((entry) => entry.type === 'error')) {
      assistant.done = true
      assistant.showTimeline = false
    }
    session.updatedAt = Date.now()
    await refreshSessions()
  } catch (error) {
    if (error.name !== 'AbortError') {
      closeLastEntry(assistant)
      assistant.timeline.push({ type: 'error', message: error.message || '请求失败', detail: '请检查 Python 后端、跨域设置及所选模式依赖。', t0: Date.now(), endedAt: Date.now() })
      assistant.showTimeline = true
    }
  } finally {
    sending.value = false
    readerController = null
    stopTick()
    runStartedAt.value = 0
    closeLastEntry(assistant)
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
  if (messageList.value) messageList.value.scrollTop = messageList.value.scrollHeight
}

function toggleSearch() {
  searchOpen.value = !searchOpen.value
  if (!searchOpen.value) searchText.value = ''
}

watch(() => currentSession.value?.messages.length, () => scrollToBottom())
watch(input, async () => {
  await nextTick()
  if (composer.value) {
    composer.value.style.height = 'auto'
    composer.value.style.height = `${Math.min(composer.value.scrollHeight, 180)}px`
  }
})

onMounted(() => {
  keydownHandler = (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault()
      newSession()
    }
    if (event.key === 'Escape') mobileSidebarOpen.value = false
  }
  window.addEventListener('keydown', keydownHandler)
  newSession()
  refreshSessions()
  getSkills(backendUrl.value).then((list) => { skills.value = list }).catch(() => {})
})

onUnmounted(() => {
  window.removeEventListener('keydown', keydownHandler)
  stopDocPolling()
})
</script>

<template>
  <div class="app-shell" :class="{ 'sidebar-collapsed': sidebarCollapsed, 'standalone-page-active': activePage !== 'home' }">
    <div v-if="mobileSidebarOpen" class="drawer-backdrop" @click="mobileSidebarOpen = false"></div>
    <aside class="app-rail" aria-label="主导航">
      <button class="rail-button" :class="{ active: activePage === 'home' }" type="button" aria-label="首页" title="首页" @click="openHome"><Home :size="20" fill="currentColor" /></button>
      <button class="rail-button" :class="{ active: activePage === 'automation' }" type="button" aria-label="自动化" title="自动化" @click="openAutomation"><CalendarClock :size="20" /></button>
      <button class="rail-button" :class="{ active: activePage === 'plugins' }" type="button" aria-label="插件" title="插件" @click="openPlugins"><Puzzle :size="20" /></button>
      <button class="rail-button" :class="{ active: activePage === 'bot' }" type="button" aria-label="轻量机器人" title="轻量机器人" @click="openBotPage"><Bot :size="20" /></button>
      <button class="rail-button" :class="{ active: activePage === 'docs' }" type="button" aria-label="文档库" title="文档库" @click="openDocsPage"><LibraryBig :size="20" /></button>
      <button class="rail-button" :class="{ active: activePage === 'harness' }" type="button" aria-label="Harness 工程" title="Harness 工程" @click="openHarnessPage"><GitBranch :size="20" /></button>
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
          <div v-for="project in projectGroups" :key="project.name" class="project-entry" :class="{ selected: selectedProjectName === project.name }">
            <div class="project-line">
              <button type="button" class="project-open" :aria-label="`打开工作区：${project.name}`" @click="selectedProjectName = project.name; openProjectView()"><FolderOpen :size="18" /><span>{{ project.name }}</span></button>
              <button class="project-add-task icon-button" type="button" :disabled="projectUploadBusy" :aria-label="`在工作区添加任务：${project.name}`" :title="`添加任务到 ${project.name}`" @click="addWorkspaceTask(project)"><Plus :size="15" /></button>
            </div>
            <div v-if="project.child" class="project-child">{{ project.child }}</div>
            <button v-for="task in project.tasks || []" :key="task.id" type="button" class="project-task" @click="selectedProjectName = project.name; openHome()"><CircleDot :size="11" /><span>{{ task.title }}</span></button>
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
          <button v-if="!session.isDraft" class="session-delete icon-button" type="button" :aria-label="`删除会话：${session.title}`" @click.stop="askDelete(session.id)"><Trash2 :size="15" /></button>
        </div>
        <div v-if="recentList.length === 0" class="session-empty">{{ searchText ? '没有匹配的会话' : '还没有历史会话' }}</div>
      </nav>

    </aside>

    <main class="workspace" :class="{ 'workspace-panel-open': showWorkspacePanel }">
      <template v-if="activePage === 'home'">
      <header class="topbar">
        <div class="topbar-left">
          <button class="icon-button sidebar-toggle" type="button" aria-controls="conversation-sidebar" :aria-expanded="sidebarIsExpanded()" :aria-label="sidebarToggleLabel()" :title="sidebarToggleLabel()" @click="toggleSidebar"><PanelLeft :size="19" /></button>
          <div v-if="currentSession && currentSession.title !== '新对话'" class="breadcrumb"><FolderOpen :size="21" /><strong>{{ currentSession.title }}</strong></div>
        </div>
      </header>

      <section ref="messageList" class="message-list" aria-label="对话内容">
        <div v-if="loadingHistory" class="history-loading"><LoaderCircle :size="18" class="spin" /> 正在加载会话记录</div>

        <div v-if="currentSession && currentSession.messages.length === 0 && !loadingHistory" class="welcome-state">
          <div class="welcome-mark"><Headset :size="28" :stroke-width="1.7" /></div>
          <div class="welcome-kicker"><span></span> Hotline <span></span></div>
          <h1>你好，我是 Hotline</h1>
          <p>从一个入口，完成问答、文件和技能任务</p>
          <div class="quick-prompts">
            <button v-for="prompt in quickPrompts" :key="prompt.text" class="quick-prompt" type="button" @click="choosePrompt(prompt.text)">
              <component :is="prompt.icon" :size="17" /> <span>{{ prompt.text }}</span><ArrowUp :size="14" class="prompt-arrow" />
            </button>
          </div>
        </div>

        <div v-for="message in currentSession?.messages || []" :key="message.id" class="message-row" :class="`message-${message.role}`">
          <div v-if="message.role === 'assistant'" class="assistant-avatar"><MessagesSquare :size="15" /></div>
          <div class="message-body">
            <div class="message-meta"><strong>{{ message.role === 'user' ? '你' : 'Hotline' }}</strong><time v-if="message.createdAt">{{ new Date(message.createdAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }}</time><span v-if="message.role === 'assistant' && sending && !message.done" class="stream-status"><span class="status-dot"></span>正在思考</span></div>
            <div v-if="message.fileName" class="message-attachment"><File :size="15" /><span>{{ message.fileName }}</span></div>

            <section v-if="message.role === 'assistant' && message.timeline?.length" class="timeline-block">
              <button class="disclosure-button" type="button" :aria-expanded="message.showTimeline" @click="message.showTimeline = !message.showTimeline">
                <span class="tl-dot" :class="{ run: sending && !message.done, err: message.timeline.some((entry) => entry.type === 'error'), ok: message.done && !message.timeline.some((entry) => entry.type === 'error') }"></span>
                <span>{{ message.timeline.some((entry) => entry.type === 'error') ? '执行记录 · 有异常' : (message.done ? '执行过程' : '正在执行') }}</span>
                <span class="timeline-count mono-time">{{ timelineSummary(message) }}</span>
                <component :is="message.showTimeline ? ChevronDown : ChevronRight" :size="15" class="disclosure-chevron" />
              </button>
              <div v-if="message.showTimeline" class="timeline-content">
                <div v-for="(entry, index) in message.timeline" :key="index" class="timeline-entry" :class="`entry-${entry.type}`">
                  <span class="timeline-marker"><Check v-if="entry.type === 'tool' && entry.status === 'completed'" :size="11" /><LoaderCircle v-else-if="entry.type === 'tool' && entry.status === 'running'" :size="11" class="spin" /><AlertCircle v-else-if="entry.type === 'error'" :size="12" /><span v-else-if="entry.type === 'thinking' && sending && !message.done && index === message.timeline.length - 1" class="dot run" style="width:7px;height:7px"></span><span v-else></span></span>
                  <div v-if="entry.type === 'thinking'" class="timeline-thinking">{{ entry.content }}</div>
                  <div v-else-if="entry.type === 'error'" class="timeline-error"><strong>{{ entry.message }}</strong><span v-if="entry.detail">{{ entry.detail }}</span></div>
                  <div v-else class="timeline-tool">{{ entry.toolName }}<span>{{ entry.status === 'running' ? '运行中' : '已完成' }}</span></div>
                  <span v-if="entry.endedAt && entry.t0" class="entry-duration">{{ fmtStep(entry.endedAt - entry.t0) }}</span>
                </div>
              </div>
            </section>

            <div v-if="message.content" v-highlight class="markdown-content" v-html="renderMarkdown(message.content)"></div>
            <div v-else-if="message.role === 'assistant' && sending && !message.done" class="thinking-placeholder"><span></span><span></span><span></span></div>

            <section v-if="message.references?.length" class="references-block">
              <button class="disclosure-button" type="button" :aria-expanded="message.showReferences" @click="message.showReferences = !message.showReferences"><Link2 :size="15" /><span>参考来源</span><span class="timeline-count">{{ message.references.length }}</span><component :is="message.showReferences ? ChevronDown : ChevronRight" :size="15" class="disclosure-chevron" /></button>
              <div v-if="message.showReferences" class="reference-list">
                <a v-for="ref in message.references" :key="ref.url" :href="ref.url" target="_blank" rel="noopener noreferrer" class="reference-link"><span class="reference-copy"><strong>{{ ref.title }}</strong><small>{{ ref.url }}</small></span><ExternalLink :size="14" /></a>
              </div>
            </section>

            <a v-if="message.pptFile" class="download-link" :href="downloadHref(message.pptFile)" download><Download :size="16" /> 下载生成的 PPT</a>
            <div v-if="message.role === 'assistant' && message.recommend?.length" class="recommendations"><span class="recommend-label">接下来可以</span><button v-for="(question, index) in message.recommend" :key="index" type="button" @click="sendRecommendation(question)">{{ question }}<ArrowUp :size="13" /></button></div>
            <button v-if="message.role === 'assistant' && message.content" class="copy-message icon-button" type="button" aria-label="复制回答" title="复制回答" @click="copyText(message.content)"><Copy :size="14" /></button>
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
                <button class="attach-button icon-button" type="button" :disabled="uploadBusy || sending" aria-label="上传文件" title="上传文件" @click="fileInput?.click()"><Paperclip :size="17" /></button>
                <span class="composer-hint"><span v-if="activeMode === 'skills'">技能助手接口</span><span v-else>{{ activeModeInfo.description }}</span><span class="hint-divider"></span><kbd>Enter</kbd> 发送 <span class="hint-divider"></span><kbd>Shift Enter</kbd> 换行</span>
              </div>
              <div class="send-actions">
                <span v-if="input.length" class="char-count">{{ input.length }}</span>
                <button v-if="sending" class="send-button stop-button" type="button" aria-label="停止生成" title="停止生成" @click="stopMessage"><Square :size="15" fill="currentColor" /></button>
                <button v-else class="send-button" type="button" aria-label="发送消息" title="发送消息" :disabled="!canSend" @click="sendMessage"><Send :size="16" /></button>
              </div>
            </div>
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
          <button v-for="file in changedFiles" :key="file.path" class="change-file" type="button">
            <span class="change-status" :class="file.tone">{{ file.status }}</span>
            <span class="change-file-copy"><strong>{{ file.path }}</strong><small>{{ file.detail }}</small></span>
            <ChevronRight :size="15" />
          </button>
        </div>
        <div class="changes-panel-footer"><button type="button" @click="workspacePanelTab = 'changes'"><GitCompare :size="15" />查看全部变更</button></div>
      </aside>
      </template>

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
          <button v-else-if="activePage === 'bot'" class="page-subitem active" type="button" disabled><Bot :size="16" />轻量机器人<span>规划中</span></button>
          <button v-else-if="activePage === 'docs'" class="page-create" type="button" @click="openDocs"><Plus :size="18" />上传文档</button>
          <button v-else-if="activePage === 'harness'" class="page-subitem active" type="button" disabled><Bot :size="16" />执行工作台<span>规划中</span></button>
          <button v-else class="page-create" type="button" :disabled="exportingHistory" @click="exportChatHistory"><LoaderCircle v-if="exportingHistory" :size="18" class="spin" /><Download v-else :size="18" />导出全部聊天</button>
          <p v-if="activePage !== 'profile'" class="page-sidebar-empty">{{ activePage === 'automation' ? '暂无已安排的任务' : activePage === 'plugins' ? '插件功能集中在这里管理' : activePage === 'bot' ? '轻量机器人能力正在规划' : activePage === 'docs' ? '暂无已上传的文档' : activePage === 'harness' ? '工作台能力正在规划' : `${sessions.filter((session) => !session.isDraft).length} 个会话可导出` }}</p>
        </aside>

        <div class="page-main">
          <header class="standalone-header">
            <div>
              <span class="standalone-kicker">Hotline 工作台</span>
              <h1 :id="`${activePage}-page-title`">{{ activePage === 'profile' ? ({ basics: '基础信息', api: 'API Key', personalization: '个性化', pet: '虚拟桌宠' })[profileSection] : ({ automation: '安排任务', plugins: '插件', bot: '轻量机器人', docs: '文档库', harness: 'Harness 工程', export: '导出历史聊天' })[activePage] }}</h1>
            </div>
            <button class="icon-button" type="button" aria-label="回到首页" title="回到首页" @click="openHome"><Home :size="18" /></button>
          </header>
          <section v-if="activePage === 'profile'" class="profile-settings-content" :aria-labelledby="`${activePage}-page-title`">
            <template v-if="profileSection === 'basics'">
              <div class="profile-settings-intro"><div class="profile-settings-avatar"><UserRound :size="25" /></div><div><h2>个人资料</h2><p>管理你的昵称和个人简介。</p></div><span class="planned-tag">暂未启用</span></div>
              <div class="profile-form"><label>昵称<input class="text-field" disabled placeholder="输入昵称" /></label><label>个人简介<textarea class="text-field" disabled rows="3" placeholder="介绍一下自己"></textarea></label><button class="primary-button" type="button" disabled>保存资料</button></div>
            </template>
            <template v-else-if="profileSection === 'api'">
              <div class="settings-section-copy"><KeyRound :size="22" /><div><h2>模型 API Key</h2><p>配置你自己的模型服务凭证。保存与调用功能尚未接入。</p></div></div>
              <label class="api-key-field">API Key<input class="text-field" type="password" disabled placeholder="sk-••••••••••••••••" /></label>
              <p class="settings-note">密钥安全存储能力完成前，此处不会读取或保存输入内容。</p>
              <button class="primary-button" type="button" disabled>保存 API Key</button>
            </template>
            <template v-else-if="profileSection === 'personalization'">
              <div class="settings-section-copy"><Palette :size="22" /><div><h2>个性化偏好</h2><p>定制助手的表达方式和界面体验。</p></div></div>
              <div class="preference-row"><div><strong>回答风格</strong><small>选择助手的表达语气</small></div><select disabled><option>默认</option></select></div>
              <div class="preference-row"><div><strong>界面主题</strong><small>浅色、深色或跟随系统</small></div><select disabled><option>跟随系统</option></select></div>
              <span class="planned-tag">偏好设置暂未启用</span>
            </template>
            <template v-else>
              <div class="pet-preview"><Smile :size="38" /><strong>你的桌面伙伴</strong><span>桌宠展示与互动功能正在准备中</span></div>
              <div class="preference-row"><div><strong>桌宠状态</strong><small>开启后可在桌面边缘显示虚拟伙伴</small></div><span class="planned-tag">即将推出</span></div>
              <button class="primary-button" type="button" disabled>选择桌宠</button>
            </template>
          </section>
          <div v-else class="page-empty-state">
            <div class="page-empty-icon"><Workflow v-if="activePage === 'automation'" :size="44" /><Puzzle v-else-if="activePage === 'plugins'" :size="44" /><Bot v-else-if="activePage === 'bot'" :size="44" /><FileText v-else-if="activePage === 'docs'" :size="44" /><FileCode2 v-else-if="activePage === 'harness'" :size="44" /><Archive v-else :size="44" /></div>
            <h2>{{ activePage === 'automation' ? '安排任务' : activePage === 'plugins' ? '管理插件' : activePage === 'bot' ? '轻量级机器人' : activePage === 'docs' ? '管理文档' : activePage === 'harness' ? 'Harness 工作台' : '导出历史聊天' }}</h2>
            <p>{{ activePage === 'automation' ? 'Hotline 可以帮你处理持续性任务，让你不必亲自自动手。' : activePage === 'plugins' ? '安装和管理技能，让 Hotline 拥有更适合你的工作能力。' : activePage === 'bot' ? '创建专注单一任务的轻量机器人，配置名称、角色指令和常用能力，并从独立入口快速开始对话。当前项目尚未接入机器人配置与运行服务。' : activePage === 'docs' ? '上传文档后，可以预览、提问并建立检索索引。' : activePage === 'harness' ? '按项目管理 Agent 执行环境，追踪任务步骤、工具调用、错误与生成文件。当前模块尚未接入执行服务。' : '将历史会话及完整问答记录导出为 JSON 文件，便于备份和迁移。' }}</p>
            <button v-if="activePage === 'plugins'" class="primary-button" type="button" @click="openSkills"><Puzzle :size="15" />打开技能</button>
            <button v-else-if="activePage === 'bot'" class="primary-button" type="button" disabled>规划中</button>
            <button v-else-if="activePage === 'docs'" class="primary-button" type="button" @click="openDocs"><Plus :size="15" />上传文档</button>
            <button v-else-if="activePage === 'export'" class="primary-button" type="button" :disabled="exportingHistory" @click="exportChatHistory"><LoaderCircle v-if="exportingHistory" :size="15" class="spin" /><Download v-else :size="15" />{{ exportingHistory ? '正在导出' : '导出 JSON' }}</button>
            <button v-else-if="activePage === 'harness'" class="primary-button" type="button" disabled>规划中</button>
            <button v-else class="primary-button" type="button" disabled>新建任务</button>
          </div>
        </div>
      </section>
    </main>

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
        <div v-if="showSkills" class="modal-backdrop" @click.self="closeSkills">
          <section class="dialog skills-dialog" role="dialog" aria-modal="true" aria-labelledby="skills-title">
            <div class="dialog-heading"><div class="dialog-symbol"><Puzzle :size="19" /></div><button class="icon-button" type="button" aria-label="关闭技能管理" @click="closeSkills"><X :size="18" /></button></div>
            <h2 id="skills-title">技能管理</h2>
            <p>上传含 SKILL.md 的技能包（.zip）。系统会在前 3 层目录内自动查找，找不到时可手动指定。</p>
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
            <p>Markdown 直接入库；PDF / Word 交给 MinerU 解析成 Markdown，抽出的图片托管到对象存储并改写正文地址，再由多模态模型逐张生成图注。</p>
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
            <p>{{ previewDoc?.fileName }} · 这里展示当前配置实际会生成的父子分段和图片描述。</p>

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
        <div v-if="showDeleteConfirm" class="modal-backdrop" @click.self="showDeleteConfirm = false">
          <section class="dialog confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="delete-title" aria-describedby="delete-copy">
            <div class="dialog-heading"><div class="dialog-symbol danger-symbol"><Trash2 :size="19" /></div><button class="icon-button" type="button" aria-label="关闭确认框" @click="showDeleteConfirm = false"><X :size="18" /></button></div>
            <h2 id="delete-title">删除这段会话？</h2><p id="delete-copy">删除后，对话记录将无法恢复。</p>
            <div class="dialog-actions"><button class="secondary-button" type="button" @click="showDeleteConfirm = false">保留会话</button><button class="danger-button" type="button" @click="confirmDelete"><Trash2 :size="15" />确认删除</button></div>
          </section>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
