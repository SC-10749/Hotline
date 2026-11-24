<script setup>
import { inject, ref } from 'vue'
import { AlertCircle, Check, LoaderCircle, Plus, Puzzle, ToggleLeft, ToggleRight, Trash2, X } from 'lucide-vue-next'
import { SKILLS_KEY } from '../app/keys'

const skills = inject(SKILLS_KEY)
const skillInput = ref(null)
</script>

<template>
  <div class="modal-backdrop" @click.self="skills.actions.closeSkills">
    <section class="dialog skills-dialog" role="dialog" aria-modal="true" aria-labelledby="skills-title">
      <div class="dialog-heading"><div class="dialog-symbol"><Puzzle :size="19" /></div><button class="icon-button" type="button" aria-label="关闭技能管理" @click="skills.actions.closeSkills"><X :size="18" /></button></div>
      <h2 id="skills-title">技能管理</h2>
      <p>支持包含 SKILL.md 的 .zip 技能包。</p>
      <div class="skill-toolbar">
        <button class="primary-button" type="button" :disabled="skills.state.skillBusy" @click="skillInput.click()"><LoaderCircle v-if="skills.state.skillBusy" :size="15" class="spin" /><Plus v-else :size="15" />上传技能包</button>
        <input ref="skillInput" class="skill-file-input" type="file" accept=".zip" @change="skills.actions.chooseSkillZip" />
        <span class="skill-tally">{{ skills.state.enabledSkills.length }} / {{ skills.state.skills.length }} 已启用</span>
      </div>
      <div v-if="skills.state.skillMessage" class="skill-feedback" :class="skills.state.skillMessage.type"><AlertCircle v-if="skills.state.skillMessage.type === 'error'" :size="15" /><Check v-else :size="15" /><span>{{ skills.state.skillMessage.text }}</span></div>
      <div v-if="skills.state.skillEntries.length" class="skill-picker">
        <span class="field-label">未自动定位到 SKILL.md，请手动选择技能文件</span>
        <div class="skill-picker-list">
          <label v-for="entry in skills.state.skillEntries" :key="entry" class="skill-picker-item"><input v-model="skills.state.skillEntryChoice" type="radio" name="skill-entry" :value="entry" /><span>{{ entry }}</span></label>
        </div>
        <div class="skill-picker-actions"><button class="secondary-button" type="button" @click="skills.actions.clearSkillEntry">取消</button><button class="primary-button" type="button" :disabled="!skills.state.skillEntryChoice || skills.state.skillBusy" @click="skills.actions.confirmSkillEntry">使用该文件</button></div>
      </div>
      <div class="skill-list">
        <div v-if="skills.state.skills.length === 0" class="skill-empty">还没有安装技能。</div>
        <article v-for="skill in skills.state.skills" :key="skill.id" class="skill-row" :class="{ off: !skill.enabled }">
          <div class="skill-row-main">
            <div class="skill-row-name"><span>{{ skill.name }}</span><em :class="{ on: skill.enabled }">{{ skill.enabled ? '已启用' : '已停用' }}</em></div>
            <p v-if="skill.description" class="skill-row-desc">{{ skill.description }}</p>
            <div class="skill-row-meta"><code>{{ skill.entry }}</code><span>{{ skill.sourceFile }}</span></div>
          </div>
          <div class="skill-row-actions">
            <button class="icon-button" type="button" :title="skill.enabled ? '停用' : '启用'" :aria-label="skill.enabled ? '停用技能' : '启用技能'" @click="skills.actions.toggleSkill(skill)"><ToggleRight v-if="skill.enabled" :size="20" /><ToggleLeft v-else :size="20" /></button>
            <template v-if="skills.state.deletingSkill === skill.id"><button class="secondary-button" type="button" @click="skills.state.deletingSkill = null">取消</button><button class="danger-button" type="button" @click="skills.actions.confirmRemoveSkill(skill)"><Trash2 :size="14" />确认删除</button></template>
            <button v-else class="icon-button" type="button" title="删除技能" aria-label="删除技能" @click="skills.state.deletingSkill = skill.id"><Trash2 :size="17" /></button>
          </div>
        </article>
      </div>
      <div class="dialog-actions"><button class="secondary-button" type="button" @click="skills.actions.closeSkills">关闭</button></div>
    </section>
  </div>
</template>
