import { computed, reactive, ref } from 'vue'
import { Bot, Smile, Sparkles } from 'lucide-vue-next'
import { deleteCredential, getCredential, getProfile, saveCredential, saveProfile, testCredential } from '../../api'
import { apiToken, setApiToken } from '../auth/token'

// 虚拟桌宠的可选形象。
export const petOptions = [
  { id: 'smile', label: '微笑伙伴', icon: Smile },
  { id: 'bot', label: '机器人伙伴', icon: Bot },
  { id: 'sparkle', label: '闪耀伙伴', icon: Sparkles },
]

export function useProfile(ctx) {
  const profileDraft = ref({ nickname: '', bio: '', answerStyle: 'default', theme: 'system' })
  const profileBusy = ref(false)
  const credentialDraft = ref({ provider: '', baseUrl: '', model: '', apiKey: '' })
  const credentialBusy = ref(false)
  const credentialMask = ref('')
  // 访问令牌：与后端 HOTLINE_API_TOKEN 一致，未配置时不发该请求头。
  const accessTokenDraft = ref(apiToken())
  const petEnabled = ref(localStorage.getItem('hotline-pet-enabled') === '1')
  const petChoice = ref(localStorage.getItem('hotline-pet') || 'smile')

  const petIcon = computed(() => petOptions.find(item => item.id === petChoice.value)?.icon || Smile)
  const petLabel = computed(() => petOptions.find(item => item.id === petChoice.value)?.label || '虚拟伙伴')

  function applyTheme(theme) {
    const root = document.documentElement
    if (theme === 'light' || theme === 'dark') root.setAttribute('data-theme', theme)
    else root.removeAttribute('data-theme')
  }

  async function refreshProfile() {
    try {
      const profile = await getProfile(ctx.backendUrl)
      profileDraft.value = {
        nickname: profile.nickname || '',
        bio: profile.bio || '',
        answerStyle: profile.answerStyle || 'default',
        theme: profile.theme || 'system',
      }
      applyTheme(profileDraft.value.theme)
    } catch (error) {
      // 后端不可用时保持当前界面，不写入假的默认值。
    }
  }

  async function saveProfileBasics() {
    if (profileBusy.value) return
    profileBusy.value = true
    try {
      await saveProfile(ctx.backendUrl, {
        nickname: profileDraft.value.nickname.trim(),
        bio: profileDraft.value.bio.trim(),
      })
      ctx.showToast('个人资料已保存')
    } catch (error) {
      ctx.showToast(`保存失败：${error.message || '个人设置服务不可用'}`)
    } finally {
      profileBusy.value = false
    }
  }

  async function savePreferences() {
    if (profileBusy.value) return
    profileBusy.value = true
    try {
      await saveProfile(ctx.backendUrl, {
        answerStyle: profileDraft.value.answerStyle,
        theme: profileDraft.value.theme,
      })
      applyTheme(profileDraft.value.theme)
      ctx.showToast('偏好已保存')
    } catch (error) {
      ctx.showToast(`保存失败：${error.message || '个人设置服务不可用'}`)
    } finally {
      profileBusy.value = false
    }
  }

  async function refreshCredential() {
    try {
      const credential = await getCredential(ctx.backendUrl)
      credentialDraft.value = {
        provider: credential?.provider || '',
        baseUrl: credential?.base_url || '',
        model: credential?.model || '',
        apiKey: '',
      }
      credentialMask.value = credential?.apiKey || ''
    } catch (error) {
      credentialMask.value = ''
    }
  }

  function credentialPayload() {
    const payload = {
      provider: credentialDraft.value.provider.trim(),
      baseUrl: credentialDraft.value.baseUrl.trim(),
      model: credentialDraft.value.model.trim(),
    }
    if (credentialDraft.value.apiKey.trim()) payload.apiKey = credentialDraft.value.apiKey.trim()
    return payload
  }

  async function saveCredentialForm() {
    if (credentialBusy.value) return
    credentialBusy.value = true
    try {
      await saveCredential(ctx.backendUrl, credentialPayload())
      credentialDraft.value.apiKey = ''
      await refreshCredential()
      ctx.showToast('模型凭证已保存')
    } catch (error) {
      ctx.showToast(`保存失败：${error.message || '凭证服务不可用'}`)
    } finally {
      credentialBusy.value = false
    }
  }

  function saveAccessToken() {
    setApiToken(accessTokenDraft.value)
    accessTokenDraft.value = apiToken()
    ctx.showToast(accessTokenDraft.value ? '访问令牌已保存' : '访问令牌已清除')
  }

  async function testCredentialForm() {
    if (credentialBusy.value) return
    credentialBusy.value = true
    try {
      const result = await testCredential(ctx.backendUrl, credentialPayload())
      ctx.showToast(result?.ok ? '模型连接正常' : (result?.message || '模型连接失败'))
    } catch (error) {
      ctx.showToast(`测试失败：${error.message || '凭证服务不可用'}`)
    } finally {
      credentialBusy.value = false
    }
  }

  async function removeCredential() {
    if (!window.confirm('删除已保存的模型凭证？')) return
    try {
      await deleteCredential(ctx.backendUrl)
      await refreshCredential()
      ctx.showToast('已删除模型凭证')
    } catch (error) {
      ctx.showToast(`删除失败：${error.message || '凭证服务不可用'}`)
    }
  }

  function togglePet() {
    petEnabled.value = !petEnabled.value
    localStorage.setItem('hotline-pet-enabled', petEnabled.value ? '1' : '0')
  }

  function choosePet(id) {
    petChoice.value = id
    localStorage.setItem('hotline-pet', id)
  }

  const state = reactive({
    profileDraft, profileBusy, credentialDraft, credentialBusy, credentialMask,
    accessTokenDraft, petEnabled, petChoice, petIcon, petLabel,
  })

  const actions = {
    refreshProfile, saveProfileBasics, savePreferences, refreshCredential,
    saveCredentialForm, saveAccessToken, testCredentialForm, removeCredential,
    togglePet, choosePet,
  }

  return { state, actions }
}
