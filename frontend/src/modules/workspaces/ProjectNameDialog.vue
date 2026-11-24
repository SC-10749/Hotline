<script setup>
import { inject } from 'vue'
import { FolderOpen, X } from 'lucide-vue-next'
import { WORKSPACES_KEY } from '../app/keys'

const workspaces = inject(WORKSPACES_KEY)
</script>

<template>
  <div class="modal-backdrop project-name-backdrop workspace-dialog-theme" @click.self="workspaces.state.showProjectNameDialog = false">
    <section class="dialog project-name-dialog" role="dialog" aria-modal="true" aria-labelledby="project-name-title" aria-describedby="project-name-copy">
      <div class="dialog-heading"><div class="dialog-symbol permission-symbol"><FolderOpen :size="19" /></div><button class="icon-button" type="button" aria-label="关闭项目命名框" @click="workspaces.state.showProjectNameDialog = false"><X :size="18" /></button></div>
      <h2 id="project-name-title">给这个项目起个名字</h2>
      <p id="project-name-copy">文件夹已上传，可为项目命名。</p>
      <label class="project-name-field"><span>项目名称</span><input v-model="workspaces.state.projectNameDraft" class="text-field" autofocus maxlength="80" @keydown.enter.prevent="workspaces.actions.saveProjectName" /></label>
      <div class="dialog-actions"><button class="secondary-button" type="button" @click="workspaces.state.showProjectNameDialog = false">稍后再命名</button><button class="primary-button" type="button" @click="workspaces.actions.saveProjectName">保存项目名称</button></div>
    </section>
  </div>
</template>
