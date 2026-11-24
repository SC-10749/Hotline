<script setup>
import { inject } from 'vue'
import { CalendarClock, Plus } from 'lucide-vue-next'
import { AUTOMATION_KEY } from '../app/keys'

const automation = inject(AUTOMATION_KEY)
</script>

<template>
  <section class="plugins-page">
    <div class="tool-toolbar">
      <p class="tool-summary">定时任务<span>{{ automation.state.schedules.length }} 个</span></p>
      <button class="primary-button" type="button" @click="automation.actions.openScheduleForm"><Plus :size="15" />新建任务</button>
    </div>
    <form v-if="automation.state.showScheduleForm" class="schedule-form" @submit.prevent="automation.actions.submitSchedule">
      <label>任务名称<input v-model="automation.state.scheduleDraft.name" placeholder="例如：每日服务巡检" /></label>
      <label>任务内容<textarea v-model="automation.state.scheduleDraft.prompt" rows="3" placeholder="每次触发时交给 Agent 的任务描述"></textarea></label>
      <label>执行模式<select v-model="automation.state.scheduleDraft.agent"><option value="chat">对话助手</option><option value="file">文件问答</option><option value="deep">深度研究</option></select></label>
      <label>间隔（分钟）<input v-model.number="automation.state.scheduleDraft.intervalMinutes" type="number" min="1" max="43200" /></label>
      <div class="dialog-actions"><button class="secondary-button" type="button" @click="automation.state.showScheduleForm = false">取消</button><button class="primary-button" type="submit" :disabled="automation.state.scheduleBusy">{{ automation.state.scheduleBusy ? '创建中…' : '创建任务' }}</button></div>
    </form>
    <div v-if="automation.state.schedules.length" class="plugin-list">
      <div v-for="task in automation.state.schedules" :key="task.task_id" class="plugin-row">
        <div class="plugin-row-main">
          <p class="plugin-row-title"><strong>{{ task.name }}</strong><span class="plugin-state" :class="{ off: !task.enabled }">{{ task.enabled ? '已启用' : '已停用' }}</span></p>
          <p class="plugin-row-desc">{{ task.prompt }}</p>
          <p class="plugin-row-meta">每 {{ task.interval_minutes }} 分钟 · 上次运行 {{ task.last_run_at || '尚未执行' }}{{ task.last_run_id ? ' · ' + task.last_run_id : '' }}</p>
        </div>
        <div class="plugin-row-actions">
          <button class="text-action" type="button" :disabled="automation.state.scheduleBusy" @click="automation.actions.runScheduleNow(task)">立即执行</button>
          <button class="text-action" type="button" :disabled="automation.state.scheduleBusy" @click="automation.actions.toggleSchedule(task)">{{ task.enabled ? '停用' : '启用' }}</button>
          <button class="text-action danger" type="button" @click="automation.actions.removeSchedule(task)">删除</button>
        </div>
      </div>
    </div>
    <div v-else class="page-empty-state">
      <div class="page-empty-icon"><CalendarClock :size="44" /></div>
      <h2>还没有定时任务</h2>
      <p>按固定间隔把一段任务描述交给 Agent 执行。</p>
      <button class="primary-button" type="button" @click="automation.actions.openScheduleForm"><Plus :size="15" />新建任务</button>
    </div>
  </section>
</template>
