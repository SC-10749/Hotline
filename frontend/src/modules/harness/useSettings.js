// Harness 设置：运行策略与默认参数。
import { ref } from 'vue'
import { setArtifactOwnerHeader } from '../artifacts/api.js'
import { getHarnessSettings, saveHarnessSettings } from '../../api'

export function useSettings({ props, notify }) {
  const harnessSettings = ref({ isolation: 'container', auditRetentionDays: 30, approvalPolicy: 'risk-based', defaultBudgetUsd: 0.2, defaultTimeoutSeconds: 900, defaultRetryCount: 1 })
  const settingsConnected = ref(false)
  const settingsError = ref('')
  async function refreshHarnessSettings({ silent = false } = {}) {
    try {
      const result = await getHarnessSettings(props.apiBase)
      harnessSettings.value = result?.settings || harnessSettings.value
      // 产物归属请求头名跟着设置走，避免前后端各认一个名字。
      setArtifactOwnerHeader(harnessSettings.value?.artifactOwnerHeader)
      settingsConnected.value = true
      settingsError.value = ''
    } catch (error) {
      settingsConnected.value = false
      settingsError.value = error.message || '设置服务暂不可用'
      if (!silent) notify(`设置读取失败：${settingsError.value}`)
    }
  }

  async function saveSettings() {
    try {
      const result = await saveHarnessSettings(props.apiBase, harnessSettings.value)
      harnessSettings.value = result.settings
      settingsConnected.value = true
      notify('Harness 设置已保存')
    } catch (error) { notify(`设置保存失败：${error.message || '设置服务不可用'}`) }
  }


  return {
    harnessSettings,
    refreshHarnessSettings,
    saveSettings,
    settingsConnected,
    settingsError,
  }
}
