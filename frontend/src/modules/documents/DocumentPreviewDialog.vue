<script setup>
import { inject } from 'vue'
import { AlertCircle, Check, Eye, LoaderCircle, X } from 'lucide-vue-next'
import { DOCUMENTS_KEY } from '../app/keys'

const documents = inject(DOCUMENTS_KEY)
</script>

<template>
  <div class="modal-backdrop preview-backdrop" @click.self="documents.actions.closeDocPreview">
    <section class="dialog doc-preview-dialog" role="dialog" aria-modal="true" aria-labelledby="doc-preview-title">
      <div class="dialog-heading"><div class="dialog-symbol"><Eye :size="19" /></div><button class="icon-button" type="button" aria-label="关闭文档预览" @click="documents.actions.closeDocPreview"><X :size="18" /></button></div>
      <h2 id="doc-preview-title">分段预览</h2>
      <p>{{ documents.state.previewDoc?.fileName }}</p>

      <div v-if="documents.state.docPreviewBusy" class="preview-loading"><LoaderCircle :size="20" class="spin" /><span>正在分析 Markdown 分段…</span></div>
      <div v-else-if="documents.state.docPreviewError" class="skill-feedback error"><AlertCircle :size="15" /><span>{{ documents.state.docPreviewError }}</span></div>
      <template v-else-if="documents.state.docPreview">
        <div class="preview-stats" aria-label="分段统计">
          <article><span>子分段</span><strong>{{ documents.state.docPreview.summary.childCount }}</strong><small>{{ documents.state.docPreview.summary.averageChunkChars }} 字 / 块（平均）</small></article>
          <article><span>章节</span><strong>{{ documents.state.docPreview.summary.sectionCount }}</strong><small>{{ documents.state.docPreview.summary.parentCount }} 个长章节保留父段</small></article>
          <article><span>分段范围</span><strong>{{ documents.state.docPreview.summary.minChunkChars }}–{{ documents.state.docPreview.summary.maxChunkChars }}</strong><small>目标 {{ documents.state.docPreview.settings.chunkSize }} 字</small></article>
          <article><span>图片描述</span><strong>{{ documents.state.docPreview.summary.captionCount }}/{{ documents.state.docPreview.summary.imageCount }}</strong><small>有描述 / 图片总数</small></article>
        </div>
        <div class="preview-rule"><code>{{ documents.state.docPreview.settings.chunkSize }}</code> 字目标块 · <code>{{ documents.state.docPreview.settings.chunkOverlap }}</code> 字重叠 · {{ documents.state.docPreview.settings.countingRule }}</div>
        <div class="preview-tabs" role="tablist" aria-label="预览内容">
          <button type="button" role="tab" :aria-selected="documents.state.docPreviewTab === 'chunks'" :class="{ active: documents.state.docPreviewTab === 'chunks' }" @click="documents.state.docPreviewTab = 'chunks'">分段明细 {{ documents.state.docPreview.summary.childCount }}</button>
          <button type="button" role="tab" :aria-selected="documents.state.docPreviewTab === 'images'" :class="{ active: documents.state.docPreviewTab === 'images' }" @click="documents.state.docPreviewTab = 'images'">图片描述 {{ documents.state.docPreview.summary.captionCount }}/{{ documents.state.docPreview.summary.imageCount }}</button>
        </div>
        <div v-if="documents.state.docPreviewTab === 'chunks'" class="preview-panel chunk-preview-list">
          <details v-for="section in documents.state.docPreview.sections" :key="section.index" class="preview-section" :open="section.index === 1">
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
          <div v-if="documents.state.docPreview.images.length === 0" class="skill-empty">这份文档没有图片。</div>
          <article v-for="image in documents.state.docPreview.images" :key="image.index" class="image-preview-item">
            <a :href="documents.actions.downloadHref(image.src)" target="_blank" rel="noopener"><img :src="documents.actions.downloadHref(image.src)" :alt="image.alt || `文档图片 ${image.index}`" /></a>
            <div><span>图片 {{ image.index }}<em v-if="image.caption">{{ image.captionSource === 'generated' ? 'AI 图注' : '原文说明' }}</em></span><strong>{{ image.alt || '无原始替代文本' }}</strong><p>{{ image.caption || '暂无多模态描述' }}</p></div>
          </article>
        </div>
      </template>
      <div class="dialog-actions"><button class="secondary-button" type="button" @click="documents.actions.closeDocPreview">关闭</button></div>
    </section>
  </div>
</template>
