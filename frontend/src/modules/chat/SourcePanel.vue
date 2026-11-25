<script setup>
import { nextTick, ref, watch } from 'vue'
import { ExternalLink, Link2, X } from 'lucide-vue-next'

const props = defineProps({
  open: { type: Boolean, default: false },
  references: { type: Array, default: () => [] },
  activeIndex: { type: Number, default: -1 },
})
const emit = defineEmits(['close'])

const panel = ref(null)
const closeButton = ref(null)

// 面板本身只是展示检索命中的来源：标题、域名、摘录都取自后端返回，不补造。
function hostOf(url) {
  try {
    return new URL(url).host.replace(/^www\./, '')
  } catch {
    return url
  }
}

watch(() => props.open, async (open) => {
  if (!open) return
  await nextTick()
  closeButton.value?.focus({ preventScroll: true })
})

function onKeydown(event) {
  if (event.key === 'Escape') {
    event.stopPropagation()
    emit('close')
  }
}
</script>

<template>
  <aside
    v-if="open"
    ref="panel"
    class="source-panel"
    aria-label="参考来源"
    tabindex="-1"
    @keydown="onKeydown"
  >
    <div class="source-panel-head">
      <h2>参考来源</h2>
      <span class="source-count">{{ references.length }}</span>
      <button ref="closeButton" class="icon-button" type="button" aria-label="关闭来源面板" title="关闭来源面板" @click="emit('close')"><X :size="16" /></button>
    </div>

    <div class="source-panel-body">
      <p class="source-panel-note">本轮回答命中的来源。标题、地址与摘录都来自检索结果，点开可回到原文核对。</p>
      <article
        v-for="(reference, index) in references"
        :key="reference.url"
        class="source-item"
        :class="{ 'is-active': index === activeIndex }"
      >
        <div class="source-item-head">
          <span class="source-index">{{ index + 1 }}</span>
          <span class="source-item-title">{{ reference.title }}</span>
        </div>
        <span class="source-item-host"><Link2 :size="11" />{{ hostOf(reference.url) }}</span>
        <p v-if="reference.content" class="source-item-excerpt">{{ reference.content }}</p>
        <a class="source-item-open" :href="reference.url" target="_blank" rel="noopener noreferrer">打开原文<ExternalLink :size="12" /></a>
      </article>
      <p v-if="!references.length" class="source-panel-note">这一轮没有可展示的来源。</p>
    </div>

    <p class="source-panel-foot">来源随回答一起返回，不展示未命中的检索结果。</p>
  </aside>
</template>
