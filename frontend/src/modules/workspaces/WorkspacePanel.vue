<script setup>
import { inject } from 'vue'
import { ChevronRight, CircleDot, File, FileCode2, FolderOpen, GitCompare, X } from 'lucide-vue-next'
import { APP_KEY, CHAT_KEY, WORKSPACES_KEY } from '../app/keys'

const ctx = inject(APP_KEY)
const chat = inject(CHAT_KEY)
const workspaces = inject(WORKSPACES_KEY)
</script>

<template>
  <aside v-if="ctx.showWorkspacePanel" class="changes-panel" aria-label="文件与变更">
    <header class="changes-panel-header">
      <div><strong>{{ ctx.selectedProjectName }}</strong><span>{{ workspaces.state.projectUploadBusy ? '正在上传文件夹…' : '当前项目文件' }}</span></div>
      <button class="icon-button" type="button" aria-label="关闭文件面板" @click="ctx.showWorkspacePanel = false"><X :size="17" /></button>
    </header>
    <div class="changes-tabs" role="tablist">
      <button type="button" :class="{ active: ctx.workspacePanelTab === 'files' }" @click="ctx.workspacePanelTab = 'files'"><FileCode2 :size="15" />文件</button>
      <button type="button" :class="{ active: ctx.workspacePanelTab === 'changes' }" @click="ctx.workspacePanelTab = 'changes'"><GitCompare :size="15" />变更 <span>3</span></button>
    </div>
    <div v-if="ctx.workspacePanelTab === 'files'" class="workspace-tree">
      <div class="tree-root"><FolderOpen :size="15" /> {{ ctx.selectedProjectName }}</div>
      <template v-if="workspaces.state.projectFiles.length">
        <div v-for="file in workspaces.state.projectFiles" :key="file.name" class="tree-item"><File :size="14" /> {{ file.name }}</div>
      </template>
      <template v-else>
        <div class="tree-item folder"><FolderOpen :size="14" /> frontend</div>
        <div class="tree-item indent"><FileCode2 :size="14" /> src/App.vue</div>
        <div class="tree-item indent"><FileCode2 :size="14" /> src/style.css</div>
        <div class="tree-item folder"><FolderOpen :size="14" /> python_backend</div>
        <div class="tree-item"><File :size="14" /> README.md</div>
      </template>
    </div>
    <div v-else class="changes-list">
      <div class="changes-summary"><CircleDot :size="15" /> 3 个文件待审阅</div>
      <button v-for="file in workspaces.state.changedFiles" :key="file.path" class="change-file" type="button" @click="chat.actions.requestTextEdit(file)">
        <span class="change-status" :class="file.tone">{{ file.status }}</span>
        <span class="change-file-copy"><strong>{{ file.path }}</strong><small>{{ file.detail }}</small></span>
        <ChevronRight :size="15" />
      </button>
    </div>
    <div class="changes-panel-footer"><button type="button" @click="ctx.workspacePanelTab = 'changes'"><GitCompare :size="15" />查看全部变更</button></div>
  </aside>
</template>
