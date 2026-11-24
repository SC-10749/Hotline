<script setup>
import { computed, inject } from 'vue'
import { Bot, Plus, Workflow } from 'lucide-vue-next'
import { BOTS_KEY } from '../app/keys'

const bots = inject(BOTS_KEY)

// CI 工作流开关：状态、目标与提示都来自后端，前端不自己猜仓库与工作流。
// 后端查 GitHub 要几秒，读取期间显示"读取中"，别把没读到当成"未配置"。
const ciLoading = computed(() => bots.state.ciWorkflow.enabled === null && !bots.state.ciWorkflow.message)

const ciStateText = computed(() => {
  const ci = bots.state.ciWorkflow
  if (ciLoading.value) return '读取中'
  if (!ci.configured) return '未配置'
  return ci.enabled ? '已开启' : '已关闭'
})

const ciTarget = computed(() => [bots.state.ciWorkflow.repository, bots.state.ciWorkflow.workflow].filter(Boolean).join(' · '))

const ciHint = computed(() => {
  const ci = bots.state.ciWorkflow
  if (ciLoading.value) return '正在读取 GitHub Actions 工作流状态'
  if (!ci.configured) return ci.message || '未配置 GitHub Token 与仓库地址，无法启停工作流'
  return ci.enabled ? '推送与 PR 会触发校验' : '推送与 PR 不再触发校验'
})
</script>

<template>
  <div class="bot-sidebar">
    <button class="page-create" type="button" @click="bots.actions.openBotForm()"><Plus :size="18" />新建机器人</button>
    <nav class="bot-nav" aria-label="机器人列表">
      <div v-for="bot in bots.state.bots" :key="bot.bot_id" class="bot-nav-row" :class="{ active: bots.state.selectedBotId === bot.bot_id }">
        <button type="button" class="bot-nav-name" @click="bots.actions.selectBot(bot)"><img v-if="bots.actions.botAvatar(bot)" class="bot-avatar" :src="bots.actions.botAvatar(bot)" alt="" /><Bot v-else :size="16" /><span>{{ bot.name }}</span></button>
        <label class="switch switch-pill" :title="bot.enabled ? '已开启：所有会话都复用它' : '已关闭'"><input type="checkbox" :checked="bot.enabled" @change="bots.actions.toggleBot(bot)" /><span class="switch-track" aria-hidden="true"></span></label>
      </div>
    </nav>
    <p v-if="!bots.state.bots.length" class="bot-nav-empty">还没有机器人</p>
    <div class="bot-ci">
      <div class="bot-ci-head">
        <Workflow :size="15" />
        <strong>CI 工作流</strong>
        <label class="switch switch-pill" :title="ciHint"><input type="checkbox" :checked="bots.state.ciWorkflow.enabled === true" :disabled="!bots.state.ciWorkflow.configured || bots.state.ciBusy" @change="bots.actions.toggleCiWorkflow" /><span class="switch-track" aria-hidden="true"></span></label>
      </div>
      <p class="bot-ci-meta"><span class="plugin-state" :class="{ off: !bots.state.ciWorkflow.enabled }">{{ ciStateText }}</span>{{ ciTarget ? ` · ${ciTarget}` : '' }}</p>
      <p class="bot-ci-hint">{{ ciHint }}</p>
    </div>
  </div>
</template>
