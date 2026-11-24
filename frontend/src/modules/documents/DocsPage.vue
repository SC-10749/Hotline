<script setup>
import { inject } from 'vue'
import { FileText, Plus } from 'lucide-vue-next'
import { DOCUMENTS_KEY } from '../app/keys'

const documents = inject(DOCUMENTS_KEY)
</script>

<template>
  <div class="page-empty-state">
    <div class="page-empty-icon"><FileText :size="44" /></div>
    <h2>管理文档</h2>
    <button class="primary-button" type="button" @click="documents.actions.openDocs"><Plus :size="15" />上传文档</button>
  </div>
</template>
