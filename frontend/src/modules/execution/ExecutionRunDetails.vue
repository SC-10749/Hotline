<script setup>
import { ref } from 'vue'
import ArtifactList from '../artifacts/ArtifactList.vue'
import ContextSnapshots from '../context_engineering/ContextSnapshots.vue'

const props = defineProps({
  run: { type: Object, required: true },
  items: { type: Array, default: () => [] },
  loading: Boolean,
  error: { type: String, default: '' },
  output: { type: String, default: '' },
  actionBusy: Boolean,
  streamState: { type: String, default: 'idle' },
  apiBase: { type: String, default: '' },
})
defineEmits(['refresh', 'cancel', 'retry', 'duplicate'])
const tab = ref('result')
const labels = { queued: '排队中', running: '运行中', completed: '已完成', failed: '失败', cancelled: '已取消' }
const streamLabels = { connecting: '正在连接实时事件', live: '实时事件已连接', reconnecting: '实时事件重连中', complete: '事件流已结束', failed: '实时事件未连接' }
const toolLabels = { running: '调用中', completed: '调用成功', failed: '调用失败', cancelled: '调用已停止' }

function exportTrace() {
  const blob = new Blob([JSON.stringify({ run: props.run.raw, events: props.items }, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `run-${props.run.id}.json`
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
</script>

<template>
  <section class="run-detail-panel" aria-label="运行详情">
    <div class="run-detail-top">
      <div class="detail-title-group"><div class="detail-run-id">{{ run.id }} · {{ labels[run.status] || run.status }}</div><h2>{{ run.title }}</h2><p>{{ run.agent }} · {{ run.elapsed }}</p></div>
      <div class="detail-toolbar">
        <button class="button button-subtle" :disabled="loading" @click="$emit('refresh')">刷新事件</button>
        <button v-if="['queued', 'running'].includes(run.status)" class="button button-stop" :disabled="actionBusy || !!run.raw.cancel_requested" @click="$emit('cancel')">{{ run.raw.cancel_requested ? '停止请求已提交' : '停止运行' }}</button>
        <button v-if="['failed', 'cancelled'].includes(run.status)" class="button button-subtle" :disabled="actionBusy" @click="$emit('retry')">重试运行</button>
        <button class="button button-subtle" :disabled="actionBusy" @click="$emit('duplicate')">复制配置</button>
      </div>
    </div>
    <div class="detail-tabs"><button :class="{ active: tab === 'result' }" @click="tab = 'result'">输入与结果</button><button :class="{ active: tab === 'trace' }" @click="tab = 'trace'">Trace {{ items.length }}</button><button :class="{ active: tab === 'request' }" @click="tab = 'request'">提交信息</button><button :class="{ active: tab === 'context' }" @click="tab = 'context'">上下文快照</button><button :class="{ active: tab === 'artifacts' }" @click="tab = 'artifacts'">运行产物</button></div>
    <div class="detail-scroll">
      <p v-if="streamLabels[streamState]" class="execution-stream-state" role="status">{{ streamLabels[streamState] }}</p>
      <p v-if="run.raw.error" role="alert">{{ run.raw.error }}</p>
      <p v-if="error" role="alert">{{ error }} <button class="text-action" @click="$emit('refresh')">重试</button></p>
      <p v-if="loading" role="status">正在读取运行事件…</p>
      <template v-if="tab === 'result'"><h3>任务输入</h3><pre class="execution-text">{{ run.raw.query }}</pre><h3>执行输出</h3><pre v-if="output" class="execution-text">{{ output }}</pre><p v-else>{{ ['queued', 'running'].includes(run.status) ? '等待执行输出' : '此运行没有文本输出' }}</p></template>
      <template v-else-if="tab === 'trace'">
        <button class="button button-subtle" :disabled="loading || !!error" @click="exportTrace">导出 Trace JSON</button>
        <p v-if="!items.length && !loading">此运行尚无事件</p>
        <p v-if="items.some(item => ['tool_start', 'tool_end'].includes(item.event?.type))">参数与结果为脱敏预览，超长内容会截断。</p>
        <details v-for="item in items" :key="item.event_id" class="execution-event">
          <summary>#{{ item.event_id }} · {{ item.event?.toolName || item.event?.type || '未知事件' }}<template v-if="toolLabels[item.event?.status]"> · {{ toolLabels[item.event.status] }}</template> · {{ item.created_at }}</summary>
          <template v-if="['tool_start', 'tool_end'].includes(item.event?.type)">
            <dl class="execution-request"><dt>调用编号</dt><dd>{{ item.event.toolCallId }}</dd><template v-if="item.event.durationMs != null"><dt>实际耗时</dt><dd>{{ item.event.durationMs }} ms</dd></template></dl>
            <p>{{ item.event.content }}</p>
            <template v-if="item.event.arguments !== undefined"><h3>调用参数</h3><p v-if="item.event.argumentsTruncated">参数预览已截断</p><pre class="execution-text">{{ JSON.stringify(item.event.arguments, null, 2) }}</pre></template>
            <template v-if="item.event.output !== undefined"><h3>返回结果</h3><p v-if="item.event.outputTruncated">结果预览已截断</p><pre class="execution-text">{{ JSON.stringify(item.event.output, null, 2) }}</pre></template>
          </template>
          <pre v-else class="execution-text">{{ JSON.stringify(item.event, null, 2) }}</pre>
        </details>
      </template>
      <dl v-else-if="tab === 'request'" class="execution-request"><dt>会话编号</dt><dd>{{ run.raw.conversation_id }}</dd><dt>执行模式</dt><dd>{{ run.raw.agent }}</dd><dt>文件编号</dt><dd>{{ run.raw.file_id || '未关联' }}</dd><dt>Worker</dt><dd>{{ run.raw.worker_id || '未分配' }}</dd><dt>创建时间</dt><dd>{{ run.raw.created_at }}</dd><dt>开始时间</dt><dd>{{ run.raw.started_at || '未开始' }}</dd><dt>结束时间</dt><dd>{{ run.raw.finished_at || '未结束' }}</dd></dl>
      <ArtifactList v-else-if="tab === 'artifacts'" :api-base="apiBase" :run-id="run.id" :refresh-key="`${run.status}:${items.filter(item => item.event?.type === 'artifact').at(-1)?.event_id || ''}`" />
      <ContextSnapshots v-else-if="tab === 'context'" :items="items" :loading="loading" :status="run.status" />
    </div>
  </section>
</template>
