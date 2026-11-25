<script setup>
import { inject } from 'vue'
import { Archive, Download, LoaderCircle } from 'lucide-vue-next'
import { CHAT_KEY } from '../app/keys'

const chat = inject(CHAT_KEY)
</script>

<template>
  <div class="ui-empty">
    <div class="ui-empty-icon"><Archive :size="26" /></div>
    <h3>导出为 JSON</h3>
    <p>打包全部会话与消息，用于备份或迁移。</p>
    <button class="primary-button" type="button" :disabled="chat.state.exportingHistory" @click="chat.actions.exportChatHistory"><LoaderCircle v-if="chat.state.exportingHistory" :size="15" class="spin" /><Download v-else :size="15" />{{ chat.state.exportingHistory ? '正在导出' : '开始导出' }}</button>
  </div>
</template>
