<script setup>
import { computed, inject } from 'vue'
import { Bot, Plus, Workflow } from 'lucide-vue-next'
import { BOTS_KEY, SKILLS_KEY } from '../app/keys'

const bots = inject(BOTS_KEY)
const skills = inject(SKILLS_KEY)

// CI 工作流开关：状态与提示都来自后端，前端不自己猜仓库与工作流。
const ciStateText = computed(() => {
  const ci = bots.state.ciWorkflow
  if (!ci.configured) return '未配置'
  return ci.enabled ? '已开启' : '已关闭'
})

const ciHint = computed(() => {
  const ci = bots.state.ciWorkflow
  if (!ci.configured) return ci.message || '未配置 GitHub Token 与仓库地址，无法启停工作流'
  const target = [ci.repository, ci.workflow].filter(Boolean).join(' · ')
  return `${target}｜${ci.enabled ? '推送与 PR 会触发校验' : '已停用：推送与 PR 不再触发校验'}`
})
</script>

<template>
  <section class="plugins-page">
    <div class="settings-section-copy"><Bot :size="22" /><div><h2>bot</h2></div><button class="primary-button" type="button" @click="bots.actions.openBotForm()"><Plus :size="15" />新建机器人</button></div>
    <div class="plugin-list">
      <div class="bot-row">
        <Workflow :size="22" />
        <div><strong>CI 工作流</strong><small>{{ ciHint }}</small></div>
        <span class="plugin-state">{{ ciStateText }}</span>
        <label class="switch switch-pill" :title="ciHint"><input type="checkbox" :checked="bots.state.ciWorkflow.enabled === true" :disabled="!bots.state.ciWorkflow.configured || bots.state.ciBusy" @change="bots.actions.toggleCiWorkflow" /><span class="switch-track" aria-hidden="true"></span></label>
      </div>
    </div>
    <form v-if="bots.state.showBotForm" class="schedule-form" @submit.prevent="bots.actions.submitBot">
      <label>机器人名称<input v-model="bots.state.botDraft.name" placeholder="例如：值班客服" /></label>
      <label>角色指令<textarea v-model="bots.state.botDraft.instruction" rows="3" placeholder="你是一位只回答售后问题的客服，结论先行、语气克制"></textarea></label>
      <label>绑定技能<select v-model="bots.state.botDraft.skills" multiple size="4"><option v-for="skill in skills.state.skills" :key="skill.id" :value="skill.id">{{ skill.name }}</option></select></label>
      <div class="dialog-actions"><button class="secondary-button" type="button" @click="bots.state.showBotForm = false">取消</button><button class="primary-button" type="submit" :disabled="bots.state.botBusy">{{ bots.state.botBusy ? '保存中…' : '保存机器人' }}</button></div>
    </form>
    <div v-if="bots.state.selectedBot" class="plugin-list">
      <div class="bot-row">
        <span v-if="bots.actions.botAvatar(bots.state.selectedBot)" class="bot-avatar-frame" :style="bots.actions.botAccent(bots.state.selectedBot)">
          <img class="bot-avatar-lg" :src="bots.actions.botAvatar(bots.state.selectedBot)" alt="" />
          <span v-if="bots.actions.botMeta(bots.state.selectedBot)" class="bot-sticker" aria-hidden="true"><component :is="bots.actions.botMeta(bots.state.selectedBot).icon" :size="12" /></span>
        </span>
        <Bot v-else :size="22" />
        <div><strong>{{ bots.state.selectedBot.name }}</strong><small>技能：{{ bots.actions.botSkillNames(bots.state.selectedBot) }}</small><small>{{ bots.state.selectedBot.enabled ? '已开启：所有会话都会复用这个助手' : '已关闭：不作用于任何会话' }}</small></div>
        <span class="plugin-state">{{ bots.state.selectedBot.enabled ? '已开启' : '已关闭' }}</span>
        <button class="text-action" type="button" :disabled="bots.state.botBusy" @click="bots.actions.toggleBot(bots.state.selectedBot)">{{ bots.state.selectedBot.enabled ? '关闭' : '开启' }}</button>
        <button class="text-action" type="button" :disabled="bots.state.botBusy" @click="bots.actions.openBotForm(bots.state.selectedBot)">编辑</button>
        <button class="text-action danger" type="button" @click="bots.actions.removeBot(bots.state.selectedBot)">删除</button>
      </div>
    </div>
    <div v-else class="page-empty-state"><div class="page-empty-icon"><Bot :size="44" /></div><h2>bot</h2><p>从左侧选择一个机器人，或新建一个</p><button class="primary-button" type="button" @click="bots.actions.openBotForm()"><Plus :size="15" />新建机器人</button></div>
  </section>
</template>
