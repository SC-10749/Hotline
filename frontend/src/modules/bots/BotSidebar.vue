<script setup>
import { inject } from 'vue'
import { Bot, Plus } from 'lucide-vue-next'
import { BOTS_KEY } from '../app/keys'

const bots = inject(BOTS_KEY)
</script>

<template>
  <div class="bot-sidebar">
    <button class="page-create" type="button" @click="bots.state.bots.actions.openBotForm()"><Plus :size="18" />新建机器人</button>
    <nav class="bot-nav" aria-label="机器人列表">
      <div v-for="bot in bots.state.bots" :key="bot.bot_id" class="bot-nav-row" :class="{ active: bots.state.selectedBotId === bot.bot_id }">
        <button type="button" class="bot-nav-name" @click="bots.actions.selectBot(bot)"><img v-if="bots.actions.botAvatar(bot)" class="bot-avatar" :src="bots.actions.botAvatar(bot)" alt="" /><Bot v-else :size="16" /><span>{{ bot.name }}</span></button>
        <label class="switch switch-pill" :title="bot.enabled ? '已开启：所有会话都复用它' : '已关闭'"><input type="checkbox" :checked="bot.enabled" @change="bots.actions.toggleBot(bot)" /><span class="switch-track" aria-hidden="true"></span></label>
      </div>
    </nav>
    <p v-if="!bots.state.bots.length" class="bot-nav-empty">还没有机器人</p>
  </div>
</template>
