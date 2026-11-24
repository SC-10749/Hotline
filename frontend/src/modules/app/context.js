import { reactive, ref } from 'vue'
import { usePageState } from '../../composables/usePageState'
import { modes } from '../chat/modes'

// 跨能力共享的内核：后端地址、页面/模式、toast、授权弹窗与工作区指针。
// 模块之间不互相 import 对方的实现，需要跨模块调用时统一走 ctx.hooks。
export function useAppContext() {
  const backendUrl = ref(localStorage.getItem('dodo-api-base') || import.meta.env.VITE_API_BASE_URL || '')
  const activeMode = usePageState('chat-mode', 'chat', modes.map(mode => mode.id))
  const activePage = usePageState('page', 'home', ['home', 'automation', 'plugins', 'bot', 'docs', 'harness', 'code-map', 'export', 'profile'])
  const profileSection = usePageState('profile', 'basics', ['basics', 'api', 'personalization', 'pet'])
  const workspacePanelTab = usePageState('workspace-tab', 'files', ['files', 'changes'])
  const toast = ref('')
  const permissionRequest = ref(null)
  const connectionState = ref('checking')
  const connectionMessage = ref('')
  let toastTimer
  function showToast(message) {
    toast.value = message
    clearTimeout(toastTimer)
    toastTimer = setTimeout(() => { toast.value = '' }, 2600)
  }
  return reactive({
    backendUrl,
    activeMode,
    activePage,
    profileSection,
    workspacePanelTab,
    toast,
    permissionRequest,
    connectionState,
    connectionMessage,
    showToast,
    mobileSidebarOpen: false,
    sidebarCollapsed: false,
    showWorkspacePanel: false,
    selectedProjectId: '',
    selectedProjectName: '',
    projectGroups: [],
    // 跨模块调用的钩子表，由 App.vue 在装配时绑定到具体实现。
    hooks: {
      newSession: () => {},
      refreshSessions: async () => {},
      closeDocs: () => {},
      scrollToBottom: async () => {},
      focusComposer: () => {},
      pickFile: () => {},
      pickWorkspaceFolder: () => {},
    },
  })
}
