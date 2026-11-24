<script setup>
import { inject, ref } from 'vue'
import { Bell, ChevronDown, CircleDot, FolderOpen, Headset, MoreHorizontal, Plus, Search, Trash2, X } from 'lucide-vue-next'
import { APP_KEY, CHAT_KEY, WORKSPACES_KEY } from '../app/keys'

const ctx = inject(APP_KEY)
const chat = inject(CHAT_KEY)
const workspaces = inject(WORKSPACES_KEY)
const projectFolderInput = ref(null)

// 工作区目录选择：浏览器不提供目录选择事件，只能由隐藏 input 触发。
function pickFolder() {
  projectFolderInput.value?.click()
}

defineExpose({ pickFolder })
</script>

<template>
  <aside id="conversation-sidebar" class="sidebar" :class="{ 'sidebar-open': ctx.mobileSidebarOpen }" aria-label="会话导航">
    <div class="sidebar-top">
      <div class="brand-row">
        <div class="brand-mark"><Headset :size="18" :stroke-width="2" /></div>
        <span class="brand-name">Hotline</span>
        <div class="brand-actions">
          <button class="icon-button" type="button" aria-label="通知" title="通知" @click="ctx.hooks.showNotifications()"><Bell :size="17" /></button>
          <button class="icon-button" type="button" :aria-label="chat.state.searchOpen ? '关闭搜索' : '搜索会话'" @click="chat.actions.toggleSearch"><Search :size="17" /></button>
          <button class="icon-button mobile-close" type="button" aria-label="关闭会话栏" @click="ctx.mobileSidebarOpen = false"><X :size="18" /></button>
        </div>
      </div>

      <nav class="quick-nav" aria-label="快捷入口">
        <button class="nav-item" type="button" @click="chat.actions.newSession"><Plus :size="18" /><span>新对话</span><kbd>Ctrl K</kbd></button>
      </nav>

      <section class="project-nav" aria-label="工作区">
        <h2 class="project-nav-heading"><span>工作区</span><button class="icon-button workspace-add" type="button" :disabled="workspaces.state.projectUploadBusy" aria-label="添加工作区" title="添加工作区" @click="workspaces.actions.addWorkspace"><Plus :size="16" /></button></h2>
        <div v-for="project in ctx.projectGroups" :key="project.id" class="project-entry" :class="{ selected: ctx.selectedProjectId === project.id }">
          <div class="project-line">
            <button type="button" class="project-open" :aria-label="`打开工作区：${project.name}`" @click="ctx.selectedProjectName = project.name; ctx.selectedProjectId = project.id; workspaces.actions.openProjectView()"><FolderOpen :size="18" /><span>{{ project.name }}</span></button>
            <button class="project-add-task icon-button" type="button" :disabled="workspaces.state.projectUploadBusy" :aria-label="`在工作区添加任务：${project.name}`" :title="`添加任务到 ${project.name}`" @click="workspaces.actions.addWorkspaceTask(project)"><Plus :size="15" /></button>
          </div>
          <div v-if="project.child" class="project-child">{{ project.child }}</div>
          <button v-for="task in project.tasks || []" :key="task.id" type="button" class="project-task" @click="ctx.selectedProjectName = project.name; ctx.selectedProjectId = project.id; ctx.hooks.openHome()"><CircleDot :size="11" /><span>{{ task.title }}</span></button>
        </div>
        <p v-if="!ctx.projectGroups.length" class="workspace-empty">暂无工作区，点击 + 添加文件夹</p>
      </section>
      <input ref="projectFolderInput" class="visually-hidden" type="file" webkitdirectory directory multiple @change="workspaces.actions.onProjectFolderPicked" />

      <label v-if="chat.state.searchOpen" class="session-search"><Search :size="15" /><input v-model="chat.state.searchText" autofocus placeholder="搜索会话" /><button class="icon-button" aria-label="清除搜索" @click="chat.state.searchText = ''"><X :size="14" /></button></label>
    </div>

    <nav class="session-list" aria-label="历史会话">
      <template v-if="chat.state.runningItem.length">
        <div class="session-heading"><span>运行中</span></div>
        <div v-for="session in chat.state.runningItem" :key="session.id" class="session-item task-card running" :class="{ active: chat.state.activeId === session.id }">
          <button class="session-select" type="button" @click="chat.actions.selectSession(session.id)">
            <span class="session-dot"><span class="dot run"></span></span>
            <span class="session-main">
              <span class="session-title-row"><span class="session-title">{{ session.title }}</span><span class="mono-time">{{ chat.state.runningElapsed }}</span></span>
              <span class="session-meta"><span class="badge" :class="chat.actions.badgeInfo(session.agentType).cls">{{ chat.actions.badgeInfo(session.agentType).label }}</span><span class="meta-note">正在执行</span></span>
            </span>
          </button>
        </div>
      </template>
      <div class="session-heading recent-heading"><span>最近</span><ChevronDown :size="16" /><span class="recent-heading-actions"><button class="icon-button" type="button" aria-label="最近会话更多"><MoreHorizontal :size="17" /></button><button class="icon-button" type="button" aria-label="新建最近会话" @click="chat.actions.newSession"><Plus :size="17" /></button></span></div>
      <div v-for="session in chat.state.recentList" :key="session.id" class="session-item task-card" :class="{ active: chat.state.activeId === session.id }">
        <button class="session-select" type="button" @click="chat.actions.selectSession(session.id)">
          <span class="session-dot"><span class="dot ok"></span></span>
          <span class="session-main">
            <span class="session-title-row"><span class="session-title">{{ session.title }}</span></span>
            <span class="session-meta"><span class="badge" :class="chat.actions.badgeInfo(session.agentType).cls">{{ chat.actions.badgeInfo(session.agentType).label }}</span><span class="meta-note">{{ chat.actions.fmtRelTime(session.createTime || session.updatedAt) }}</span></span>
          </span>
        </button>
        <button v-if="!session.isDraft" class="session-delete icon-button" type="button" :disabled="!!chat.state.deletingId" :aria-label="`删除会话：${session.title}`" @click.stop="chat.actions.deleteConversation(session.id)"><Trash2 :size="15" /></button>
      </div>
      <div v-if="chat.state.recentList.length === 0" class="session-empty">{{ chat.state.searchText ? '没有匹配的会话' : '还没有历史会话' }}</div>
    </nav>

  </aside>
</template>
