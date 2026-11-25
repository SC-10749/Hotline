import { computed, nextTick, reactive, ref, watch } from 'vue'
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
import { FileCode2, FileText } from 'lucide-vue-next'
import { apiFetch } from '../auth/token'
import { getAllSessions, getSession, getSessions, removeSession, stopAgent, streamUrl, uploadFile } from '../../api'
import { appendProgressEvent, finishProgress, progressEntryLabel, progressLabel } from '../execution/progress'
import { buildOptionPanel, composeOptionAnswer, extractQuestionOptions } from '../requirement/question-options'
import { readSseStream } from '../streaming/sse'
import { handoffFor, recommendationLabel } from '../requirement/handoff'
import { skillComposerCopy } from '../skills/composer'
import { modes } from './modes'
import { makeId } from '../app/ids'
import { downloadHref as makeDownloadHref } from '../app/format'

marked.setOptions({ breaks: true, gfm: true })
Object.entries({ bash, css, java, javascript, json, markdown, python, sql, typescript, xml }).forEach(([name, language]) => hljs.registerLanguage(name, language))

// 任务卡上的助手角标：会话列表与消息时间线共用。
export const modeBadges = {
  chat: { label: '对话助手', cls: 'b-chat' },
  file: { label: '文件问答', cls: 'b-file' },
  ppt: { label: 'PPT 生成', cls: 'b-ppt' },
  deep: { label: '深度研究', cls: 'b-deep' },
  skills: { label: '技能助手', cls: 'b-skill' },
}

const supportedExtensions = new Set(['pdf', 'doc', 'docx', 'txt', 'png', 'jpg', 'jpeg'])
const STREAM_TICK_MS = 33

export function useChat(ctx) {
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
  const exportingHistory = ref(false)
  const deletingId = ref(null)
  const searchText = ref('')
  const searchOpen = ref(false)
  // 用户主动上滑后不再强制回到底部，回到底部时自动恢复跟随
  const autoScroll = ref(true)
  const runStartedAt = ref(0)
  const nowTick = ref(Date.now())
  let tickTimer = null
  let readerController = null

  const currentSession = computed(() => sessions.value.find((session) => session.id === activeId.value) || null)
  const isWelcome = computed(() => ctx.activePage === 'home' && currentSession.value?.messages.length === 0 && !loadingHistory.value)
  const visibleSessions = computed(() => sessions.value.filter((session) => !session.isDraft && session.title.toLowerCase().includes(searchText.value.toLowerCase())))
  const runningItem = computed(() => (sending.value && currentSession.value && !currentSession.value.isDraft ? [currentSession.value] : []))
  const recentList = computed(() => visibleSessions.value.filter((session) => !runningItem.value.includes(session)))
  const canSend = computed(() => !sending.value && !uploadBusy.value && (input.value.trim() || uploadedFileId.value))
  // 技能助手（TDD）阶段：底部对话框整块被技能接手，不再是普通聊天输入区。
  const skillCopy = computed(() => skillComposerCopy(ctx.activeMode))
  const activeModeInfo = computed(() => modes.find((mode) => mode.id === ctx.activeMode) || modes[0])
  const draftSessions = () => sessions.value.filter((session) => session.isDraft)
  const runningElapsed = computed(() => fmtElapsed(nowTick.value - runStartedAt.value))
  const optionPanel = computed(() => currentSession.value?.optionPanel || [])
  const optionSelection = computed(() => currentSession.value?.optionSelection || [])

  // ===== 任务卡与时间线：状态点、等宽耗时、相对时间 =====
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
      const session = { id: makeId(), title: '新对话', messages: [], isDraft: true, updatedAt: Date.now(), optionPanel: [], optionSelection: [] }
      sessions.value.unshift(session)
      activeId.value = session.id
    }
    ctx.mobileSidebarOpen = false
    ctx.activeMode = 'chat'
    selectedFile.value = null
    uploadedFileId.value = null
    docSource.value = null
    input.value = ''
  }

  async function exportChatHistory() {
    if (exportingHistory.value) return
    exportingHistory.value = true
    try {
      const records = await getAllSessions(ctx.backendUrl)
      const conversations = []
      for (let start = 0; start < records.length; start += 8) {
        const batch = await Promise.all(records.slice(start, start + 8).map(async (record) => {
          const detail = await getSession(ctx.backendUrl, record.conversationId)
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
      ctx.showToast(`已导出 ${conversations.length} 个历史会话`)
    } catch (error) {
      ctx.showToast(error.message || '聊天记录导出失败')
    } finally {
      exportingHistory.value = false
    }
  }

  function requestPermission(request) {
    ctx.permissionRequest = request
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
    ctx.permissionRequest = null
  }

  function confirmPermission() {
    const request = ctx.permissionRequest
    ctx.permissionRequest = null
    if (!request) return
    if (request.kind === 'file-read') {
      ctx.hooks.pickFile()
    } else if (request.kind === 'text-edit') {
      ctx.showToast(`已允许编辑「${request.target}」`)
    }
  }

  async function refreshSessions() {
    try {
      const previous = new Map(sessions.value.map((session) => [session.id, session]))
      const records = await getSessions(ctx.backendUrl)
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
          optionPanel: previous.get(item.conversationId)?.optionPanel || [],
          optionSelection: previous.get(item.conversationId)?.optionSelection || [],
        })),
      ]
      ctx.connectionState = 'online'
      ctx.connectionMessage = ''
    } catch (error) {
      ctx.connectionState = 'offline'
      ctx.connectionMessage = error.name === 'TimeoutError'
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
    ctx.mobileSidebarOpen = false
    const session = sessions.value.find((item) => item.id === id)
    ctx.selectedProjectId = session?.workspaceId || ''
    ctx.selectedProjectName = ctx.projectGroups.find(item => item.id === session?.workspaceId)?.name || ''
    if (!session || session.isDraft || session.loaded) {
      await ctx.hooks.scrollToBottom()
      return
    }
    loadingHistory.value = true
    try {
      const detail = await getSession(ctx.backendUrl, id)
      const history = []
      for (const row of detail.messages || []) {
        if (row.question) history.push({ id: `user-${row.id}`, role: 'user', content: row.question, fileName: row.fileid ? '已上传文件' : '', createdAt: row.createTime })
        if (row.answer || row.thinking) {
          const message = {
            id: `assistant-${row.id}`, role: 'assistant', content: normalizeBrandText(row.answer), done: true,
            timeline: row.thinking ? [{ type: 'thinking', content: normalizeBrandText(row.thinking) }] : [],
            references: normalizeReferences(row.reference), recommend: parseArray(row.recommend),
            showTimeline: false, showReferences: false, createdAt: row.createTime,
          }
          applyQuestionOptions(message)
          history.push(message)
        }
      }
      session.messages = history
      const lastAnswer = [...history].reverse().find(item => item.role === 'assistant' && item.questionOptions?.length)
      session.optionPanel = buildOptionPanel(lastAnswer?.questionOptions || [])
      session.optionSelection = []
      session.workspaceId = detail.workspaceId || session.workspaceId || ''
      ctx.selectedProjectId = session.workspaceId
      ctx.selectedProjectName = ctx.projectGroups.find(item => item.id === session.workspaceId)?.name || ''
      session.loaded = true
      session.agentType = detail.agentType || session.agentType
      ctx.activeMode = ['chat', 'file', 'ppt', 'deep', 'skills'].includes(session.agentType) ? session.agentType : 'chat'
    } catch (error) {
      if (error.status === 404) {
        // 服务端已经没有这条会话（别处删过），列表里的旧条目要自己消失，否则点了永远进不去
        sessions.value = sessions.value.filter((item) => item.id !== id)
        if (activeId.value === id) newSession()
        ctx.showToast('该会话已不存在，已从列表移除')
        await refreshSessions()
      } else {
        ctx.showToast(error.message || '会话记录加载失败')
      }
    } finally {
      loadingHistory.value = false
      await ctx.hooks.scrollToBottom()
    }
  }

  async function deleteConversation(id) {
    if (!id || deletingId.value) return
    deletingId.value = id
    try {
      await removeSession(ctx.backendUrl, id)
      sessions.value = sessions.value.filter((session) => session.id !== id)
      if (activeId.value === id) {
        activeId.value = null
        newSession()
      }
      ctx.showToast('会话已删除')
    } catch (error) {
      ctx.showToast(error.message || '删除失败')
    } finally {
      deletingId.value = null
    }
  }

  function chooseMode(id) {
    if (sending.value) return
    ctx.activeMode = id
    if (id !== 'file') {
      selectedFile.value = null
      uploadedFileId.value = null
      docSource.value = null
    }
  }

  function choosePrompt(text) {
    input.value = text
    nextTick(() => ctx.hooks.focusComposer())
  }

  async function onFilePicked(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    const ext = file.name.split('.').pop().toLowerCase()
    if (!supportedExtensions.has(ext)) {
      ctx.showToast('支持 PDF、Word、TXT、PNG、JPG 文件')
      return
    }
    if (file.size > 50 * 1024 * 1024) {
      ctx.showToast('文件不能超过 50 MB')
      return
    }
    selectedFile.value = file
    ctx.activeMode = 'file'
    uploadBusy.value = true
    try {
      const uploaded = await uploadFile(ctx.backendUrl, file)
      uploadedFileId.value = uploaded.fileId
      ctx.showToast('文件已上传并完成解析')
    } catch (error) {
      selectedFile.value = null
      uploadedFileId.value = null
      ctx.showToast(error.message || '文件上传失败，请检查文件服务')
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
    ctx.activeMode = 'file'
    ctx.hooks.closeDocs()
  }

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
        if (ticks % 3 === 0) ctx.hooks.scrollToBottom()
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
      applyQuestionOptions(message)
      syncOptionPanel(message)
    }
    ctx.hooks.scrollToBottom()
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
    } else if (data.type === 'agent') {
      // 后端说这一轮实际跑的是哪个助手：技能助手就把输入区切过去。
      const mode = String(content || '')
      if (['chat', 'file', 'ppt', 'deep', 'skills'].includes(mode)) ctx.activeMode = mode
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
    if (ctx.connectionState !== 'online') {
      ctx.showToast('Python 服务未连接，请先检查服务地址')
      return
    }
    const text = input.value.trim() || (uploadedFileId.value ? '请分析这个文件' : (docSource.value ? `请基于《${docSource.value.fileName}》回答` : ''))
    const fileId = uploadedFileId.value || docSource.value?.fileId || null
    const fileName = selectedFile.value?.name || docSource.value?.fileName || ''
    let session = currentSession.value
    const workspaceId = ctx.selectedProjectId
    const mode = ctx.activeMode
    if (session.messages.length && (session.workspaceId || '') !== workspaceId) {
      newSession()
      session = currentSession.value
      ctx.activeMode = mode
    }
    session.workspaceId = workspaceId
    session.isDraft = false
    session.loaded = true
    session.optionPanel = []
    session.optionSelection = []
    session.agentType = ctx.activeMode === 'skills' ? 'skills' : (fileId ? 'file' : ctx.activeMode)
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
    await ctx.hooks.scrollToBottom()

    try {
      readerController = new AbortController()
      const response = await apiFetch(streamUrl(ctx.backendUrl, ctx.activeMode, text, session.id, fileId, session.workspaceId), {
        headers: { Accept: 'text/event-stream', 'Cache-Control': 'no-cache' },
        signal: readerController.signal,
      })
      if (!response.ok) {
        let message = `请求失败（HTTP ${response.status}）`
        try { message = (await response.json()).message || message } catch {}
        throw new Error(message)
      }
      if (!response.body) throw new Error('浏览器不支持流式响应')
      // 分帧规则收敛到 streaming/sse.js：对话、运行事件、并行子任务共用一套。
      await readSseStream(response, async (data) => {
        try { appendStreamEvent(JSON.parse(data), assistant) } catch { /* Ignore an incomplete or non-JSON event. */ }
        await ctx.hooks.scrollToBottom()
      })
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
      await ctx.hooks.scrollToBottom()
    }
  }

  async function stopMessage() {
    if (!sending.value || !currentSession.value) return
    try {
      await stopAgent(ctx.backendUrl, currentSession.value.id)
    } catch (error) {
      ctx.showToast(error.message || '停止请求未能送达后端')
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

  // 需求问答里的候选答案从正文抽出来，正文只留问题，候选挪到输入框上方做选择面板。
  function applyQuestionOptions(message) {
    const parsed = extractQuestionOptions(normalizeBrandText(message.content || ''))
    message.bodyText = parsed.text
    message.questionOptions = parsed.groups
  }

  // 选择面板只跟随最新一轮回答：换了问题就换面板，选项可多选。
  function syncOptionPanel(message) {
    const session = currentSession.value
    if (!session) return
    session.optionPanel = buildOptionPanel(message.questionOptions || [])
    session.optionSelection = []
  }

  function messageBody(message) {
    if (!message) return ''
    return message.bodyText ?? normalizeBrandText(message.content || '')
  }

  function toggleOption(key) {
    const session = currentSession.value
    if (!session) return
    const selected = session.optionSelection || (session.optionSelection = [])
    const index = selected.indexOf(key)
    if (index >= 0) selected.splice(index, 1)
    else selected.push(key)
  }

  // 选好的候选答案交给 TDD 技能继续追问，需求分析助手不再重复问同一件事。
  function sendSelectedOptions() {
    const session = currentSession.value
    if (!session || !session.optionSelection?.length) return
    const text = composeOptionAnswer(session.optionPanel || [], session.optionSelection)
    if (!text) return
    ctx.activeMode = 'skills'
    input.value = text
    sendMessage()
  }

  function sendRecommendation(item) {
    // 结构化推荐项带目标技能：切到技能助手，把标签原样作为请求发过去。
    const handoff = handoffFor(item)
    if (handoff) ctx.activeMode = handoff.mode
    input.value = handoff ? handoff.query : String(item || '')
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
      ctx.showToast('已复制到剪贴板')
    } catch {
      ctx.showToast('复制失败，请检查浏览器权限')
    }
  }

  function downloadHref(file) {
    return makeDownloadHref(ctx.backendUrl, file)
  }

  function toggleSearch() {
    searchOpen.value = !searchOpen.value
    if (!searchOpen.value) searchText.value = ''
  }

  watch(() => currentSession.value?.messages.length, () => ctx.hooks.scrollToBottom())

  const state = reactive({
    sessions, activeId, input, selectedFile, uploadedFileId, docSource,
    uploadBusy, sending, loadingHistory, exportingHistory, deletingId,
    searchText, searchOpen, autoScroll, runStartedAt, nowTick,
    currentSession, isWelcome, visibleSessions, runningItem, recentList,
    canSend, skillCopy, activeModeInfo, optionPanel, optionSelection, runningElapsed,
  })

  const actions = {
    newSession, refreshSessions, selectSession, deleteConversation,
    chooseMode, choosePrompt, onFilePicked, removeSelectedFile,
    sendMessage, stopMessage, submitFromKeyboard, sendRecommendation,
    answerClarify, clarifyKeydown, copyText, exportChatHistory, toggleSearch,
    toggleOption, sendSelectedOptions, requestPermission, cancelPermission,
    confirmPermission, openFilePicker, requestTextEdit, askFromDoc, downloadHref,
    messageBody, renderMarkdown, badgeInfo, timelineSummary, messageIsStreaming, highlightCode,
    fmtRelTime, fmtElapsed, fmtStep, normalizeBrandText, recommendationLabel,
    progressLabel, progressEntryLabel,
  }

  return { state, actions }
}
