<script setup>
import { computed, inject, ref } from 'vue'
import { HARNESS_SHELL, HARNESS_RUNS, HARNESS_RESOURCES } from '../context'
import ParallelPanel from '../../execution/ParallelPanel.vue'
import { ArrowRight } from 'lucide-vue-next'

const ctxShell = inject(HARNESS_SHELL)
const ctxRuns = inject(HARNESS_RUNS)
const ctxResources = inject(HARNESS_RESOURCES)

const { activeSection, props, selectSection } = ctxShell
const { formatTokenCount, overviewStats, runs, showParallelPanel } = ctxRuns
const { formatWorkerSeen, machineRows, machinesConnected, onlineWorkerCount } = ctxResources

const showOfflineMachines = ref(false)
const offlineMachineRows = computed(() => machineRows.value.filter(row => row.state === 'offline'))
const displayMachineRows = computed(() => showOfflineMachines.value ? machineRows.value : machineRows.value.filter(row => row.state !== 'offline'))
</script>

<template>



          <section v-if="activeSection === 'overview'" class="overview-strip" aria-label="今日运行指标"><div class="overview-stat"><span>活动运行</span><strong>{{ overviewStats ? overviewStats.activeRuns : '—' }}</strong><small>排队与执行中</small></div><div class="overview-stat"><span>今日完成</span><strong>{{ overviewStats ? overviewStats.completedToday : '—' }}</strong><small>失败 {{ overviewStats?.failedToday ?? '—' }} · 取消 {{ overviewStats?.cancelledToday ?? '—' }}</small></div><div class="overview-stat"><span>待人工审批</span><strong class="stat-warn">{{ overviewStats ? overviewStats.pendingApprovals : '—' }}</strong><small>来自真实审批队列</small></div><div class="overview-stat"><span>今日模型用量</span><strong>{{ overviewStats ? formatTokenCount(overviewStats.tokensToday) : '—' }}</strong><small>Tokens · 工具调用 {{ overviewStats?.toolCallsToday ?? '—' }}</small></div><div class="overview-stat stat-runtime"><span>运行时节点</span><strong>{{ onlineWorkerCount }} <em>/ {{ machineRows.length }}</em></strong><small>在线节点</small></div></section>
          <ParallelPanel v-if="showParallelPanel" :api-base="props.apiBase" />
          <section v-if="activeSection === 'overview'" class="machine-section"><div class="section-title-row"><div><h2>执行节点</h2><span>在线 {{ onlineWorkerCount }} / 共 {{ machineRows.length }} 个节点</span></div><button class="text-action" @click="selectSection('machines')">管理机器 <ArrowRight :size="13" /></button></div><div v-if="displayMachineRows.length" class="ui-table ui-cols-machine-summary"><div class="ui-table-head"><span>节点</span><span class="ui-num">进程</span><span>状态</span><span class="ui-num">容量</span><span>最近心跳</span><span>当前运行</span></div><div v-for="row in displayMachineRows" :key="row.worker_id" class="ui-row"><strong>{{ row.worker_id }}</strong><span class="ui-num">{{ row.process_id }}</span><span class="ui-status" :class="row.state === 'draining' ? 'warn' : row.state === 'offline' ? 'idle' : 'ok'">{{ row.state === 'draining' ? '排空中' : row.state === 'offline' ? '离线' : '在线' }}</span><span class="ui-num">{{ row.capacity ?? 1 }}</span><span>{{ formatWorkerSeen(row.last_seen) }}</span><span>{{ row.current_run_id || '空闲' }}</span></div></div><div v-else class="ui-empty"><span>{{ machinesConnected ? '当前没有在线节点' : '未连接运行时节点 API' }}</span></div><div v-if="offlineMachineRows.length" class="machine-offline-note"><span>{{ offlineMachineRows.length }} 个离线节点已折叠</span><button class="text-action" @click="showOfflineMachines = !showOfflineMachines">{{ showOfflineMachines ? '收起离线节点' : '展开离线节点' }}</button></div></section>
          <footer class="page-footer"><span>{{ activeSection === 'runs' ? '运行记录来自执行服务 · 每 5 秒刷新' : '总览指标来自今日真实运行记录' }}</span></footer>



</template>
