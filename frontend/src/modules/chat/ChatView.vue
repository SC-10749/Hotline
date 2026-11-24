<script setup>
import { inject, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  AlertCircle, ArrowUp, Check, ChevronDown, ChevronRight, Copy, Download, ExternalLink,
  File, FileText, Link2, LoaderCircle, MessageCircle, Paperclip, Square, X,
} from 'lucide-vue-next'
import OptionPanel from '../requirement/OptionPanel.vue'
import { modes, quickPrompts } from './modes'
import { formatBytes } from '../app/format'
import { APP_KEY, CHAT_KEY } from '../app/keys'
import hotlineAvatar from '../../assets/hotline-avatar.jpg'

const ctx = inject(APP_KEY)
const chat = inject(CHAT_KEY)
const messageList = ref(null)
const composer = ref(null)
const composerArea = ref(null)
const fileInput = ref(null)
let composerObserver = null

// 代码块高亮：markdown 渲染后统一补一次。
const vHighlight = { mounted: chat.actions.highlightCode, updated: chat.actions.highlightCode }

async function scrollToBottom() {
  await nextTick()
  const list = messageList.value
  if (!list || !chat.state.autoScroll) return
  list.scrollTop = list.scrollHeight
}

function onUserScroll() {
  const list = messageList.value
  if (!list) return
  chat.state.autoScroll = list.scrollHeight - list.scrollTop - list.clientHeight < 48
}

function focusComposer(options) {
  composer.value?.focus(options)
}

function pickFile() {
  fileInput.value?.click()
}

defineExpose({ scrollToBottom, focusComposer, pickFile })

watch([() => chat.state.input, composer], async () => {
  await nextTick()
  const field = composer.value
  if (!field) return
  const max = parseFloat(getComputedStyle(field).maxHeight) || 150
  const current = field.getBoundingClientRect().height
  // 量内容高度必须先关掉过渡：开着过渡时 height:auto 会被动画值挡住，量到的还是旧高度
  field.style.transition = 'none'
  field.style.height = 'auto'
  const content = field.scrollHeight
  field.style.height = `${current}px`
  void field.offsetHeight
  field.style.transition = ''
  field.style.height = `${Math.min(Math.max(content, 26), max)}px`
})

onMounted(() => {
  // 输入区悬浮在底部，消息流要按它的高度留出底部空间
  if (composerArea.value) {
    composerObserver = new ResizeObserver(() => {
      document.documentElement.style.setProperty('--composer-height', `${composerArea.value.offsetHeight}px`)
      // 消息流高度变了，滚动位置要重新贴底，否则最后一条会掉到可视区外
      requestAnimationFrame(() => { if (chat.state.autoScroll) scrollToBottom() })
    })
    composerObserver.observe(composerArea.value)
  }
})

onUnmounted(() => {
  composerObserver?.disconnect()
  composerObserver = null
})
</script>

<template>
  <section ref="messageList" class="message-list" aria-label="对话内容" @scroll="onUserScroll">
    <div v-if="chat.state.loadingHistory" class="history-loading"><LoaderCircle :size="18" class="spin" /> 正在加载会话记录</div>

    <div v-if="chat.state.isWelcome" class="welcome-state">
      <div class="welcome-mark"><img :src="hotlineAvatar" alt="Hotline" /></div>
      <h1>你好，我是 Hotline</h1>

    </div>

    <div v-for="message in chat.state.currentSession?.messages || []" :key="message.id" class="message-row" :class="`message-${message.role}`">
      <div v-if="message.role === 'assistant'" class="assistant-avatar"><img :src="hotlineAvatar" alt="Hotline" /></div>
      <div class="message-body">
        <div class="message-meta"><strong>{{ message.role === 'user' ? '你' : 'Hotline' }}</strong><time v-if="message.createdAt">{{ new Date(message.createdAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }}</time><span v-if="message.role === 'assistant' && message.showTimeline && chat.actions.messageIsStreaming(message)" class="stream-status" role="status" aria-live="polite"><span class="status-dot"></span>{{ chat.actions.progressLabel(message) }}</span></div>
        <div v-if="message.fileName" class="message-attachment"><File :size="15" /><span>{{ message.fileName }}</span></div>

        <section v-if="message.role === 'assistant' && message.timeline?.length" class="timeline-block">
          <button class="disclosure-button" type="button" :aria-expanded="message.showTimeline" @click="message.showTimeline = !message.showTimeline">
            <span class="tl-dot" :class="{ run: chat.actions.messageIsStreaming(message), err: message.timeline.some((entry) => entry.type === 'error'), ok: message.done && !message.timeline.some((entry) => entry.type === 'error') }"></span>
            <span>{{ message.timeline.some((entry) => entry.type === 'error') ? '执行记录 · 有异常' : (message.done ? '处理过程' : '处理进度') }}</span>
            <span class="timeline-count mono-time">{{ chat.actions.timelineSummary(message) }}</span>
            <component :is="message.showTimeline ? ChevronDown : ChevronRight" :size="15" class="disclosure-chevron" />
          </button>
          <div v-if="message.showTimeline" class="timeline-content">
            <div v-for="(entry, index) in message.timeline" :key="index" class="timeline-entry" :class="`entry-${entry.type}`">
              <span class="timeline-marker" :class="{ 'is-error': entry.type === 'error' || ['failed', 'cancelled'].includes(entry.status) }"><AlertCircle v-if="entry.type === 'error' || ['failed', 'cancelled'].includes(entry.status)" :size="12" /><LoaderCircle v-else-if="entry.status === 'running' && entry.endedAt == null" :size="12" class="spin" /><Check v-else-if="entry.endedAt != null" :size="12" /><span v-else></span></span>
              <div v-if="entry.type === 'thinking' || entry.type === 'step'" class="timeline-thinking"><span>{{ chat.actions.progressEntryLabel(entry) }}</span><ul v-if="entry.sources?.length" class="progress-sources"><li v-for="(source, sourceIndex) in entry.sources" :key="sourceIndex">{{ source }}</li></ul></div>
              <div v-else-if="entry.type === 'error'" class="timeline-error"><strong>{{ entry.message }}</strong><span v-if="entry.detail">{{ entry.detail }}</span></div>
              <div v-else class="timeline-tool"><span class="progress-entry-label">{{ chat.actions.progressEntryLabel(entry) }}</span><span>{{ ({ running: '运行中', completed: '已完成', failed: '调用失败', cancelled: '已停止' })[entry.status] || entry.status }}</span></div>
              <span v-if="entry.endedAt && entry.t0" class="entry-duration">{{ chat.actions.fmtStep(entry.endedAt - entry.t0) }}</span>
            </div>
          </div>
        </section>

        <div v-if="message.content" v-highlight class="markdown-content" v-html="chat.actions.renderMarkdown(chat.actions.messageBody(message))"></div>
        <div v-else-if="message.role === 'assistant' && chat.actions.messageIsStreaming(message) && !message.timeline?.length" class="thinking-placeholder"><span></span><span></span><span></span></div>

        <section v-if="message.role === 'assistant' && message.clarify" class="clarify-card" aria-label="需求澄清">
          <div class="clarify-head"><MessageCircle :size="15" /><strong>需要先确认一下</strong><span>不确定你想要哪种结果，选一个方向，或在下面直接补充说明</span></div>
          <div class="clarify-options">
            <button v-for="option in message.clarify.options" :key="option.intent" type="button" class="clarify-option" :disabled="message.clarify.sent || chat.state.sending" @click="chat.actions.answerClarify(message, option)">
              <span class="clarify-option-label">{{ option.label }}</span>
              <span class="clarify-option-hint">{{ option.hint }}</span>
            </button>
          </div>
          <div v-if="!message.clarify.sent" class="clarify-free">
            <textarea v-model="message.clarifyText" rows="2" placeholder="也可以直接写下你的想法…" aria-label="补充说明" @keydown="chat.actions.clarifyKeydown(message, $event)"></textarea>
            <button type="button" class="clarify-send" :disabled="chat.state.sending || !message.clarifyText.trim()" @click="chat.actions.answerClarify(message, null)">按我的说明继续</button>
          </div>
          <p v-else class="clarify-note">已按你的选择继续提问。</p>
        </section>

        <section v-if="message.references?.length" class="references-block">
          <button class="disclosure-button" type="button" :aria-expanded="message.showReferences" @click="message.showReferences = !message.showReferences"><Link2 :size="15" /><span>参考来源</span><span class="timeline-count">{{ message.references.length }}</span><component :is="message.showReferences ? ChevronDown : ChevronRight" :size="15" class="disclosure-chevron" /></button>
          <div v-if="message.showReferences" class="reference-list">
            <a v-for="ref in message.references" :key="ref.url" :href="ref.url" target="_blank" rel="noopener noreferrer" class="reference-link"><span class="reference-copy"><strong>{{ ref.title }}</strong><small>{{ ref.url }}</small></span><ExternalLink :size="14" /></a>
          </div>
        </section>

        <a v-if="message.pptFile" class="download-link" :href="chat.actions.downloadHref(message.pptFile)" download><Download :size="16" /> 下载生成的 PPT</a>
        <div v-if="message.role === 'assistant' && message.recommend?.length" class="recommendations"><span class="recommend-label">接下来可以</span><button v-for="(question, index) in message.recommend" :key="index" type="button" @click="chat.actions.sendRecommendation(question)">{{ chat.actions.recommendationLabel(question) }}<ArrowUp :size="13" /></button></div>
        <button v-if="message.role === 'assistant' && message.content" class="copy-message icon-button" type="button" aria-label="复制回答" title="复制回答" @click="chat.actions.copyText(chat.actions.normalizeBrandText(message.content))"><Copy :size="14" /></button>
      </div>
      <div v-if="message.role === 'user'" class="user-avatar">你</div>
    </div>
  </section>

  <footer ref="composerArea" class="composer-area">
    <div class="composer-wrap">
      <div v-if="chat.state.skillCopy" class="skill-bar" role="status">{{ chat.state.skillCopy.bar }}</div>
      <OptionPanel :panel="chat.state.optionPanel" :selection="chat.state.optionSelection" :chat.state.sending="chat.state.sending" @toggle="chat.actions.toggleOption" @send="chat.actions.sendSelectedOptions" />
      <div class="mode-strip" role="tablist" aria-label="助手模式">
        <button v-for="mode in modes" :key="mode.id" class="mode-option" :class="{ selected: ctx.activeMode === mode.id }" role="tab" :aria-selected="ctx.activeMode === mode.id" type="button" :disabled="chat.state.sending" @click="chat.actions.chooseMode(mode.id)">
          <component :is="mode.icon" :size="16" /><span>{{ mode.label }}</span><Check v-if="ctx.activeMode === mode.id" :size="13" class="mode-check" />
        </button>
      </div>

      <div class="composer-box" :class="{ 'composer-focused': chat.state.input.length > 0 || chat.state.selectedFile || chat.state.docSource, 'composer-disabled': chat.state.uploadBusy }">
        <div v-if="chat.state.selectedFile" class="attachment-chip"><div class="attachment-icon"><FileText :size="16" /></div><div class="attachment-info"><strong>{{ chat.state.selectedFile.name }}</strong><small>{{ chat.state.uploadBusy ? '正在上传并解析' : `${formatBytes(chat.state.selectedFile.size)} · 已就绪` }}</small></div><LoaderCircle v-if="chat.state.uploadBusy" :size="16" class="spin attachment-spinner" /><button v-else class="icon-button" type="button" aria-label="移除文件" @click="chat.actions.removeSelectedFile"><X :size="16" /></button></div>
        <div v-else-if="chat.state.docSource" class="attachment-chip"><div class="attachment-icon"><FileText :size="16" /></div><div class="attachment-info"><strong>{{ chat.state.docSource.fileName }}</strong><small>文档库 · {{ chat.state.docSource.charCount }} 字 · 按父子分段检索</small></div><button class="icon-button" type="button" aria-label="移除文档来源" @click="chat.state.docSource = null"><X :size="16" /></button></div>
        <textarea ref="composer" v-model="chat.state.input" rows="1" :disabled="chat.state.sending || chat.state.uploadBusy" :placeholder="chat.state.docSource ? `想问《${chat.state.docSource.fileName}》里的什么？` : chat.state.selectedFile ? '描述你想了解文件的什么内容…' : ctx.activeMode === 'ppt' ? '描述你想制作的演示文稿…' : chat.state.skillCopy ? chat.state.skillCopy.placeholder : '给 Hotline 发消息…'" aria-label="输入消息" @keydown="chat.actions.submitFromKeyboard" />
        <div class="composer-bottom">
          <div class="composer-tools">
            <input ref="fileInput" class="visually-hidden" type="file" accept=".pdf,.doc,.docx,.txt,.png,.jpg,.jpeg" @change="chat.actions.onFilePicked($event)" />
            <button class="attach-button icon-button" type="button" :disabled="chat.state.uploadBusy || chat.state.sending" aria-label="上传文件" title="上传文件" @click="pickFile"><Paperclip :size="17" /></button>
            <span v-if="chat.state.skillCopy" class="composer-hint">{{ chat.state.skillCopy.hintLabel }} · <kbd>{{ chat.state.skillCopy.hintKey }}</kbd> 发送</span>
            <span v-else class="composer-hint"><kbd>Enter</kbd> 发送 <span class="hint-divider"></span><kbd>Shift Enter</kbd> 换行</span>
          </div>
          <div class="send-actions">
            <span v-if="chat.state.input.length" class="char-count">{{ chat.state.input.length }}</span>
            <button v-if="chat.state.sending" class="send-button stop-button" type="button" aria-label="停止生成" title="停止生成" @click="chat.actions.stopMessage"><Square :size="15" fill="currentColor" /></button>
            <button v-else class="send-button" type="button" aria-label="发送消息" title="发送消息" :disabled="!chat.state.canSend" @click="chat.actions.sendMessage"><ArrowUp :size="18" /></button>
          </div>
        </div>
      </div>
      <div v-if="chat.state.isWelcome" class="quick-prompts" aria-label="试试这些任务">
        <button v-for="prompt in quickPrompts" :key="prompt.text" class="quick-prompt" type="button" @click="chat.actions.choosePrompt(prompt.text)">
          <component :is="prompt.icon" :size="15" /><span>{{ prompt.text }}</span><ArrowUp :size="13" class="prompt-arrow" />
        </button>
      </div>
    </div>
  </footer>
</template>
