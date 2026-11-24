<script setup>
import { inject } from 'vue'
import { HARNESS_SETTINGS, HARNESS_SHELL } from '../context'
import { Check } from 'lucide-vue-next'

const ctxShell = inject(HARNESS_SHELL)
const ctxSettings = inject(HARNESS_SETTINGS)

const { activeSection } = ctxShell

const { harnessSettings, refreshHarnessSettings, saveSettings, settingsConnected } = ctxSettings
</script>

<template>



        <section v-if="activeSection === 'settings'" class="resource-page">
          <div class="release-toolbar"><div><h2>Harness 设置</h2></div><button class="button button-primary" @click="saveSettings"><Check :size="14" />保存设置</button></div>
          <section class="harness-panel resource-table-panel"><div class="harness-panel-heading"><div><h3>运行策略</h3><p>{{ settingsConnected ? '设置已连接' : '当前使用默认值' }}</p></div><button class="button button-subtle" @click="refreshHarnessSettings">刷新设置</button></div><div class="release-form settings-form"><label>默认隔离方式<select v-model="harnessSettings.isolation"><option value="container">容器</option><option value="process">进程</option><option value="host">主机</option></select></label><label>审计保留天数<input v-model.number="harnessSettings.auditRetentionDays" type="number" min="1" max="3650" /></label><label>审批策略<select v-model="harnessSettings.approvalPolicy"><option value="risk-based">按风险等级</option><option value="always">所有写入都审批</option><option value="never">不自动审批</option></select></label><label>默认预算（USD）<input v-model.number="harnessSettings.defaultBudgetUsd" type="number" min="0" step="0.01" /></label><label>默认超时（秒）<input v-model.number="harnessSettings.defaultTimeoutSeconds" type="number" min="1" max="86400" /></label><label>默认重试次数<input v-model.number="harnessSettings.defaultRetryCount" type="number" min="0" max="10" /></label></div></section>
          <footer class="page-footer"><span><i class="footer-health demo-health"></i>{{ settingsConnected ? '已连接设置 API' : '默认设置 · 未连接设置 API' }}</span></footer>
        </section>



</template>
