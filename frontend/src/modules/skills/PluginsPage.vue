<script setup>
import { inject } from 'vue'
import { Plus, Puzzle, Upload } from 'lucide-vue-next'
import { SKILLS_KEY } from '../app/keys'

const skills = inject(SKILLS_KEY)
</script>

<template>
  <section class="plugins-page">
    <div class="settings-section-copy"><Puzzle :size="22" /><div><h2>已安装技能</h2></div><button class="primary-button" type="button" @click="skills.actions.openSkills"><Upload :size="15" />上传技能包</button></div>
    <div v-if="skills.state.skills.length" class="plugin-list">
      <div v-for="skill in skills.state.skills" :key="skill.id" class="plugin-row">
        <div><strong>{{ skill.name }}</strong><small>{{ skill.description || '暂无说明' }}</small><small>来源 {{ skill.sourceFile || '本地安装包' }} · 入口 {{ skill.entry || '—' }}</small></div>
        <span class="plugin-state">{{ skill.enabled ? '已启用' : '已停用' }}</span>
        <button class="text-action" type="button" @click="skills.actions.togglePlugin(skill)">{{ skill.enabled ? '停用' : '启用' }}</button>
        <button class="text-action danger" type="button" @click="skills.actions.removePlugin(skill)">删除</button>
      </div>
    </div>
    <div v-else class="page-empty-state"><div class="page-empty-icon"><Puzzle :size="44" /></div><h2>管理插件</h2><p>暂无已安装技能</p><button class="primary-button" type="button" @click="skills.actions.openSkills"><Plus :size="15" />上传技能包</button></div>
  </section>
</template>
