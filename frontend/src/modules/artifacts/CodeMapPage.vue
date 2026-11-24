<script setup>
import { computed, onScopeDispose, ref, watch } from 'vue'
import { ExternalLink, Home, RefreshCw } from 'lucide-vue-next'
import { apiUrl, getCodeMapStatus } from '../../api'

const props = defineProps({ apiBase: { type: String, default: '' } })
defineEmits(['home'])
const loading = ref(true)
const available = ref(false)
const error = ref('')
const refreshKey = ref(0)
let generation = 0
const mapUrl = computed(() => apiUrl(props.apiBase, `/code-map/hotline.html?v=${refreshKey.value}`))

async function refresh() {
  const request = ++generation
  loading.value = true
  error.value = ''
  available.value = false
  try {
    const status = await getCodeMapStatus(props.apiBase)
    if (request !== generation) return
    available.value = status.available
    refreshKey.value++
  } catch (failure) {
    if (request === generation) error.value = failure.message || '代码地图读取失败，请重试'
  } finally {
    if (request === generation) loading.value = false
  }
}

watch(() => props.apiBase, refresh, { immediate: true })
onScopeDispose(() => { generation++ })
</script>

<template>
  <section class="code-map-page" aria-labelledby="code-map-title">
    <header class="code-map-header">
      <h1 id="code-map-title">代码地图</h1>
      <div class="code-map-actions">
        <button class="secondary-button" type="button" :disabled="loading" @click="refresh"><RefreshCw :size="16" />刷新</button>
        <a v-if="available" class="secondary-button" :href="mapUrl" target="_blank" rel="noopener noreferrer"><ExternalLink :size="16" />独立打开</a>
        <button class="icon-button" type="button" aria-label="回到首页" title="回到首页" @click="$emit('home')"><Home :size="18" /></button>
      </div>
    </header>
    <p class="code-map-narrow-hint">横向滚动画布查看完整地图，也可选择独立打开。</p>
    <div v-if="loading" class="code-map-state" role="status">正在读取代码地图…</div>
    <div v-else-if="error" class="code-map-state" role="alert">
      <p>{{ error }}</p>
      <button class="secondary-button" type="button" @click="refresh">重试</button>
    </div>
    <div v-else-if="!available" class="code-map-state" role="status">
      <h2>尚未生成完整代码地图</h2>
      <p>将地图 HTML 和 vendor/mermaid.min.js 放入 data/code-map/hotline 后刷新。</p>
    </div>
    <div v-else class="code-map-canvas" tabindex="0" aria-label="代码地图画布，可横向滚动">
      <iframe :key="refreshKey" :src="mapUrl" title="Hotline 当前系统代码地图" sandbox="allow-scripts allow-same-origin" />
    </div>
  </section>
</template>

<style scoped>
:global(.workspace.workspace-code-map) { grid-template-rows: minmax(0, 1fr); min-height: 0; height: 100dvh; }
.code-map-page { display: flex; flex: 1; flex-direction: column; width: 100%; height: 100%; min-width: 0; min-height: 0; background: var(--canvas); }
.code-map-header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; flex: 0 0 auto; gap: 12px; padding: 16px 20px; border-bottom: 1px solid var(--line-soft); }
.code-map-header h1 { margin: 0; font-size: 24px; font-weight: 600; color: var(--text); }
.code-map-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.code-map-actions .secondary-button { display: inline-flex; align-items: center; gap: 6px; min-height: 38px; text-decoration: none; }
.code-map-canvas { flex: 1; min-height: 0; overflow: auto; }
.code-map-canvas iframe { display: block; width: 100%; min-width: 1080px; height: 100%; border: 0; }
.code-map-state { display: flex; flex: 1; flex-direction: column; align-items: center; justify-content: center; gap: 12px; padding: 24px; color: var(--text-secondary); text-align: center; overflow-wrap: anywhere; }
.code-map-state h2 { margin: 0; font-size: 18px; color: var(--text); }
.code-map-state p { max-width: 65ch; margin: 0; }
.code-map-narrow-hint { display: none; }
@media (max-width: 1132px) {
  .code-map-header { padding: 12px 16px; }
  .code-map-narrow-hint { display: block; flex: 0 0 auto; margin: 0; padding: 8px 16px; font-size: 12px; color: var(--muted); }
}
@media (max-width: 960px) {
  :global(.workspace.workspace-code-map) { height: calc(100dvh - 52px - env(safe-area-inset-bottom)); }
}
</style>
