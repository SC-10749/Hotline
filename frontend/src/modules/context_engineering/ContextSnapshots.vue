<script setup>
import { computed } from 'vue'

const props = defineProps({
  items: { type: Array, default: () => [] },
  loading: Boolean,
  status: { type: String, default: '' },
})
const snapshots = computed(() => props.items.filter(item => item.event?.type === 'context_snapshot' && item.event.snapshot))
const stages = { answer: '回答输入', 'retrieval-route': '检索路由', 'retrieval-sql': '检索 SQL 生成', 'skill-model': 'Skills 模型输入' }
const format = value => typeof value === 'string' ? value : JSON.stringify(value, null, 2)
</script>

<template>
  <section aria-label="运行上下文快照">
    <p>共 {{ snapshots.length }} 份调用前输入快照（已脱敏）。</p>
    <p v-if="loading" role="status">正在读取上下文快照…</p>
    <p v-else-if="!snapshots.length">{{ ['queued', 'running'].includes(status) ? '尚未记录快照，等待模型输入准备完成。' : '此运行没有记录上下文快照。历史运行不会根据当前配置补建快照。' }}</p>
    <details v-for="item in snapshots" :key="item.event_id" class="execution-event">
      <summary>#{{ item.event_id }} · {{ stages[item.event.snapshot.stage] || item.event.snapshot.stage }} · {{ item.created_at }}</summary>
      <dl class="execution-request"><dt>捕获时间</dt><dd>{{ item.event.snapshot.capturedAt }}</dd><dt>模型</dt><dd>{{ item.event.snapshot.modelName || '未指定' }}</dd><dt>模型配置</dt><dd>{{ item.event.snapshot.modelConfigured ? '已配置，调用前捕获' : '未配置，使用本地降级' }}</dd><dt>消息数</dt><dd>{{ item.event.snapshot.messageCount }}</dd></dl>
      <h3>上下文来源</h3><p v-if="item.event.snapshot.sourcesTruncated">来源信息已截断</p><pre class="execution-text">{{ format(item.event.snapshot.sources) }}</pre>
      <h3>准备发送的消息</h3><p v-if="item.event.snapshot.omittedMessages">省略 {{ item.event.snapshot.omittedMessages }} 条超限消息</p>
      <div v-for="(message, index) in item.event.snapshot.messages" :key="index">
        <strong>{{ index + 1 }} · {{ message.role }}</strong><span v-if="message.truncated"> · 内容预览已截断</span>
        <pre class="execution-text">{{ format(message.content) }}</pre>
        <template v-if="message.toolProtocol && Object.keys(message.toolProtocol).length"><p>工具消息关联<span v-if="message.toolProtocolTruncated"> · 关联预览已截断</span></p><pre class="execution-text">{{ format(message.toolProtocol) }}</pre></template>
      </div>
      <template v-if="item.event.snapshot.tools.length"><h3>本轮可用工具定义</h3><div v-for="(tool, index) in item.event.snapshot.tools" :key="index"><p v-if="tool.truncated">工具定义预览已截断</p><pre class="execution-text">{{ format(tool.definition) }}</pre></div></template>
      <p v-if="item.event.snapshot.omittedTools">省略 {{ item.event.snapshot.omittedTools }} 个超限工具定义</p>
    </details>
  </section>
</template>
