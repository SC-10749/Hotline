<script setup>
import { inject } from 'vue'
import { HARNESS_SHELL, HARNESS_RUNS, HARNESS_AGENTS, HARNESS_WORKSPACES } from '../context'
import ExecutionRunDetails from '../../execution/ExecutionRunDetails.vue'
import ParallelPanel from '../../execution/ParallelPanel.vue'
import { Play, Search, X } from 'lucide-vue-next'

const ctxShell = inject(HARNESS_SHELL)
const ctxRuns = inject(HARNESS_RUNS)
const ctxAgents = inject(HARNESS_AGENTS)
const ctxWorkspaces = inject(HARNESS_WORKSPACES)

const { activeSection, props } = ctxShell
const { changeRunPage, duplicateSelectedRun, eventsError, eventsLoading, eventsStreamState, executionLoaded, executionLoading, executionTotal, filter, refreshSelectedRunEvents, retrySelectedRun, runActionBusy, runDraft, runEvents, runOffset, runOutput, runPageSize, runSubmitBusy, runs, search, selectRun, selectedRun, showParallelPanel, showRunDialog, statusFilters, statusLabels, stopSelectedRun, submitRun } = ctxRuns
const { harnessAgents } = ctxAgents
const { harnessWorkspaces } = ctxWorkspaces
</script>

<template>



          <ParallelPanel v-if="showParallelPanel" :api-base="props.apiBase" />
          <section v-if="activeSection === 'runs'" class="run-workbench execution-live">
            <div class="run-list-panel">
              <div class="panel-heading"><div><h2>执行任务</h2><span>共 {{ executionTotal }} 条匹配记录 · 每页 {{ runPageSize }} 条</span></div><button class="button button-subtle" @click="showParallelPanel = !showParallelPanel">{{ showParallelPanel ? '收起并行派发' : '并行派发' }}</button></div>
              <div class="run-list-tools"><select v-model="filter" aria-label="任务状态"><option v-for="option in ['全部任务', ...Object.keys(statusFilters)]" :key="option">{{ option }}</option></select><label class="run-search"><Search :size="14" /><input ref="searchField" v-model="search" placeholder="搜索任务" /></label></div>
              <div class="run-list" :aria-busy="executionLoading"><button v-for="run in runs" :key="run.id" class="run-row" :class="{ selected: selectedRun?.id === run.id }" @click="selectRun(run.id)"><strong>{{ run.title }}</strong><div class="run-row-meta">{{ run.id }}</div><div class="run-row-bottom"><span>{{ run.agent }}</span><span>{{ statusLabels[run.status] || run.status }}</span></div></button>
                <div v-if="!runs.length" class="empty-runs"><span>{{ executionLoading ? '正在读取任务…' : executionLoaded ? '没有匹配的运行记录' : '等待运行服务连接' }}</span><button v-if="search || filter !== '全部任务'" @click="search = ''; filter = '全部任务'">清除筛选</button></div>
              </div>
              <nav class="execution-pagination" aria-label="执行任务分页"><button class="button button-subtle" :disabled="executionLoading || runOffset === 0" @click="changeRunPage(runOffset - runPageSize)">上一页</button><span aria-live="polite">{{ Math.floor(runOffset / runPageSize) + 1 }} / {{ Math.max(1, Math.ceil(executionTotal / runPageSize)) }}</span><button class="button button-subtle" :disabled="executionLoading || runOffset + runPageSize >= executionTotal" @click="changeRunPage(runOffset + runPageSize)">下一页</button></nav>
            </div>
            <ExecutionRunDetails v-if="selectedRun" :key="selectedRun.id" :run="selectedRun" :api-base="props.apiBase" :items="runEvents" :loading="eventsLoading" :error="eventsError" :output="runOutput" :stream-state="eventsStreamState" :action-busy="runActionBusy" @refresh="refreshSelectedRunEvents" @cancel="stopSelectedRun" @retry="retrySelectedRun" @duplicate="duplicateSelectedRun" />
            <div v-else class="empty-runs">选择运行后查看输入、输出和 Trace</div>
          </section>
          <footer class="page-footer"><span>{{ activeSection === 'runs' ? '运行记录来自执行服务 · 每 5 秒刷新' : '总览指标来自今日真实运行记录' }}</span></footer>
      <div v-if="showRunDialog" class="modal-backdrop" @click.self="showRunDialog = false"><section class="dialog run-create-dialog" role="dialog" aria-modal="true" aria-labelledby="run-create-title"><div class="dialog-heading"><div class="dialog-symbol"><Play :size="19" /></div><button class="icon-button" type="button" aria-label="关闭新建运行" @click="showRunDialog = false"><X :size="18" /></button></div><h2 id="run-create-title">新建执行任务</h2><p>提交一个独立的 Agent 运行。运行创建后只在“执行任务”页面管理。</p><label class="run-create-field"><span>执行模式</span><select v-model="runDraft.agent"><option value="chat">对话助手</option><option value="file">文件问答</option><option value="ppt">PPT 生成</option><option value="deep">深度研究</option><option value="skills">技能助手</option></select></label><label class="run-create-field"><span>任务内容</span><textarea v-model="runDraft.query" rows="5" placeholder="描述要执行的任务" autofocus></textarea></label><label class="run-create-field"><span>会话编号</span><input v-model="runDraft.conversationId" placeholder="可选，默认自动生成" /></label><label v-if="runDraft.agent === 'file' || runDraft.agent === 'skills'" class="run-create-field"><span>文件编号</span><input v-model="runDraft.fileId" placeholder="填写已上传文件或文档的 fileId" /></label><label class="run-create-field"><span>关联 Agent</span><select v-model="runDraft.agentId"><option value="">不关联</option><option v-for="item in harnessAgents" :key="item.agent_id" :value="item.agent_id">{{ item.name }}{{ item.enabled ? '' : '（已停用）' }}</option></select></label><label class="run-create-field"><span>关联工作空间</span><select v-model="runDraft.workspaceId"><option value="">不关联</option><option v-for="item in harnessWorkspaces" :key="item.workspace_id" :value="item.workspace_id">{{ item.name }} · {{ item.branch }}</option></select></label><div class="dialog-actions"><button class="secondary-button" type="button" @click="showRunDialog = false">取消</button><button class="primary-button" type="button" :disabled="runSubmitBusy" @click="submitRun">{{ runSubmitBusy ? '提交中…' : '提交运行' }}</button></div></section></div>

</template>
