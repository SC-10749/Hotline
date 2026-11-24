<script setup>
import { inject } from 'vue'
import { HARNESS_SHELL, HARNESS_RUNS, HARNESS_RESOURCES } from '../context'
import ParallelPanel from '../../execution/ParallelPanel.vue'
import { ArrowRight, Check } from 'lucide-vue-next'

const ctxShell = inject(HARNESS_SHELL)
const ctxRuns = inject(HARNESS_RUNS)
const ctxResources = inject(HARNESS_RESOURCES)

const { activeSection, props, selectSection } = ctxShell
const { formatTokenCount, overviewStats, runs, showParallelPanel } = ctxRuns
const { formatWorkerSeen, machineRows, machinesConnected, onlineWorkerCount } = ctxResources
</script>

<template>



          <p v-if="activeSection === 'overview'">下列汇总指标与节点表为演示数据，实际运行请进入执行任务。</p>
          <section v-if="activeSection === 'overview'" class="overview-strip" aria-label="今日运行指标"><div class="overview-stat"><span>活动运行</span><strong>{{ overviewStats ? overviewStats.activeRuns : '—' }}</strong><small><i class="status-inline"></i>排队与执行中</small></div><div class="overview-stat"><span>今日完成</span><strong>{{ overviewStats ? overviewStats.completedToday : '—' }}</strong><small class="positive"><Check :size="12" />失败 {{ overviewStats?.failedToday ?? '—' }} · 取消 {{ overviewStats?.cancelledToday ?? '—' }}</small></div><div class="overview-stat"><span>待人工审批</span><strong class="stat-warn">{{ overviewStats ? overviewStats.pendingApprovals : '—' }}</strong><small>来自真实审批队列</small></div><div class="overview-stat"><span>今日模型用量</span><strong>{{ overviewStats ? formatTokenCount(overviewStats.tokensToday) : '—' }}</strong><small>Tokens · 工具调用 {{ overviewStats?.toolCallsToday ?? '—' }}</small></div><div class="overview-stat stat-runtime"><span>运行时节点</span><strong>{{ onlineWorkerCount }} <em>/ {{ machineRows.length }}</em></strong><small>在线节点</small></div></section>
          <ParallelPanel v-if="showParallelPanel" :api-base="props.apiBase" />
          <section v-if="activeSection === 'overview'" class="machine-section"><div class="section-title-row"><div><h2>执行节点</h2><span>本地与远端 Agent Runtime 的容量和健康状态</span></div><button class="text-action" @click="selectSection('machines')">管理机器 <ArrowRight :size="13" /></button></div><div v-if="machineRows.length" class="machine-table"><div class="machine-header"><span>节点</span><span>进程</span><span>状态</span><span>容量</span><span>最近心跳</span><span>当前运行</span></div><div v-for="row in machineRows" :key="row.worker_id" class="machine-row"><strong><i class="machine-led" :class="{ offline: row.state === 'offline' }"></i>{{ row.worker_id }}</strong><span>{{ row.process_id }}</span><span><i class="health-mini" :class="{ offline: row.state === 'offline' }"></i>{{ row.state === 'draining' ? '排空中' : row.state === 'offline' ? '离线' : '在线' }}</span><span>{{ row.capacity ?? 1 }}</span><span>{{ formatWorkerSeen(row.last_seen) }}</span><span>{{ row.current_run_id || '空闲' }}</span></div></div><div v-else class="release-empty"><span>{{ machinesConnected ? '当前没有注册节点' : '未连接运行时节点 API' }}</span></div></section>
          <footer class="page-footer"><span>{{ activeSection === 'runs' ? '运行记录来自执行服务 · 每 5 秒刷新' : '总览指标来自今日真实运行记录' }}</span></footer>



</template>
