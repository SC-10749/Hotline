<script setup>
import { onScopeDispose, ref, watch } from 'vue'
import { cleanupHarnessArtifacts, downloadHarnessArtifact, getHarnessArtifactPreview, getHarnessArtifacts } from '../../api'

const props = defineProps({
  apiBase: { type: String, default: '' },
  runId: { type: String, default: '' },
  refreshKey: { type: String, default: '' },
})
const items = ref([])
const total = ref(0)
const offset = ref(0)
const limit = 25
const filter = ref('')
const loading = ref(false)
const error = ref('')
const message = ref('')
const previews = ref({})
const retentionDays = ref(30)
const cleaning = ref(false)
// 项目还没有统一身份体系，归属身份由使用者填写并随下载请求头发送。
const owner = ref(localStorage.getItem('harness-owner') || '')
const downloading = ref('')
let generation = 0

async function refresh() {
  const request = ++generation
  loading.value = true
  error.value = ''
  try {
    const result = await getHarnessArtifacts(props.apiBase, props.runId || filter.value.trim(), { limit, offset: offset.value, owner: owner.value.trim() })
    if (request !== generation) return
    if (result.total > 0 && offset.value >= result.total) {
      offset.value = Math.floor((result.total - 1) / limit) * limit
      return refresh()
    }
    total.value = result.total
    if (!total.value) offset.value = 0
    items.value = result.items || []
  } catch (failure) {
    if (request === generation) error.value = failure.message || '产物读取失败'
  } finally {
    if (request === generation) loading.value = false
  }
}
function changePage(next) {
  offset.value = next
  items.value = []
  refresh()
}
async function togglePreview(item) {
  const id = item.artifact_id
  if (previews.value[id]) {
    delete previews.value[id]
    return
  }
  previews.value[id] = { loading: true, content: '', truncated: false, error: '' }
  try {
    const result = await getHarnessArtifactPreview(props.apiBase, id, owner.value.trim())
    previews.value[id] = {
      loading: false,
      content: result?.content ?? '',
      truncated: Boolean(result?.truncated),
      error: '',
    }
  } catch (failure) {
    previews.value[id] = { loading: false, content: '', truncated: false, error: failure.message || '产物预览失败' }
  }
}
async function downloadArtifact(item) {
  if (downloading.value) return
  downloading.value = item.artifact_id
  message.value = ''
  try {
    const blob = await downloadHarnessArtifact(props.apiBase, item.artifact_id, owner.value.trim())
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = item.name
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    message.value = `已下载 ${item.name}`
  } catch (failure) {
    message.value = `下载失败：${failure.message || '产物服务不可用'}`
  } finally {
    downloading.value = ''
  }
}
function rememberOwner() {
  localStorage.setItem('harness-owner', owner.value.trim())
  offset.value = 0
  items.value = []
  total.value = 0
  refresh()
}
async function cleanupArtifacts() {
  if (cleaning.value) return
  const days = Number(retentionDays.value)
  if (!Number.isFinite(days) || days < 1) {
    message.value = '保留天数必须大于等于 1'
    return
  }
  cleaning.value = true
  message.value = ''
  try {
    const result = await cleanupHarnessArtifacts(props.apiBase, { retentionDays: days, deleteFiles: false })
    message.value = `已清理 ${result?.removed ?? 0} 个过期产物`
    await refresh()
  } catch (failure) {
    message.value = `清理失败：${failure.message || '产物服务不可用'}`
  } finally {
    cleaning.value = false
  }
}
watch([() => props.runId, () => props.apiBase, filter], () => {
  offset.value = 0
  items.value = []
  total.value = 0
  refresh()
}, { immediate: true, flush: 'sync' })
watch(() => props.refreshKey, refresh)
onScopeDispose(() => { generation += 1 })
</script>

<template>
  <section class="artifact-list" aria-label="登记产物">
    <div class="artifact-toolbar">
      <label v-if="!runId">按运行编号筛选 <input v-model="filter" placeholder="完整 runId" /></label>
      <label>归属身份 <input v-model="owner" placeholder="用于下载校验的身份标识" @change="rememberOwner" /></label>
      <span>共 {{ total }} 个登记产物</span>
      <button class="button button-subtle" :disabled="loading" @click="refresh">刷新产物</button>
      <label class="artifact-retention">保留天数 <input v-model.number="retentionDays" type="number" min="1" max="3650" /></label>
      <button class="button button-subtle" :disabled="cleaning" @click="cleanupArtifacts">{{ cleaning ? '清理中…' : '清理过期产物' }}</button>
    </div>
    <p v-if="message" role="status">{{ message }}</p>
    <p v-if="error" role="alert">{{ error }}。<template v-if="items.length">保留上次读取的记录。</template><button class="text-action" @click="refresh">重试</button></p>
    <p v-if="loading" role="status">正在读取产物…</p>
    <p v-else-if="!items.length && !error">{{ runId || filter ? '此运行没有登记产物' : '尚无登记产物' }}</p>
    <div :aria-busy="loading">
      <details v-for="item in items" :key="item.artifact_id" class="execution-event">
        <summary>{{ item.name }} · {{ item.size }} 字节 · {{ item.created_at }}</summary>
        <dl class="execution-request"><dt>产物编号</dt><dd>{{ item.artifact_id }}</dd><dt>所属运行</dt><dd>{{ item.run_id }}</dd><dt>文件类型</dt><dd>{{ item.content_type }}</dd><dt>存储方式</dt><dd>{{ item.storage_backend }}</dd><dt>归属身份</dt><dd>{{ item.owner || '未登记' }}</dd><dt>SHA-256</dt><dd>{{ item.sha256 }}</dd></dl>
        <div class="artifact-actions">
          <button class="button button-subtle" type="button" :disabled="downloading === item.artifact_id" @click="downloadArtifact(item)">{{ downloading === item.artifact_id ? '下载中…' : '下载文件' }}</button>
          <button class="button button-subtle" @click="togglePreview(item)">{{ previews[item.artifact_id] ? '收起预览' : '预览' }}</button>
        </div>
        <div v-if="previews[item.artifact_id]" class="artifact-preview-box">
          <p v-if="previews[item.artifact_id].loading" role="status">正在读取预览…</p>
          <p v-else-if="previews[item.artifact_id].error" role="alert">{{ previews[item.artifact_id].error }}</p>
          <template v-else>
            <pre class="artifact-preview-text">{{ previews[item.artifact_id].content || '（预览内容为空）' }}</pre>
            <p v-if="previews[item.artifact_id].truncated" class="artifact-note">内容已截断</p>
          </template>
        </div>
      </details>
    </div>
    <nav class="execution-pagination" aria-label="产物分页"><button class="button button-subtle" :disabled="loading || offset === 0" @click="changePage(offset - limit)">上一页</button><span aria-live="polite">{{ Math.floor(offset / limit) + 1 }} / {{ Math.max(1, Math.ceil(total / limit)) }}</span><button class="button button-subtle" :disabled="loading || offset + limit >= total" @click="changePage(offset + limit)">下一页</button></nav>
  </section>
</template>

<style scoped>
.artifact-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-bottom: 12px; }
.artifact-toolbar label { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.artifact-toolbar input { max-width: 100%; padding: 7px; border: 1px solid var(--h-line); border-radius: 5px; font: inherit; color: var(--h-text); background: var(--h-surface); }
.artifact-retention input { width: 84px; }
.artifact-list .execution-request dd { overflow-wrap: anywhere; }
.artifact-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.artifact-preview-box { margin-top: 10px; }
.artifact-preview-text { max-height: 320px; overflow: auto; margin: 0; padding: 10px; border: 1px solid var(--h-line-soft); border-radius: 5px; color: var(--h-secondary); background: var(--h-subtle); font: 11px/1.6 Consolas, "Microsoft YaHei", monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
