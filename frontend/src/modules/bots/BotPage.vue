<script setup>
import { inject } from 'vue'
import { Bot, Plus } from 'lucide-vue-next'
import { BOTS_KEY, SKILLS_KEY } from '../app/keys'

const bots = inject(BOTS_KEY)
const skills = inject(SKILLS_KEY)
</script>

<template>
  <section class="plugins-page">
    <div class="settings-section-copy"><Bot :size="22" /><div><h2>bot</h2></div><button class="primary-button" type="button" @click="bots.actions.openBotForm()"><Plus :size="15" />新建机器人</button></div>
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
