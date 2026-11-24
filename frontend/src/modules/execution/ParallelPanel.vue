<script setup>
import { onUnmounted, ref } from 'vue'
import { createParallelRuns, getHarnessWorkspaces, parallelStreamUrl } from '../../api'

const props = defineProps({ apiBase: { type: String, default: '' } })

const conversationId = ref(`parallel-${Date.now().toString(36)}`)
const agent = ref('chat')
const workspaceId = ref('')
const tasks = ref([{ text: '' }])
const workspaces = ref([])
const busy = ref(false)
const error = ref('')
const cards = ref([])
const streamState = ref('idle')
let source = null

const statusLabels = { queued: '排队中', running: '执行中', completed: '已完成', failed: '失败', cancelled: '已取消' }

function addTask() {
  tasks.value.push({ text: '' })
}

function removeTask(index) {
  tasks.value.splice(index, 1)
  if (!tasks.value.length) tasks.value.push({ text: '' })
}

async function loadWorkspaces() {
  try {
    const result = await getHarnessWorkspaces(props.apiBase)
    workspaces.value = result?.items || result?.workspaces || []
  } catch {
    workspaces.value = []
  }
}

function closeStream() {
  source?.close()
  source = null
}

function applyEvent(payload) {
  const card = cards.value.find(item => item.id === payload.runId)
  if (!card) return
  const event = payload.event || {}
  if (event.type === 'text') card.text += String(event.content || '')
  else if (event.type === 'error') {
    card.error = String(event.content || '')
    card.status = 'failed'
  } else if (event.type === 'complete') card.status = 'completed'
  else if (event.type === 'policy' && event.policy?.workspacePath) card.workspacePath = event.policy.workspacePath
}

function connect() {
  closeStream()
  const ids = cards.value.map(card => card.id)
  if (!ids.length) return
  streamState.value = 'connecting'
  // 合并流：所有子任务共用一条连接，避开浏览器同源连接数上限。
  source = new EventSource(parallelStreamUrl(props.apiBase, ids))
  source.onopen = () => { streamState.value = 'live' }
  source.onmessage = message => {
    try {
      applyEvent(JSON.parse(message.data))
    } catch {
      // 单条事件格式异常不影响其它子任务。
    }
  }
  source.addEventListener('done', () => {
    streamState.value = 'complete'
    closeStream()
  })
  source.onerror = () => {
    if (streamState.value !== 'complete') streamState.value = 'reconnecting'
  }
}

async function submit() {
  const list = tasks.value.map(item => item.text.trim()).filter(Boolean)
  if (!list.length) {
    error.value = '至少填写一个子任务'
    return
  }
  error.value = ''
  busy.value = true
  try {
    const result = await createParallelRuns(props.apiBase, {
      conversationId: conversationId.value.trim(),
      tasks: list.map(text => ({
        agent: agent.value,
        query: text,
        workspaceId: workspaceId.value || undefined,
      })),
    })
    cards.value = (result.runs || []).map(run => ({
      id: run.run_id,
      slot: run.slot,
      status: run.status,
      text: '',
      error: '',
      workspacePath: '',
    }))
    connect()
  } catch (failure) {
    error.value = failure.message || '派发失败'
  } finally {
    busy.value = false
  }
}

loadWorkspaces()
onUnmounted(closeStream)
</script>

<template>
  <section class="parallel-panel">
    <header class="parallel-head">
      <div>
        <strong>并行派发</strong>
        <span>一次派发多个子任务，各占一个隔离目录并行执行</span>
      </div>
      <span class="parallel-state">{{ streamState }}</span>
    </header>

    <div class="parallel-form">
      <label>会话标识<input v-model="conversationId" placeholder="parallel-xxx" /></label>
      <label>助手<select v-model="agent"><option value="chat">对话助手</option><option value="skills">技能助手</option><option value="deep">深度检索</option></select></label>
      <label>工作区<select v-model="workspaceId"><option value="">不绑定工作区</option><option v-for="item in workspaces" :key="item.workspace_id || item.id" :value="item.workspace_id || item.id">{{ item.name || item.workspace_id }}</option></select></label>
    </div>

    <div class="parallel-tasks">
      <label v-for="(item, index) in tasks" :key="index" class="parallel-task-input">
        <span>子任务 {{ index + 1 }}</span>
        <textarea v-model="item.text" rows="2" placeholder="描述这个子任务要做什么"></textarea>
        <button type="button" class="text-action" @click="removeTask(index)">移除</button>
      </label>
      <button type="button" class="button button-subtle" @click="addTask">添加子任务</button>
    </div>

    <div class="parallel-actions">
      <button type="button" class="button button-primary" :disabled="busy" @click="submit">{{ busy ? '派发中…' : '派发' }}</button>
      <span v-if="error" role="alert" class="parallel-error">{{ error }}</span>
    </div>

    <div v-if="cards.length" class="parallel-cards">
      <article v-for="card in cards" :key="card.id" class="parallel-card">
        <header><strong>{{ card.slot }}</strong><span>{{ statusLabels[card.status] || card.status }}</span></header>
        <p v-if="card.text" class="parallel-card-text">{{ card.text }}</p>
        <p v-else-if="card.error" class="parallel-card-error">{{ card.error }}</p>
        <p v-else class="parallel-card-text muted">等待输出…</p>
        <small v-if="card.workspacePath">隔离目录：{{ card.workspacePath }}</small>
      </article>
    </div>
  </section>
</template>

<style scoped>
.parallel-panel {
  border: 1px solid var(--line, rgba(148, 163, 184, 0.24));
  border-radius: 12px;
  padding: 16px;
  display: grid;
  gap: 12px;
  background: rgba(15, 23, 42, 0.35);
}
.parallel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.parallel-head strong { display: block; font-size: 14px; }
.parallel-head span { font-size: 12px; opacity: 0.72; }
.parallel-state { font-size: 11px; opacity: 0.6; text-transform: uppercase; }
.parallel-form {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
}
.parallel-form label { display: grid; gap: 4px; font-size: 12px; opacity: 0.82; }
.parallel-form input,
.parallel-form select,
.parallel-task-input textarea {
  border: 1px solid rgba(148, 163, 184, 0.28);
  border-radius: 8px;
  padding: 6px 8px;
  background: rgba(2, 6, 23, 0.5);
  color: inherit;
  font: inherit;
  font-size: 12px;
}
.parallel-tasks { display: grid; gap: 8px; }
.parallel-task-input { display: grid; gap: 4px; font-size: 12px; }
.parallel-task-input span { opacity: 0.72; }
.parallel-actions { display: flex; align-items: center; gap: 10px; }
.parallel-error { color: #f87171; font-size: 12px; }
.parallel-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 10px;
}
.parallel-card {
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 10px;
  padding: 10px;
  display: grid;
  gap: 6px;
  background: rgba(2, 6, 23, 0.4);
}
.parallel-card header { display: flex; justify-content: space-between; font-size: 12px; }
.parallel-card-text { margin: 0; font-size: 12px; line-height: 1.6; white-space: pre-wrap; max-height: 220px; overflow: auto; }
.parallel-card-text.muted { opacity: 0.55; }
.parallel-card-error { margin: 0; font-size: 12px; color: #f87171; }
.parallel-card small { font-size: 11px; opacity: 0.6; word-break: break-all; }
</style>
