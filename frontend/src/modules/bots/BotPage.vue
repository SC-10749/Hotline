<script setup>
import { computed, inject } from 'vue'
import { Bot, Plus, Workflow } from 'lucide-vue-next'
import { BOTS_KEY, SKILLS_KEY } from '../app/keys'

const bots = inject(BOTS_KEY)
const skills = inject(SKILLS_KEY)

// 全局只有一个机器人生效，把它单独抬到顶部；列表页因此不是一片空白。
const enabledBot = computed(() => bots.state.bots.find(bot => bot.enabled) || null)
const otherBots = computed(() => bots.state.bots.filter(bot => !bot.enabled))
</script>

<template>
  <section class="plugins-page bot-page">
    <form v-if="bots.state.showBotForm" class="schedule-form bot-form" @submit.prevent="bots.actions.submitBot">
      <label>机器人名称<input v-model="bots.state.botDraft.name" placeholder="例如：值班客服" /></label>
      <label>角色指令<textarea v-model="bots.state.botDraft.instruction" rows="3" placeholder="你是一位只回答售后问题的客服，结论先行、语气克制"></textarea></label>
      <label>绑定技能<select v-model="bots.state.botDraft.skills" multiple size="4"><option v-for="skill in skills.state.skills" :key="skill.id" :value="skill.id">{{ skill.name }}</option></select></label>
      <div class="dialog-actions"><button class="secondary-button" type="button" @click="bots.state.showBotForm = false">取消</button><button class="primary-button" type="submit" :disabled="bots.state.botBusy">{{ bots.state.botBusy ? '保存中…' : '保存机器人' }}</button></div>
    </form>

    <div v-else-if="bots.state.selectedBot" class="bot-detail">
      <div class="bot-detail-head">
        <span v-if="bots.actions.botAvatar(bots.state.selectedBot)" class="bot-avatar-frame" :style="bots.actions.botAccent(bots.state.selectedBot)">
          <img class="bot-avatar-lg" :src="bots.actions.botAvatar(bots.state.selectedBot)" alt="" />
          <span v-if="bots.actions.botMeta(bots.state.selectedBot)" class="bot-sticker" aria-hidden="true"><component :is="bots.actions.botMeta(bots.state.selectedBot).icon" :size="12" /></span>
        </span>
        <span v-else class="bot-avatar-fallback"><Bot :size="24" /></span>
        <div class="bot-detail-title">
          <h2>{{ bots.state.selectedBot.name }}</h2>
          <p>{{ bots.state.selectedBot.enabled ? '已开启：所有会话都复用这个助手' : '已关闭：不作用于任何会话' }}</p>
        </div>
        <label class="switch switch-pill" :title="bots.state.selectedBot.enabled ? '关闭这个机器人' : '开启这个机器人'"><input type="checkbox" :checked="bots.state.selectedBot.enabled" :disabled="bots.state.botBusy" @change="bots.actions.toggleBot(bots.state.selectedBot)" /><span class="switch-track" aria-hidden="true"></span></label>
      </div>
      <div class="bot-detail-block">
        <p class="bot-detail-label">绑定技能</p>
        <div class="bot-chips">
          <span v-for="name in bots.actions.botSkillList(bots.state.selectedBot)" :key="name" class="bot-chip">{{ name }}</span>
          <span v-if="!bots.actions.botSkillList(bots.state.selectedBot).length" class="bot-detail-note">未绑定技能，这个助手只按角色指令回答</span>
        </div>
      </div>
      <div class="bot-detail-actions">
        <button class="secondary-button" type="button" :disabled="bots.state.botBusy" @click="bots.actions.openBotForm(bots.state.selectedBot)">编辑</button>
        <button class="text-action danger" type="button" @click="bots.actions.removeBot(bots.state.selectedBot)">删除机器人</button>
      </div>
    </div>

    <div v-else-if="!bots.state.bots.length" class="page-empty-state">
      <div class="page-empty-icon"><Bot :size="40" /></div>
      <h2>还没有机器人</h2>
      <p>机器人把一个角色的指令和技能绑在一起，开启后所有会话都复用它的人设。</p>
      <button class="primary-button" type="button" @click="bots.actions.openBotForm()"><Plus :size="15" />新建机器人</button>
    </div>

    <template v-else>
      <section v-if="enabledBot" class="bot-spotlight">
        <div class="bot-spotlight-head">
          <span v-if="bots.actions.botAvatar(enabledBot)" class="bot-avatar-frame" :style="bots.actions.botAccent(enabledBot)">
            <img class="bot-avatar-lg" :src="bots.actions.botAvatar(enabledBot)" alt="" />
            <span v-if="bots.actions.botMeta(enabledBot)" class="bot-sticker" aria-hidden="true"><component :is="bots.actions.botMeta(enabledBot).icon" :size="12" /></span>
          </span>
          <span v-else class="bot-avatar-fallback"><Bot :size="24" /></span>
          <div class="bot-detail-title">
            <p class="bot-detail-label">当前启用</p>
            <h2>{{ enabledBot.name }}</h2>
            <p>{{ bots.actions.botSkillNames(enabledBot) }}</p>
          </div>
          <button class="secondary-button" type="button" @click="bots.actions.selectBot(enabledBot)">查看</button>
        </div>
      </section>

      <section class="bot-overview">
        <div class="bot-overview-head">
          <h2>{{ enabledBot ? '其他机器人' : '全部机器人' }}<span>{{ enabledBot ? otherBots.length : bots.state.bots.length }}</span></h2>
          <button class="text-action" type="button" @click="bots.actions.openBotForm()"><Plus :size="14" />新建</button>
        </div>
        <div class="bot-grid">
          <button v-for="bot in (enabledBot ? otherBots : bots.state.bots)" :key="bot.bot_id" class="bot-card" :class="{ active: bots.state.selectedBotId === bot.bot_id }" type="button" @click="bots.actions.selectBot(bot)">
            <span class="bot-card-top">
              <span v-if="bots.actions.botAvatar(bot)" class="bot-avatar-frame" :style="bots.actions.botAccent(bot)"><img class="bot-avatar" :src="bots.actions.botAvatar(bot)" alt="" /></span>
              <Bot v-else :size="18" />
              <span class="bot-card-name">{{ bot.name }}</span>
              <span class="plugin-state" :class="{ off: !bot.enabled }">{{ bot.enabled ? '已开启' : '已关闭' }}</span>
            </span>
            <span class="bot-card-skills">{{ bots.actions.botSkillNames(bot) }}</span>
          </button>
        </div>
        <p v-if="enabledBot && !otherBots.length" class="bot-overview-empty">只有这一个机器人。再建一个角色助手，按场景在左侧切换。</p>
      </section>
    </template>
  </section>
</template>
