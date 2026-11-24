<script setup>
import { inject } from 'vue'
import { AlertCircle, ChevronRight, File, FolderOpen, LoaderCircle, ShieldCheck, Upload, X } from 'lucide-vue-next'
import { formatBytes } from '../app/format'
import { WORKSPACES_KEY } from '../app/keys'

const workspaces = inject(WORKSPACES_KEY)
</script>

<template>
  <div class="modal-backdrop folder-import-backdrop workspace-dialog-theme" @click.self="workspaces.actions.cancelFolderImport">
    <section class="dialog folder-import-dialog" role="dialog" aria-modal="true" aria-labelledby="folder-import-title" aria-describedby="folder-import-copy">
      <div class="folder-import-head">
        <div class="folder-import-icon"><FolderOpen :size="18" /></div>
        <div class="folder-import-headings">
          <h2 id="folder-import-title">添加工作区</h2>
          <p id="folder-import-copy">只读取你刚刚选中的这个文件夹，确认后开始上传。</p>
        </div>
        <button class="icon-button" type="button" aria-label="关闭上传确认框" :disabled="workspaces.state.projectUploadBusy" @click="workspaces.actions.cancelFolderImport"><X :size="18" /></button>
      </div>

      <div class="folder-import-card">
        <div class="folder-import-card-icon"><FolderOpen :size="17" /></div>
        <div class="folder-import-card-copy">
          <strong>{{ workspaces.state.pendingWorkspaceFolderName || '新工作区' }}</strong>
          <span>整个文件夹 · {{ workspaces.state.pendingWorkspaceEntries.length }} 个文件 · {{ formatBytes(workspaces.state.folderImportTotalSize) }}</span>
        </div>
      </div>

      <details class="folder-import-files" aria-label="待上传文件预览">
        <summary class="folder-import-files-heading"><span>文件预览</span><span>{{ workspaces.state.pendingWorkspaceEntries.length }} 个文件</span><ChevronRight :size="14" /></summary>
        <ul>
          <li v-for="entry in workspaces.state.pendingWorkspaceEntries.slice(0, 6)" :key="entry.path">
            <File :size="15" /><span>{{ entry.path }}</span><small>{{ formatBytes(entry.size) }}</small>
          </li>
        </ul>
        <p v-if="workspaces.state.pendingWorkspaceEntries.length > 6" class="folder-import-more">还有 {{ workspaces.state.pendingWorkspaceEntries.length - 6 }} 个文件</p>
      </details>

      <p v-if="workspaces.state.folderImportSkipped" class="folder-import-warning"><AlertCircle :size="14" /> 已跳过 {{ workspaces.state.folderImportSkipped }} 个私密、依赖或超过 50 MB 的文件</p>

      <div v-if="workspaces.state.projectUploadBusy" class="folder-import-progress">
        <div class="folder-import-progress-head"><span>正在上传 {{ workspaces.state.folderImportProgress.done }} / {{ workspaces.state.folderImportProgress.total }}</span><strong>{{ workspaces.state.folderImportPercent }}%</strong></div>
        <div class="folder-import-track"><i :style="{ width: `${workspaces.state.folderImportPercent}%` }"></i></div>
        <span class="folder-import-current">{{ workspaces.state.folderImportProgress.current }}</span>
      </div>

      <p class="folder-import-note"><ShieldCheck :size="14" /> 不会读取其他目录，也不会修改你本地的文件。</p>

      <div class="dialog-actions">
        <button class="secondary-button" type="button" :disabled="workspaces.state.projectUploadBusy" @click="workspaces.actions.cancelFolderImport">取消</button>
        <button class="primary-button folder-import-confirm" type="button" :disabled="workspaces.state.projectUploadBusy" @click="workspaces.actions.startFolderUpload">
          <LoaderCircle v-if="workspaces.state.projectUploadBusy" :size="15" class="spin" />
          <Upload v-else :size="15" />
          {{ workspaces.state.projectUploadBusy ? '正在上传…' : '确认并上传' }}
        </button>
      </div>
    </section>
  </div>
</template>
