<script setup>
import { inject } from 'vue'
import { FileText, Plus } from 'lucide-vue-next'
import { DOCUMENTS_KEY } from '../app/keys'

const documents = inject(DOCUMENTS_KEY)
</script>

<template>
  <div class="ui-empty">
    <div class="ui-empty-icon"><FileText :size="26" /></div>
    <h3>管理文档</h3>
    <p>Markdown、PDF、Word 上传后转成 Markdown，向量化之后就能直接引用问答。</p>
    <button class="primary-button" type="button" @click="documents.actions.openDocs"><Plus :size="15" />上传文档</button>
  </div>
</template>
