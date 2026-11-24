import { reactive, ref } from 'vue'
import { testBackend } from '../../api'

export function useSettings(ctx) {
  const settingsDraft = ref(ctx.backendUrl)
  const busySettings = ref(false)
  const showSettings = ref(false)

  function openSettings() {
    settingsDraft.value = ctx.backendUrl
    showSettings.value = true
  }

  async function saveSettings() {
    const value = settingsDraft.value.trim().replace(/\/+$/, '')
    if (value && !/^https?:\/\//i.test(value)) {
      ctx.showToast('留空恢复同源地址，或输入以 http:// 开头的服务地址')
      return
    }
    busySettings.value = true
    try {
      ctx.backendUrl = value
      if (value) localStorage.setItem('dodo-api-base', value)
      else localStorage.removeItem('dodo-api-base')
      await testBackend(value)
      ctx.connectionState = 'online'
      ctx.connectionMessage = ''
      showSettings.value = false
      ctx.showToast(value ? '服务连接正常' : '已恢复同源服务地址')
      await ctx.hooks.refreshSessions()
    } catch (error) {
      ctx.connectionState = 'offline'
      ctx.connectionMessage = error.message
      ctx.showToast(`连接失败：${error.message}`)
    } finally {
      busySettings.value = false
    }
  }

  async function retryConnection() {
    ctx.connectionState = 'checking'
    await ctx.hooks.refreshSessions()
  }

  const state = reactive({ settingsDraft, busySettings, showSettings })

  const actions = { openSettings, saveSettings, retryConnection }

  return { state, actions }
}
