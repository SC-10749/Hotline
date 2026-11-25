<script setup>
import { computed, nextTick, onMounted, onUnmounted, provide, ref, watch } from 'vue'
import { usePageState } from './composables/usePageState'
import { sections } from './modules/harness/sections'
import { HARNESS_SHELL, HARNESS_RUNS, HARNESS_EVALUATIONS, HARNESS_RELEASES, HARNESS_SETTINGS, HARNESS_AGENTS, HARNESS_WORKSPACES, HARNESS_TOOLS, HARNESS_MODELS, HARNESS_SKILLS, HARNESS_RESOURCES, HARNESS_TRACES } from './modules/harness/context'
import { useRuns } from './modules/harness/useRuns'
import { useEvaluations } from './modules/harness/useEvaluations'
import { useReleases } from './modules/harness/useReleases'
import { useSettings } from './modules/harness/useSettings'
import { useAgents } from './modules/harness/useAgents'
import { useWorkspaces } from './modules/harness/useWorkspaces'
import { useTools } from './modules/harness/useTools'
import { useModels } from './modules/harness/useModels'
import { useSkillDirectory } from './modules/harness/useSkillDirectory'
import { useResources } from './modules/harness/useResources'
import { useTraces } from './modules/harness/useTraces'
import OverviewPanel from './modules/harness/panels/OverviewPanel.vue'
import RunsPanel from './modules/harness/panels/RunsPanel.vue'
import EvaluationsPanel from './modules/harness/panels/EvaluationsPanel.vue'
import SettingsPanel from './modules/harness/panels/SettingsPanel.vue'
import ArtifactsPanel from './modules/harness/panels/ArtifactsPanel.vue'
import TracesPanel from './modules/harness/panels/TracesPanel.vue'
import ResourcesPanel from './modules/harness/panels/ResourcesPanel.vue'
import ToolsPanel from './modules/harness/panels/ToolsPanel.vue'
import ModelsPanel from './modules/harness/panels/ModelsPanel.vue'
import SkillDirectoryPanel from './modules/harness/panels/SkillDirectoryPanel.vue'
import AgentsPanel from './modules/harness/panels/AgentsPanel.vue'
import WorkspacesPanel from './modules/harness/panels/WorkspacesPanel.vue'
import ReleasesPanel from './modules/harness/panels/ReleasesPanel.vue'
import { Activity, Check, Menu, Plus, ShieldCheck, Workflow, X } from 'lucide-vue-next'

const props = defineProps({ embedded: { type: Boolean, default: false }, apiBase: { type: String, default: '' } })

const activeSection = usePageState('harness-section', 'overview', sections.flatMap(group => group.items.map(item => item.id)))

const activeView = ref('control')

const selectedModuleRecord = ref(null)

const toast = ref('')

const mobileNavOpen = ref(false)

function notify(message) {
  toast.value = message
  window.clearTimeout(notify.timer)
  notify.timer = window.setTimeout(() => { toast.value = '' }, 2600)
}


const runsCtx = useRuns({ props, notify, activeSection, activeView })
const evaluationsCtx = useEvaluations({ props, notify })
const releasesCtx = useReleases({ props, notify })
const settingsCtx = useSettings({ props, notify })
const agentsCtx = useAgents({ props, notify })
const workspacesCtx = useWorkspaces({ props, notify })
const toolsCtx = useTools({ props, notify })
const modelsCtx = useModels({ props, notify })
const skillsCtx = useSkillDirectory({ props, notify })
const resourcesCtx = useResources({ props, notify })
const tracesCtx = useTraces({ props, notify, harnessTraceRuns: resourcesCtx.harnessTraceRuns })
const { executionConnected, executionError, executionLoaded, executionLoading, executionTotal, loadOverviewStats, openCreateRun, refreshExecutionRuns, runs, showRunDialog, startExecutionRefresh } = runsCtx
const { evalRunDetail, evalRuns, evaluationConnected, evaluationError, refreshEvaluationData, selectedEvaluationDataset, showCaseDialog, showDatasetDialog, showImportDialog } = evaluationsCtx
const { refreshReleaseData, releaseConnected, releaseError } = releasesCtx
const { refreshHarnessSettings, settingsConnected, settingsError } = settingsCtx
const { agentsConnected, harnessAgents, refreshAgentData, showAgentDialog } = agentsCtx
const { harnessWorkspaces, refreshWorkspaceData, showWorkspaceDialog, workspacesConnected } = workspacesCtx
const { harnessTools, refreshToolData, showToolDialog, toolsConnected } = toolsCtx
const { harnessModels, modelsConnected, refreshModelData, showModelDialog } = modelsCtx
const { catalogConnected, harnessSkills, refreshCatalogData, refreshSkillData, selectedCatalogName, selectedSkill, skillDirectoryTab, skillsConnected } = skillsCtx
const { approvalDetail, approvalsConnected, harnessMachines, pendingApprovalRows, refreshResourceData, rejectDialog, traceConnected } = resourcesCtx
const { loadTraceEvents, loadTraceMetrics, loadTraceTrends } = tracesCtx
const { machinesConnected } = resourcesCtx


// 每个 section 的数据来源与连接状态一一对应，避免用兜底分支把已接入的页面标成「未接入」
const sectionStatus = computed(() => {
  const skillLive = skillDirectoryTab.value === 'catalog' ? catalogConnected.value : skillsConnected.value
  return {
    overview: { live: executionConnected.value, label: executionConnected.value ? '今日真实运行记录' : executionLoaded.value ? '运行数据缓存 · 连接失败' : '运行服务未连接' },
    runs: { live: executionConnected.value, label: executionConnected.value ? '运行服务数据' : executionLoaded.value ? '运行数据缓存 · 连接失败' : '运行服务未连接' },
    evaluations: { live: evaluationConnected.value, label: evaluationConnected.value ? '实时测评数据 · 后台执行' : '未连接测评服务' },
    agents: { live: agentsConnected.value, label: agentsConnected.value ? '实时资源目录' : '未连接资源目录' },
    workspaces: { live: workspacesConnected.value, label: workspacesConnected.value ? '实时工作空间目录' : '未连接工作空间目录' },
    tools: { live: toolsConnected.value, label: toolsConnected.value ? '工具登记数据' : '未连接工具目录' },
    skills: { live: skillLive, label: skillDirectoryTab.value === 'catalog' ? (catalogConnected.value ? 'Catalog 版本目录' : 'Catalog 目录未连接') : skillsConnected.value ? '本地安装包目录' : '未连接 Skill 目录' },
    models: { live: modelsConnected.value, label: modelsConnected.value ? '模型路由登记数据' : '未连接模型目录' },
    machines: { live: machinesConnected.value, label: machinesConnected.value ? '运行时节点数据' : '未连接运行时节点 API' },
    approvals: { live: approvalsConnected.value, label: approvalsConnected.value ? '审批队列数据' : '未连接审批 API' },
    artifacts: { live: true, label: '登记产物 · 只读' },
    observability: { live: traceConnected.value, label: traceConnected.value ? '只读运营 API' : '未连接运营 API' },
    releases: { live: releaseConnected.value, label: releaseConnected.value ? '实时发布数据' : '未连接发布目录' },
    settings: { live: settingsConnected.value, label: settingsConnected.value ? '实时设置' : '默认设置 · 未连接设置 API' },
  }[activeSection.value] || { live: false, label: '未接入运行 API' }
})

const sectionMode = computed(() => sectionStatus.value.live ? 'live' : 'demo')

const sourceLabel = computed(() => sectionStatus.value.label)

const canCreateRun = computed(() => ['overview', 'runs'].includes(activeSection.value))

const canRefreshStatus = computed(() => ['overview', 'runs', 'evaluations', 'releases', 'agents', 'workspaces', 'settings', 'machines', 'approvals', 'observability'].includes(activeSection.value))

const sectionCounts = computed(() => ({
  runs: executionTotal.value,
  evaluations: evalRuns.value.length,
  agents: harnessAgents.value.length,
  workspaces: harnessWorkspaces.value.length,
  tools: harnessTools.value.length,
  skills: harnessSkills.value.length,
  models: harnessModels.value.length,
  machines: harnessMachines.value.length,
  approvals: pendingApprovalRows.value.length,
}))

const navTitle = computed(() => sections.flatMap(group => group.items).find(item => item.id === activeSection.value)?.label || '运行总览')

const pageHeading = computed(() => activeSection.value === 'overview' ? 'Harness 控制台' : navTitle.value)


function selectSection(id) {
  activeSection.value = id
  mobileNavOpen.value = false
  activeView.value = 'control'
  selectedModuleRecord.value = null
  if (id === 'observability') { loadTraceEvents(); loadTraceMetrics(); loadTraceTrends() }
}

function refreshActiveSection() {
  if (activeSection.value === 'skills') return skillDirectoryTab.value === 'catalog' ? refreshCatalogData() : refreshSkillData()
  if (activeSection.value === 'models') return refreshModelData()
  if (activeSection.value === 'tools') return refreshToolData()
  if (activeSection.value === 'agents') return refreshAgentData()
  if (activeSection.value === 'evaluations') return refreshEvaluationData()
  if (activeSection.value === 'releases') return refreshReleaseData()
  if (activeSection.value === 'workspaces') return refreshWorkspaceData()
  if (activeSection.value === 'settings') return refreshHarnessSettings()
  if (activeSection.value === 'machines' || activeSection.value === 'approvals') return refreshResourceData()
  if (activeSection.value === 'observability') { refreshResourceData(); loadTraceEvents(); loadTraceMetrics(); loadTraceTrends(); return }
  return refreshExecutionRuns()
}


const harnessRoot = ref(null)

const harnessDialogCount = computed(() => [
  selectedCatalogName.value, selectedSkill.value, showModelDialog.value, showToolDialog.value,
  showAgentDialog.value, showWorkspaceDialog.value, selectedEvaluationDataset.value, showCaseDialog.value,
  showImportDialog.value, showDatasetDialog.value, showRunDialog.value, evalRunDetail.value,
  approvalDetail.value, rejectDialog.value,
].filter(Boolean).length)

let harnessDialogReturnFocus

function harnessDialogBackdrops() {
  return Array.from(harnessRoot.value?.querySelectorAll('.modal-backdrop') || [])
}

function harnessTopDialog() {
  const backdrops = harnessDialogBackdrops()
  return backdrops[backdrops.length - 1]?.querySelector('[role="dialog"], [role="alertdialog"]') || null
}

function harnessDialogControls(dialog) {
  return Array.from(dialog?.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex="0"]') || []).filter(element => element.getClientRects().length)
}

function harnessKeydown(event) {
  const dialog = harnessTopDialog()
  if (!dialog) return
  if (event.key === 'Escape') {
    event.preventDefault()
    // 点遮罩复用各弹窗自己的关闭逻辑，保存进行中不会被误关
    harnessDialogBackdrops().pop()?.click()
  } else if (event.key === 'Tab') {
    const controls = harnessDialogControls(dialog)
    const first = controls[0]
    const last = controls[controls.length - 1]
    if (!first) event.preventDefault()
    else if (!controls.includes(document.activeElement) || (event.shiftKey && document.activeElement === first) || (!event.shiftKey && document.activeElement === last)) {
      event.preventDefault()
      const nextControl = event.shiftKey ? last : first
      nextControl.focus()
    }
  }
}

watch(harnessDialogCount, async (count, previousCount) => {
  if (count > 0) {
    if (previousCount === 0) harnessDialogReturnFocus = document.activeElement
    await nextTick()
    // 模板里的 autofocus 优先，保留各弹窗原本的落点意图
    const controls = harnessDialogControls(harnessTopDialog())
    ;(controls.find(element => element.hasAttribute('autofocus')) || controls[0])?.focus()
  } else if (previousCount > 0) {
    if (harnessDialogReturnFocus?.isConnected) harnessDialogReturnFocus.focus()
    harnessDialogReturnFocus = null
  }
})


onMounted(() => {
  if (skillDirectoryTab.value === 'catalog') refreshCatalogData()
  if (activeSection.value === 'observability') loadTraceEvents()
  refreshSkillData()
  refreshModelData()
  refreshToolData()
  refreshAgentData()
  refreshWorkspaceData()
  refreshExecutionRuns({ silent: true })
  refreshEvaluationData({ silent: true })
  refreshReleaseData({ silent: true })
  refreshResourceData({ silent: true })
  refreshHarnessSettings({ silent: true })
  loadOverviewStats()
  loadTraceTrends()
  loadTraceMetrics()
  startExecutionRefresh()
  window.addEventListener('keydown', harnessKeydown)
})

onUnmounted(() => {
  window.clearTimeout(notify.timer)
  window.removeEventListener('keydown', harnessKeydown)
})

const shellCtx = {
  activeSection,
  activeView,
  canCreateRun,
  canRefreshStatus,
  harnessDialogBackdrops,
  harnessDialogControls,
  harnessDialogCount,
  harnessKeydown,
  harnessRoot,
  harnessTopDialog,
  mobileNavOpen,
  navTitle,
  notify,
  pageHeading,
  props,
  refreshActiveSection,
  sectionCounts,
  sectionMode,
  selectSection,
  selectedModuleRecord,
  sourceLabel,
  toast,
}

provide(HARNESS_SHELL, shellCtx)
provide(HARNESS_RUNS, runsCtx)
provide(HARNESS_EVALUATIONS, evaluationsCtx)
provide(HARNESS_RELEASES, releasesCtx)
provide(HARNESS_SETTINGS, settingsCtx)
provide(HARNESS_AGENTS, agentsCtx)
provide(HARNESS_WORKSPACES, workspacesCtx)
provide(HARNESS_TOOLS, toolsCtx)
provide(HARNESS_MODELS, modelsCtx)
provide(HARNESS_SKILLS, skillsCtx)
provide(HARNESS_RESOURCES, resourcesCtx)
provide(HARNESS_TRACES, tracesCtx)
</script>

<template>
  <div ref="harnessRoot" class="harness-shell" :class="{ 'is-embedded': props.embedded }">
    <div v-if="mobileNavOpen" class="mobile-scrim" @click="mobileNavOpen = false"></div>
    <aside class="harness-sidebar" :class="{ 'is-open': mobileNavOpen }">
      <div class="brand-lockup"><div class="brand-symbol"><Workflow :size="18" :stroke-width="2" /></div><div class="brand-copy"><strong>HOTLINE</strong></div><button class="close-mobile" aria-label="关闭导航" @click="mobileNavOpen = false"><X :size="17" /></button></div>
      <nav class="side-navigation" aria-label="Harness 导航"><div v-for="group in sections" :key="group.label" class="nav-group"><div class="nav-group-label">{{ group.label }}</div><button v-for="item in group.items" :key="item.id" class="nav-link" :class="{ active: activeSection === item.id }" @click="selectSection(item.id)"><component :is="item.icon" :size="16" :stroke-width="1.8" /><span>{{ item.label }}</span><small v-if="sectionCounts[item.id]">{{ sectionCounts[item.id] }}</small></button></div></nav>
    </aside>

    <main class="main-surface">
      <header v-if="!props.embedded" class="topbar"><button class="mobile-menu" aria-label="打开导航" @click="mobileNavOpen = true"><Menu :size="19" /></button><div class="breadcrumbs"><span>Harness</span><span class="crumb-slash">/</span><strong>{{ navTitle }}</strong></div><div class="topbar-actions"><span class="demo-label" :class="sectionMode"><span></span>{{ sourceLabel }}</span><button class="avatar-small" aria-label="个人账户">SC</button></div></header>
      <div class="page-scroll"><div class="page-content">
      <div class="page-heading-row"><div><h1>{{ pageHeading }}</h1></div><div class="heading-actions"><button v-if="props.embedded" class="mobile-menu embedded-mobile-menu" type="button" title="打开 Harness 菜单" aria-label="打开 Harness 菜单" :aria-expanded="mobileNavOpen" @click="mobileNavOpen = true"><Menu :size="18" /></button><span v-if="props.embedded" class="embedded-source-label">{{ sourceLabel }}</span><button v-if="canRefreshStatus" class="button button-subtle refresh-button" title="刷新状态" aria-label="刷新状态" @click="refreshActiveSection"><Activity :size="15" /><span>{{ executionLoading ? '刷新中…' : '刷新状态' }}</span></button><button v-if="canCreateRun" class="button button-primary" @click="openCreateRun"><Plus :size="16" />新建运行</button></div></div>
      <div v-if="executionError && ['overview', 'runs'].includes(activeSection)" class="execution-error-banner"><ShieldCheck :size="16" /><span>{{ executionError }}。{{ executionLoaded ? '保留上次读取的记录。' : '尚未读取到运行记录。' }}</span><button class="text-action" @click="refreshExecutionRuns">重试</button></div>
      <div v-if="evaluationError && activeSection === 'evaluations'" class="execution-error-banner"><ShieldCheck :size="16" /><span>{{ evaluationError }}，当前保留测评演示数据。</span><button class="text-action" @click="refreshEvaluationData">重试</button></div>
      <div v-if="releaseError && activeSection === 'releases'" class="execution-error-banner"><ShieldCheck :size="16" /><span>{{ releaseError }}，当前保留发布演示数据。</span><button class="text-action" @click="refreshReleaseData">重试</button></div>

      <div v-if="settingsError && activeSection === 'settings'" class="execution-error-banner"><ShieldCheck :size="16" /><span>{{ settingsError }}，当前保留默认设置。</span><button class="text-action" @click="refreshHarnessSettings">重试</button></div>

        <OverviewPanel v-if="activeSection === 'overview'" />
        <RunsPanel v-if="activeSection === 'runs'" />
        <EvaluationsPanel v-if="activeSection === 'evaluations'" />
        <SettingsPanel v-if="activeSection === 'settings'" />
        <ArtifactsPanel v-if="activeSection === 'artifacts'" />
        <TracesPanel v-if="activeSection === 'observability'" />
        <ResourcesPanel v-if="['machines', 'approvals'].includes(activeSection)" />
        <ToolsPanel v-if="activeSection === 'tools'" />
        <ModelsPanel v-if="activeSection === 'models'" />
        <SkillDirectoryPanel v-if="activeSection === 'skills'" />
        <AgentsPanel v-if="activeSection === 'agents'" />
        <WorkspacesPanel v-if="activeSection === 'workspaces'" />
        <ReleasesPanel v-if="activeSection === 'releases'" />
      </div></div>
      <div v-if="toast" class="toast-message"><Check :size="15" />{{ toast }}</div>
    </main>
  </div>
</template>
