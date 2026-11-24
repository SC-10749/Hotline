<script setup>
import { computed, nextTick, onMounted, onUnmounted, provide, ref, watch } from 'vue'
import {
  AlertCircle, Bot, CalendarClock, CheckCircle2, CircleUserRound, Download, FolderOpen,
  History, Home, LibraryBig, LoaderCircle, Map as MapIcon, PanelLeft,
  Plus, Puzzle, Settings2, Workflow,
} from 'lucide-vue-next'
import HarnessApp from './HarnessApp.vue'
import CodeMapPage from './modules/artifacts/CodeMapPage.vue'
import { useAppContext } from './modules/app/context'
import {
  APP_KEY, AUTOMATION_KEY, BOTS_KEY, CHAT_KEY, DOCUMENTS_KEY, PROFILE_KEY,
  SETTINGS_KEY, SKILLS_KEY, WORKSPACES_KEY,
} from './modules/app/keys'
import { useChat } from './modules/chat/useChat'
import { useWorkspaces } from './modules/workspaces/useWorkspaces'
import { useDocuments } from './modules/documents/useDocuments'
import { useSkills } from './modules/skills/useSkills'
import { useBots } from './modules/bots/useBots'
import { useAutomation } from './modules/automation/useAutomation'
import { useProfile } from './modules/profile/useProfile'
import { useSettings } from './modules/settings/useSettings'
import SessionSidebar from './modules/chat/SessionSidebar.vue'
import ChatView from './modules/chat/ChatView.vue'
import PermissionDialog from './modules/chat/PermissionDialog.vue'
import ExportPage from './modules/chat/ExportPage.vue'
import WorkspacePanel from './modules/workspaces/WorkspacePanel.vue'
import FolderImportDialog from './modules/workspaces/FolderImportDialog.vue'
import ProjectNameDialog from './modules/workspaces/ProjectNameDialog.vue'
import DocumentsDialog from './modules/documents/DocumentsDialog.vue'
import DocumentPreviewDialog from './modules/documents/DocumentPreviewDialog.vue'
import DocsPage from './modules/documents/DocsPage.vue'
import SkillsDialog from './modules/skills/SkillsDialog.vue'
import PluginsPage from './modules/skills/PluginsPage.vue'
import BotPage from './modules/bots/BotPage.vue'
import BotSidebar from './modules/bots/BotSidebar.vue'
import AutomationPage from './modules/automation/AutomationPage.vue'
import ProfilePage from './modules/profile/ProfilePage.vue'
import ProfileSidebar from './modules/profile/ProfileSidebar.vue'
import SettingsDialog from './modules/settings/SettingsDialog.vue'

// 壳层：只管布局、导航、弹窗焦点管理与跨页面 toast；具体能力都在 modules/ 下。
const ctx = useAppContext()
const chat = useChat(ctx)
const workspaces = useWorkspaces(ctx)
const documents = useDocuments(ctx)
const skills = useSkills(ctx)
const bots = useBots(ctx, skills)
const automation = useAutomation(ctx)
const profile = useProfile(ctx)
const settings = useSettings(ctx)

provide(APP_KEY, ctx)
provide(CHAT_KEY, chat)
provide(WORKSPACES_KEY, workspaces)
provide(DOCUMENTS_KEY, documents)
provide(SKILLS_KEY, skills)
provide(BOTS_KEY, bots)
provide(AUTOMATION_KEY, automation)
provide(PROFILE_KEY, profile)
provide(SETTINGS_KEY, settings)

// 视图层持有的 DOM 引用：跨模块的滚动与文件选择统一走钩子表。
const chatView = ref(null)
const sessionSidebar = ref(null)

ctx.hooks.newSession = () => chat.actions.newSession()
ctx.hooks.refreshSessions = () => chat.actions.refreshSessions()
ctx.hooks.closeDocs = () => documents.actions.closeDocs()
ctx.hooks.scrollToBottom = () => chatView.value?.scrollToBottom()
ctx.hooks.focusComposer = (options) => chatView.value?.focusComposer(options)
ctx.hooks.pickFile = () => chatView.value?.pickFile()
ctx.hooks.pickWorkspaceFolder = () => sessionSidebar.value?.pickFolder()
ctx.hooks.openHome = () => openHome()
ctx.hooks.showNotifications = () => showNotifications()

function toggleSidebar() {
  if (window.matchMedia('(max-width: 960px)').matches) {
    ctx.mobileSidebarOpen = !ctx.mobileSidebarOpen
    ctx.sidebarCollapsed = false
    return
  }
  ctx.sidebarCollapsed = !ctx.sidebarCollapsed
}

function openHome() {
  ctx.activePage = 'home'
  ctx.showWorkspacePanel = false
  ctx.mobileSidebarOpen = false
  if (!chat.state.currentSession) chat.actions.newSession()
  nextTick(() => ctx.hooks.focusComposer({ preventScroll: true }))
}

function openAutomation() {
  ctx.activePage = 'automation'
  ctx.showWorkspacePanel = false
  ctx.mobileSidebarOpen = false
  automation.actions.refreshSchedules()
}

function openPlugins() {
  ctx.activePage = 'plugins'
  ctx.showWorkspacePanel = false
  ctx.mobileSidebarOpen = false
  skills.actions.refreshSkills()
}

function openBotPage() {
  ctx.activePage = 'bot'
  ctx.showWorkspacePanel = false
  ctx.mobileSidebarOpen = false
  bots.actions.refreshBots()
  skills.actions.refreshSkills()
}

function openDocsPage() {
  ctx.activePage = 'docs'
  ctx.showWorkspacePanel = false
  ctx.mobileSidebarOpen = false
}

function openHarnessPage() {
  ctx.activePage = 'harness'
  ctx.showWorkspacePanel = false
  ctx.mobileSidebarOpen = false
}

function openCodeMapPage() {
  ctx.activePage = 'code-map'
  ctx.showWorkspacePanel = false
  ctx.mobileSidebarOpen = false
}

function openExportPage() {
  ctx.activePage = 'export'
  ctx.showWorkspacePanel = false
  ctx.mobileSidebarOpen = false
}

function showNotifications() {
  ctx.showToast('暂无新通知')
}

function openMore() {
  ctx.activePage = 'profile'
  ctx.profileSection = 'basics'
  ctx.showWorkspacePanel = false
  ctx.mobileSidebarOpen = false
  profile.actions.refreshProfile()
  profile.actions.refreshCredential()
}

function sidebarToggleLabel() {
  if (window.matchMedia('(max-width: 960px)').matches) {
    return ctx.mobileSidebarOpen ? '关闭会话栏' : '打开会话栏'
  }
  return ctx.sidebarCollapsed ? '展开会话栏' : '收起会话栏'
}

function sidebarIsExpanded() {
  return window.matchMedia('(max-width: 960px)').matches ? ctx.mobileSidebarOpen : !ctx.sidebarCollapsed
}

// 弹窗统一按 DOM 定位：App 的遮罩挂在 body 上，不会误伤 Harness 内嵌弹窗
const appDialogCount = computed(() => [
  settings.state.showSettings, skills.state.showSkills, documents.state.showDocs, documents.state.showDocPreview,
  workspaces.state.folderImportOpen, ctx.permissionRequest, workspaces.state.showProjectNameDialog,
].filter(Boolean).length)
let appDialogReturnFocus
function appDialogBackdrops() {
  return Array.from(document.body.children).filter(element => element.classList.contains('modal-backdrop'))
}
function appTopDialog() {
  const backdrops = appDialogBackdrops()
  return backdrops[backdrops.length - 1]?.querySelector('[role="dialog"], [role="alertdialog"]') || null
}
function appDialogControls(dialog) {
  return Array.from(dialog?.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], summary, [tabindex="0"]') || []).filter(element => element.getClientRects().length)
}
watch(appDialogCount, async (count, previousCount) => {
  if (count > 0) {
    if (previousCount === 0) appDialogReturnFocus = document.activeElement
    await nextTick()
    // 模板里的 autofocus 优先，保留各弹窗原本的落点意图
    const controls = appDialogControls(appTopDialog())
    ;(controls.find(element => element.hasAttribute('autofocus')) || controls[0])?.focus()
  } else if (previousCount > 0) {
    if (appDialogReturnFocus?.isConnected) appDialogReturnFocus.focus()
    appDialogReturnFocus = null
  }
})

let keydownHandler
let visibilityHandler
onMounted(() => {
  keydownHandler = (event) => {
    if (appTopDialog()) {
      if (event.key === 'Escape') {
        event.preventDefault()
        // 点遮罩复用各弹窗自己的关闭逻辑，保存或上传进行中不会被误关
        appDialogBackdrops().pop()?.click()
      } else if (event.key === 'Tab') {
        const controls = appDialogControls(appTopDialog())
        const first = controls[0]
        const last = controls[controls.length - 1]
        if (!first) event.preventDefault()
        else if (!controls.includes(document.activeElement) || (event.shiftKey && document.activeElement === first) || (!event.shiftKey && document.activeElement === last)) {
          event.preventDefault()
          const nextControl = event.shiftKey ? last : first
          nextControl.focus()
        }
      }
      return
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault()
      chat.actions.newSession()
    }
    if (event.key === 'Escape') ctx.mobileSidebarOpen = false
  }
  window.addEventListener('keydown', keydownHandler)
  // 回到前台时重新对齐会话列表：会话可能在别的窗口或后端被删掉
  visibilityHandler = () => { if (document.visibilityState === 'visible') chat.actions.refreshSessions() }
  document.addEventListener('visibilitychange', visibilityHandler)
  const restoredMode = ctx.activeMode
  chat.actions.newSession()
  ctx.activeMode = restoredMode
  chat.actions.refreshSessions()
  workspaces.actions.refreshWorkspaces()
  skills.actions.loadSkillsSilently()
  profile.actions.refreshProfile()
  if (ctx.activePage === 'automation') automation.actions.refreshSchedules()
  if (ctx.activePage === 'bot') bots.actions.refreshBots()
})

onUnmounted(() => {
  window.removeEventListener('keydown', keydownHandler)
  document.removeEventListener('visibilitychange', visibilityHandler)
})
</script>

<template>
  <div class="app-shell" :class="{ 'chat-page': ctx.activePage === 'home', 'sidebar-collapsed': ctx.sidebarCollapsed, 'standalone-page-active': ctx.activePage !== 'home' }">
    <div v-if="ctx.mobileSidebarOpen" class="drawer-backdrop" @click="ctx.mobileSidebarOpen = false"></div>
    <aside class="app-rail" aria-label="主导航">
      <button class="rail-button" :class="{ active: ctx.activePage === 'home' }" type="button" aria-label="首页" title="首页" @click="openHome"><Home :size="20" fill="currentColor" /></button>
      <button class="rail-button" :class="{ active: ctx.activePage === 'automation' }" type="button" aria-label="自动化" title="自动化" @click="openAutomation"><CalendarClock :size="20" /></button>
      <button class="rail-button" :class="{ active: ctx.activePage === 'plugins' }" type="button" aria-label="插件" title="插件" @click="openPlugins"><Puzzle :size="20" /></button>
      <button class="rail-button" :class="{ active: ctx.activePage === 'bot' }" type="button" aria-label="机器人" title="机器人" @click="openBotPage"><Bot :size="20" /></button>
      <button class="rail-button" :class="{ active: ctx.activePage === 'docs' }" type="button" aria-label="文档库" title="文档库" @click="openDocsPage"><LibraryBig :size="20" /></button>
      <button class="rail-button" :class="{ active: ctx.activePage === 'harness' }" type="button" aria-label="Harness 工程" title="Harness 工程" @click="openHarnessPage"><Workflow :size="20" /></button>
      <button class="rail-button" :class="{ active: ctx.activePage === 'code-map' }" type="button" aria-label="代码地图" title="代码地图" @click="openCodeMapPage"><MapIcon :size="20" /></button>
      <button class="rail-button" :class="{ active: ctx.activePage === 'export' }" type="button" aria-label="导出历史聊天" title="导出历史聊天" @click="openExportPage"><History :size="20" /></button>
      <button class="rail-profile" type="button" aria-label="用户设置" title="用户设置" @click="openMore"><CircleUserRound :size="19" :stroke-width="1.9" /></button>
    </aside>
    <SessionSidebar ref="sessionSidebar" />

    <main class="workspace" :class="{ 'workspace-panel-open': ctx.showWorkspacePanel, 'workspace-welcome': chat.state.isWelcome, 'workspace-code-map': ctx.activePage === 'code-map' }">
      <template v-if="ctx.activePage === 'home'">
        <header class="topbar">
          <div class="topbar-left">
            <button class="icon-button sidebar-toggle" type="button" aria-controls="conversation-sidebar" :aria-expanded="sidebarIsExpanded()" :aria-label="sidebarToggleLabel()" :title="sidebarToggleLabel()" @click="toggleSidebar"><PanelLeft :size="19" /></button>
            <div v-if="chat.state.currentSession && chat.state.currentSession.title !== '新对话'" class="breadcrumb"><FolderOpen :size="21" /><strong>{{ chat.state.currentSession.title }}</strong></div>
            <span v-else class="topbar-title">新对话</span>
          </div>
        </header>
        <ChatView ref="chatView" />
        <WorkspacePanel />
      </template>

      <CodeMapPage v-else-if="ctx.activePage === 'code-map'" :api-base="ctx.backendUrl" @home="openHome" />
      <section v-else class="standalone-page" :aria-labelledby="`${ctx.activePage}-page-title`">
        <aside class="page-sidebar">
          <header class="page-sidebar-header">
            <h2>{{ ctx.activePage === 'profile' ? '个人中心' : ({ automation: '自动化', plugins: '插件', bot: '机器人', docs: '文档库', harness: 'Harness 工程', export: '历史聊天' })[ctx.activePage] }}</h2>
          </header>
          <ProfileSidebar v-if="ctx.activePage === 'profile'" />
          <button v-else-if="ctx.activePage === 'automation'" class="page-create" type="button" @click="automation.actions.openScheduleForm"><Plus :size="18" />新建任务</button>
          <button v-else-if="ctx.activePage === 'plugins'" class="page-create" type="button" @click="skills.actions.openSkills"><Puzzle :size="18" />上传技能包</button>
          <BotSidebar v-else-if="ctx.activePage === 'bot'" />
          <button v-else-if="ctx.activePage === 'docs'" class="page-create" type="button" @click="documents.actions.openDocs"><Plus :size="18" />上传文档</button>
          <button v-else-if="ctx.activePage === 'harness'" class="page-subitem active" type="button" @click="openHarnessPage"><Workflow :size="16" />Harness 控制面<span>已接入</span></button>
          <button v-else class="page-create" type="button" :disabled="chat.state.exportingHistory" @click="chat.actions.exportChatHistory"><LoaderCircle v-if="chat.state.exportingHistory" :size="18" class="spin" /><Download v-else :size="18" />导出全部聊天</button>
        </aside>

        <div class="page-main">
          <header v-if="ctx.activePage !== 'harness'" class="standalone-header">
            <div>
              <h1 :id="`${ctx.activePage}-page-title`">{{ ctx.activePage === 'profile' ? ({ basics: '基础信息', api: 'API Key', personalization: '个性化', pet: '虚拟桌宠' })[ctx.profileSection] : ({ automation: '安排任务', plugins: '插件', bot: '机器人', docs: '文档库', harness: 'Harness 工程', export: '导出历史聊天' })[ctx.activePage] }}</h1>
            </div>
            <button class="icon-button" type="button" aria-label="回到首页" title="回到首页" @click="openHome"><Home :size="18" /></button>
          </header>
          <ProfilePage v-if="ctx.activePage === 'profile'" />
          <HarnessApp v-if="ctx.activePage === 'harness'" embedded :api-base="ctx.backendUrl" />
          <AutomationPage v-if="ctx.activePage === 'automation'" />
          <PluginsPage v-else-if="ctx.activePage === 'plugins'" />
          <BotPage v-else-if="ctx.activePage === 'bot'" />
          <DocsPage v-else-if="ctx.activePage === 'docs'" />
          <ExportPage v-else-if="ctx.activePage === 'export'" />
        </div>
      </section>
    </main>

    <div v-if="profile.state.petEnabled" class="page-pet" :title="profile.state.petLabel"><component :is="profile.state.petIcon" :size="22" /></div>
    <Transition name="toast"><div v-if="ctx.toast" class="toast-message" role="status"><CheckCircle2 :size="17" />{{ ctx.toast }}</div></Transition>

    <div v-if="ctx.connectionState === 'offline'" class="connection-banner" role="alert"><AlertCircle :size="17" /><span>{{ ctx.connectionMessage || 'Python 服务暂不可用' }}</span><button type="button" @click="settings.actions.retryConnection">重试</button><button class="icon-button" type="button" aria-label="设置服务地址" @click="settings.actions.openSettings"><Settings2 :size="16" /></button></div>

    <Teleport to="body">
      <Transition name="modal">
        <SettingsDialog v-if="settings.state.showSettings" @close="settings.state.showSettings = false" @save="settings.actions.saveSettings" />
      </Transition>
      <Transition name="modal">
        <FolderImportDialog v-if="workspaces.state.folderImportOpen" />
      </Transition>
      <Transition name="modal">
        <ProjectNameDialog v-if="workspaces.state.showProjectNameDialog" />
      </Transition>
      <Transition name="modal">
        <SkillsDialog v-if="skills.state.showSkills" />
      </Transition>
      <Transition name="modal">
        <DocumentsDialog v-if="documents.state.showDocs" />
      </Transition>
      <Transition name="modal">
        <DocumentPreviewDialog v-if="documents.state.showDocPreview" />
      </Transition>
      <Transition name="modal">
        <PermissionDialog v-if="ctx.permissionRequest" :request="ctx.permissionRequest" @confirm="chat.actions.confirmPermission" @cancel="chat.actions.cancelPermission" />
      </Transition>
    </Teleport>
  </div>
</template>
