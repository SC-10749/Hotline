<script setup>
import { inject } from 'vue'
import { Plus, Puzzle, Upload } from 'lucide-vue-next'
import { SKILLS_KEY } from '../app/keys'

const skills = inject(SKILLS_KEY)
</script>

<template>
  <section class="plugins-page">
    <div class="tool-toolbar">
      <p class="tool-summary">已安装技能<span>{{ skills.state.skills.length }} 个</span></p>
      <button class="primary-button" type="button" @click="skills.actions.openSkills"><Upload :size="15" />上传技能包</button>
    </div>
    <div v-if="skills.state.skills.length" class="plugin-list">
      <div v-for="skill in skills.state.skills" :key="skill.id" class="plugin-row">
        <div class="plugin-row-main">
          <p class="plugin-row-title"><strong>{{ skill.name }}</strong><span class="plugin-state" :class="{ off: !skill.enabled }">{{ skill.enabled ? '已启用' : '已停用' }}</span></p>
          <p class="plugin-row-desc">{{ skill.description || '暂无说明' }}</p>
          <p class="plugin-row-meta">来源 {{ skill.sourceFile || '本地安装包' }} · 入口 {{ skill.entry || '—' }}</p>
        </div>
        <div class="plugin-row-actions">
          <button class="text-action" type="button" @click="skills.actions.togglePlugin(skill)">{{ skill.enabled ? '停用' : '启用' }}</button>
          <button class="text-action danger" type="button" @click="skills.actions.removePlugin(skill)">删除</button>
        </div>
      </div>
    </div>
    <div v-else class="page-empty-state">
      <div class="page-empty-icon"><Puzzle :size="44" /></div>
      <h2>还没有安装技能</h2>
      <p>上传技能包后，机器人就能绑定它并按它的方式干活。</p>
      <button class="primary-button" type="button" @click="skills.actions.openSkills"><Plus :size="15" />上传技能包</button>
    </div>
  </section>
</template>
