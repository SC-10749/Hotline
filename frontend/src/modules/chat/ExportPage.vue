<script setup>
import { inject } from 'vue'
import { Archive, Download, LoaderCircle } from 'lucide-vue-next'
import { CHAT_KEY } from '../app/keys'

const chat = inject(CHAT_KEY)
</script>

<template>
  <div class="page-empty-state">
    <div class="page-empty-icon"><Archive :size="44" /></div>
    <h2>导出历史聊天</h2>
    <p>导出为 JSON 文件</p>
    <button class="primary-button" type="button" :disabled="chat.state.exportingHistory" @click="chat.actions.exportChatHistory"><LoaderCircle v-if="chat.state.exportingHistory" :size="15" class="spin" /><Download v-else :size="15" />{{ chat.state.exportingHistory ? '正在导出' : '导出 JSON' }}</button>
  </div>
</template>
