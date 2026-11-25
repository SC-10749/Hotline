<script setup>
import { inject } from 'vue'
import { HARNESS_SHELL, HARNESS_WORKSPACES } from '../context'
import { Layers3, Plus, X } from 'lucide-vue-next'

const ctxShell = inject(HARNESS_SHELL)
const ctxWorkspaces = inject(HARNESS_WORKSPACES)

const { refreshActiveSection } = ctxShell
const { checkoutBusy, checkoutError, createWorkspaceSnapshot, editingWorkspace, loadWorkspaceChanges, openWorkspaceDetails, openWorkspaceDialog, runWorkspaceCheckout, showWorkspaceDialog, submitWorkspace, workspaceChanges, workspaceChangesError, workspaceCheckout, workspaceDraft, workspaceError, workspaceRows, workspaceRuns, workspaceRunsError, workspaceSaving, workspaceSelectedSnapshotId, workspaceSnapshotBusy, workspaceSnapshotError, workspaceSnapshots, workspacesConnected, workspacesError } = ctxWorkspaces
</script>

<template>



        <section class="resource-page">
          <p v-if="workspacesError" role="alert">{{ workspacesError }}</p><section class="harness-panel resource-table-panel"><div class="harness-panel-heading"><div><h3>工作空间目录</h3><p>{{ workspaceRows.length }} 个工作空间 · {{ workspacesConnected ? '已连接工作空间目录' : '未连接工作空间目录' }}</p></div><div class="harness-panel-actions"><button class="button button-subtle" @click="refreshActiveSection">刷新目录</button><button class="button button-primary" @click="openWorkspaceDialog"><Plus :size="14" />新建工作空间</button></div></div><div v-if="workspaceRows.length" class="ui-table ui-cols-workspace"><div class="ui-table-head"><span>名称</span><span>仓库</span><span>分支</span><span>状态</span><span>操作</span></div><div v-for="row in workspaceRows" :key="row.workspace_id" class="ui-row"><span><strong>{{ row.name }}</strong><small>{{ row.workspace_id }}</small></span><span>{{ row.repository || '未绑定仓库' }}</span><span>{{ row.branch }}</span><span>{{ row.status }}</span><button class="text-action" @click="openWorkspaceDetails(row)">查看</button></div></div><div v-else class="ui-empty"><span>{{ workspacesConnected ? '还没有工作空间记录' : '未连接工作空间目录 API' }}</span></div></section>
          <footer class="page-footer"><span><i class="footer-health" :class="workspacesConnected ? 'live' : ''"></i>{{ workspacesConnected ? '已连接工作空间目录' : '未连接工作空间目录 API' }}</span></footer>
        </section>
      <div v-if="showWorkspaceDialog" class="modal-backdrop" @click.self="!workspaceSaving && (showWorkspaceDialog = false)">
        <form class="dialog run-create-dialog" role="dialog" aria-modal="true" aria-labelledby="workspace-create-title" @submit.prevent="submitWorkspace">
          <div class="dialog-heading"><div class="dialog-symbol"><Layers3 :size="19" /></div><button class="icon-button" type="button" aria-label="关闭工作空间配置" :disabled="workspaceSaving" @click="showWorkspaceDialog = false"><X :size="18" /></button></div>
          <h2 id="workspace-create-title">{{ editingWorkspace ? '工作空间详情与编辑' : '新建工作空间' }}</h2>
          <p v-if="editingWorkspace">{{ editingWorkspace.workspace_id }} · 状态 {{ editingWorkspace.status }} · 修订 {{ editingWorkspace.revision }} · 更新时间 {{ editingWorkspace.updated_at }}</p>
          <label class="run-create-field"><span>名称</span><input v-model="workspaceDraft.name" required maxlength="120" :disabled="workspaceSaving" /></label>
          <label class="run-create-field"><span>仓库标识</span><input v-model="workspaceDraft.repository" maxlength="500" :disabled="workspaceSaving" /></label>
          <label class="run-create-field"><span>分支</span><input v-model="workspaceDraft.branch" required maxlength="200" :disabled="workspaceSaving" /></label>
          <template v-if="editingWorkspace">
            <div class="harness-detail-block"><strong>仓库检出</strong><div class="harness-detail-actions"><button class="button button-subtle" type="button" :disabled="checkoutBusy" @click="runWorkspaceCheckout">{{ checkoutBusy ? '检出中…' : '检出仓库' }}</button></div><p v-if="checkoutError" role="alert">{{ checkoutError }}</p><div v-if="workspaceCheckout" class="harness-detail-rows"><div class="harness-detail-row"><span>分支 / 提交</span><span>{{ workspaceCheckout.branch || '—' }} · {{ workspaceCheckout.commit ? workspaceCheckout.commit.slice(0, 8) : '—' }}</span></div><div class="harness-detail-row"><span>检出目录</span><code>{{ workspaceCheckout.checkoutDir || '—' }}</code></div><div class="harness-detail-row"><span>检出时间</span><span>{{ workspaceCheckout.checkedAt || '—' }}</span></div></div></div>
            <div class="harness-detail-block"><strong>仓库快照</strong><div class="harness-detail-actions"><button class="button button-subtle" type="button" :disabled="workspaceSnapshotBusy" @click="createWorkspaceSnapshot">{{ workspaceSnapshotBusy ? '创建中…' : '创建快照' }}</button></div><p v-if="workspaceSnapshotError" role="alert">{{ workspaceSnapshotError }}</p><div v-if="workspaceSnapshots.length" class="harness-detail-rows"><div v-for="item in workspaceSnapshots" :key="item.snapshot_id" class="harness-detail-row"><span><strong>{{ item.branch || '未记录分支' }}</strong> · {{ item.file_count }} 个文件 · {{ item.size_bytes }} 字节</span><code>{{ item.snapshot_id }} · {{ item.created_at }}</code></div></div><div v-else class="ui-empty"><span>暂无快照</span></div></div>
            <div class="harness-detail-block"><strong>文件变更</strong><div class="harness-detail-actions"><select v-model="workspaceSelectedSnapshotId" @change="loadWorkspaceChanges(editingWorkspace.workspace_id, workspaceSelectedSnapshotId)"><option value="">选择快照</option><option v-for="item in workspaceSnapshots" :key="item.snapshot_id" :value="item.snapshot_id">{{ item.branch || '未记录分支' }} · {{ item.created_at }}</option></select></div><p v-if="workspaceChangesError" role="alert">{{ workspaceChangesError }}</p><div v-if="workspaceChanges.length" class="harness-detail-rows"><div v-for="item in workspaceChanges" :key="item.change_id" class="harness-detail-row"><code>{{ item.path }}</code><span>{{ item.change_type }}</span></div></div><div v-else class="ui-empty"><span>该快照没有文件变更记录</span></div></div>
            <div class="harness-detail-block"><strong>关联运行</strong><div v-if="workspaceRuns.length" class="harness-detail-rows"><div v-for="item in workspaceRuns" :key="item.run_id" class="harness-detail-row"><span><strong>{{ item.run_id }}</strong> · {{ item.status }}</span><span>{{ item.query || '无任务' }} · {{ item.created_at || '—' }}</span></div></div><div v-else class="ui-empty"><span>暂无关联运行</span></div><p v-if="workspaceRunsError" role="alert">{{ workspaceRunsError }}</p></div>
          </template>
          <p v-if="workspaceError" role="alert">{{ workspaceError }}</p>
          <div class="dialog-actions"><button class="secondary-button" type="button" :disabled="workspaceSaving" @click="showWorkspaceDialog = false">取消</button><button class="primary-button" type="submit" :disabled="workspaceSaving">{{ workspaceSaving ? '保存中…' : editingWorkspace ? '保存登记信息' : '创建工作空间' }}</button></div>
        </form>
      </div>

</template>
