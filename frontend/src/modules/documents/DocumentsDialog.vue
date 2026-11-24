<script setup>
import { inject, ref } from 'vue'
import { Activity, AlertCircle, Check, ChevronRight, Eye, FileText, LoaderCircle, Plus, Trash2, X } from 'lucide-vue-next'
import { CHAT_KEY, DOCUMENTS_KEY } from '../app/keys'

const documents = inject(DOCUMENTS_KEY)
const chat = inject(CHAT_KEY)
const docInput = ref(null)
</script>

<template>
  <div class="modal-backdrop" @click.self="documents.actions.closeDocs">
    <section class="dialog skills-dialog docs-dialog" role="dialog" aria-modal="true" aria-labelledby="docs-title">
      <div class="dialog-heading"><div class="dialog-symbol"><FileText :size="19" /></div><button class="icon-button" type="button" aria-label="关闭文档库" @click="documents.actions.closeDocs"><X :size="18" /></button></div>
      <h2 id="docs-title">文档库</h2>
      <p>支持 Markdown、PDF 和 Word。</p>
      <div class="skill-toolbar">
        <button class="primary-button" type="button" :disabled="documents.state.docBusy" @click="docInput.click()"><LoaderCircle v-if="documents.state.docBusy" :size="15" class="spin" /><Plus v-else :size="15" />{{ documents.state.docBusy ? '处理中' : '上传文档' }}</button>
        <input ref="docInput" class="skill-file-input" type="file" accept=".md,.markdown,.pdf,.docx,.doc" @change="documents.actions.chooseDocFile" />
        <button class="secondary-button" type="button" :disabled="documents.state.docBusy" @click="documents.actions.runCompensation"><Activity :size="15" />兜底补偿</button>
        <span class="skill-tally">{{ documents.state.docCounts.vectorized }} 已向量化 · {{ documents.state.docCounts.waiting }} 待处理 · {{ documents.state.docCounts.failed }} 失败</span>
      </div>
      <div v-if="documents.state.docMessage" class="skill-feedback" :class="documents.state.docMessage.type"><AlertCircle v-if="documents.state.docMessage.type === 'error'" :size="15" /><Check v-else :size="15" /><span>{{ documents.state.docMessage.text }}</span></div>
      <div class="skill-list">
        <div v-if="documents.state.docs.length === 0" class="skill-empty">还没有上传文档。</div>
        <article v-for="doc in documents.state.docs" :key="doc.fileId" class="skill-row" :class="{ off: doc.status === 'FAILED' }">
          <div class="skill-row-main">
            <div class="skill-row-name"><span>{{ doc.fileName }}</span><em :class="documents.actions.docStatusClass(doc.status)"><LoaderCircle v-if="['CONVERTING', 'VECTORIZING'].includes(doc.status)" :size="10" class="spin" />{{ documents.actions.docStatusLabel(doc.status) }}</em></div>
            <p class="skill-row-desc">{{ doc.convertedVia === 'mineru' ? 'MinerU 解析' : doc.convertedVia === 'markdown' ? 'Markdown 直通' : '尚未转换' }} · {{ doc.charCount }} 字 · {{ doc.imageCount }} 张图（{{ doc.captionCount }} 张有图注）</p>
            <div class="skill-row-meta"><code>{{ doc.docType }}</code><a v-if="doc.markdownUrl" :href="documents.actions.downloadHref(doc.markdownUrl)" target="_blank" rel="noopener">Markdown v{{ doc.version }}</a></div>
            <p v-if="doc.errorMsg" class="doc-error">{{ doc.errorMsg }}</p>
            <div v-if="documents.state.expandingDoc === doc.fileId" class="doc-versions">
              <div v-for="item in documents.state.docVersions[doc.fileId] || []" :key="item.version" class="doc-version"><b>v{{ item.version }}</b><code>{{ item.note }}</code><a :href="documents.actions.downloadHref(item.markdownUrl)" target="_blank" rel="noopener">{{ item.markdownUrl }}</a><span>{{ item.createTime }}</span></div>
              <p v-if="!documents.state.docVersions[doc.fileId]?.length" class="doc-version-empty">暂无版本记录</p>
            </div>
          </div>
          <div class="skill-row-actions">
            <button v-if="doc.markdownUrl" class="secondary-button" type="button" title="查看分段、字数和图片描述" @click="documents.actions.openDocPreview(doc)"><Eye :size="14" />预览</button>
            <button v-if="doc.markdownUrl" class="secondary-button" type="button" title="就这份文档提问" @click="chat.actions.askFromDoc(doc)">提问</button>
            <button class="secondary-button" type="button" :disabled="documents.state.docBusy || !doc.markdownUrl || doc.status === 'VECTORIZED' || doc.status === 'VECTORIZING'" :title="doc.status === 'VECTORIZED' ? '这份文档已经完成向量化' : '按标题层级做父子分段并向量化'" @click="documents.actions.runVectorize(doc)">{{ doc.status === 'VECTORIZED' ? '已完成' : doc.status === 'VECTORIZING' ? '处理中' : '向量化' }}</button>
            <button class="icon-button" type="button" title="版本记录" aria-label="版本记录" @click="documents.actions.toggleDocVersions(doc)"><ChevronRight :size="17" /></button>
            <template v-if="documents.state.deletingDoc === doc.fileId"><button class="secondary-button" type="button" @click="documents.state.deletingDoc = null">取消</button><button class="danger-button" type="button" @click="documents.actions.confirmRemoveDoc(doc)"><Trash2 :size="14" />确认删除</button></template>
            <button v-else class="icon-button" type="button" title="删除文档" aria-label="删除文档" @click="documents.state.deletingDoc = doc.fileId"><Trash2 :size="17" /></button>
          </div>
        </article>
      </div>
      <div class="dialog-actions"><button class="secondary-button" type="button" @click="documents.actions.closeDocs">关闭</button></div>
    </section>
  </div>
</template>
