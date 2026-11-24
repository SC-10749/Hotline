import { computed, reactive, ref } from 'vue'
import { Brain, Bug, ClipboardCheck, ClipboardList, Code, Server, Wrench } from 'lucide-vue-next'
import { createBot, deleteBot, getBots, getCiWorkflow, setCiWorkflow, updateBot } from '../../api'
import botAiAvatar from '../../assets/bot-ai-avatar.jpg'
import botBackendAvatar from '../../assets/bot-backend-avatar.jpg'
import botDevopsAvatar from '../../assets/bot-devops-avatar.jpg'
import botFrontendAvatar from '../../assets/bot-frontend-avatar.jpg'
import botPmAvatar from '../../assets/bot-pm-avatar.jpg'
import botQaAvatar from '../../assets/bot-qa-avatar.jpg'
import botRequirementAvatar from '../../assets/bot-requirement-analysis-avatar.jpg'

// 角色机器人的头像与贴图角标：按机器人名称匹配，角标用 Lucide 图标 + 主题色。
// 名称对不上（改名或自建机器人）时没有头像，回落成 Lucide 机器人图标。
const BOT_META = {
  '需求分析助手': { avatar: botRequirementAvatar, icon: ClipboardCheck, accent: '#6366f1' },
  '产品经理': { avatar: botPmAvatar, icon: ClipboardList, accent: '#f59e0b' },
  '前端工程师': { avatar: botFrontendAvatar, icon: Code, accent: '#ec4899' },
  '后端工程师': { avatar: botBackendAvatar, icon: Server, accent: '#14b8a6' },
  'AI 工程师': { avatar: botAiAvatar, icon: Brain, accent: '#8b5cf6' },
  '运维工程师': { avatar: botDevopsAvatar, icon: Wrench, accent: '#f97316' },
  '测试工程师': { avatar: botQaAvatar, icon: Bug, accent: '#84cc16' },
}

export function useBots(ctx, skills) {
  const bots = ref([])
  const botBusy = ref(false)
  const showBotForm = ref(false)
  const botDraft = ref({ botId: '', name: '', instruction: '', skills: [], enabled: false })
  const selectedBotId = ref('')
  // CI 工作流开关：直接启停仓库里的 GitHub Actions 工作流，未配置凭据时如实显示。
  const ciWorkflow = ref({ configured: false, enabled: null, state: '', workflow: '', repository: '', message: '' })
  const ciBusy = ref(false)

  const selectedBot = computed(() => bots.value.find(bot => bot.bot_id === selectedBotId.value) || null)
  const skillNameMap = computed(() => new Map(skills.state.skills.map(skill => [skill.id, skill.name])))

  function botMeta(bot) {
    return BOT_META[bot?.name] || null
  }

  function botAvatar(bot) {
    return botMeta(bot)?.avatar || ''
  }

  // 角标与描边颜色走 CSS 变量，样式集中在 style.css。
  function botAccent(bot) {
    return botMeta(bot) ? { '--bot-accent': botMeta(bot).accent } : {}
  }

  async function refreshBots() {
    try {
      bots.value = await getBots(ctx.backendUrl)
    } catch (error) {
      bots.value = []
    }
    await refreshCiWorkflow()
    // 不自动选中：右侧详情只在用户点左侧列表项时出现。
    if (!bots.value.some(bot => bot.bot_id === selectedBotId.value)) {
      selectedBotId.value = ''
    }
  }

  async function refreshCiWorkflow() {
    try {
      ciWorkflow.value = await getCiWorkflow(ctx.backendUrl)
    } catch (error) {
      ciWorkflow.value = { configured: false, enabled: null, state: '', workflow: '', repository: '',
        message: error.message || 'CI 工作流服务不可用' }
    }
  }

  async function toggleCiWorkflow() {
    if (ciBusy.value || !ciWorkflow.value.configured) return
    ciBusy.value = true
    const next = !ciWorkflow.value.enabled
    try {
      ciWorkflow.value = await setCiWorkflow(ctx.backendUrl, next)
      ctx.showToast(next ? 'CI 工作流已开启' : 'CI 工作流已关闭')
    } catch (error) {
      ctx.showToast(`切换失败：${error.message || 'CI 工作流服务不可用'}`)
    } finally {
      ciBusy.value = false
    }
  }

  function selectBot(bot) {
    selectedBotId.value = bot.bot_id
  }

  // 技能名列表给详情页渲染成标签；botSkillNames 保留一行文本给列表摘要。
  function botSkillList(bot) {
    return (bot?.skills || []).map(id => skillNameMap.value.get(id) || id)
  }

  function botSkillNames(bot) {
    const ids = bot?.skills || []
    return ids.length ? ids.map(id => skillNameMap.value.get(id) || id).join('、') : '未绑定技能'
  }

  function openBotForm(bot) {
    botDraft.value = bot
      ? { botId: bot.bot_id, name: bot.name, instruction: bot.instruction || '', skills: [...(bot.skills || [])], enabled: bot.enabled }
      : { botId: '', name: '', instruction: '', skills: [], enabled: false }
    showBotForm.value = true
  }

  async function submitBot() {
    if (botBusy.value) return
    if (!botDraft.value.name.trim()) {
      ctx.showToast('请填写机器人名称')
      return
    }
    botBusy.value = true
    const payload = {
      name: botDraft.value.name.trim(),
      instruction: botDraft.value.instruction.trim(),
      skills: botDraft.value.skills,
      enabled: botDraft.value.enabled,
    }
    try {
      const saved = botDraft.value.botId
        ? await updateBot(ctx.backendUrl, botDraft.value.botId, payload)
        : await createBot(ctx.backendUrl, payload)
      showBotForm.value = false
      if (saved?.bot_id) selectedBotId.value = saved.bot_id
      await refreshBots()
      ctx.showToast('机器人已保存')
    } catch (error) {
      ctx.showToast(`保存失败：${error.message || '机器人服务不可用'}`)
    } finally {
      botBusy.value = false
    }
  }

  async function toggleBot(bot) {
    if (botBusy.value) return
    botBusy.value = true
    try {
      await updateBot(ctx.backendUrl, bot.bot_id, {
        name: bot.name,
        instruction: bot.instruction || '',
        skills: bot.skills || [],
        enabled: !bot.enabled,
      })
      await refreshBots()
      ctx.showToast(bot.enabled ? `已关闭 ${bot.name}` : `已开启 ${bot.name}，所有会话都会复用它`)
    } catch (error) {
      ctx.showToast(`更新失败：${error.message || '机器人服务不可用'}`)
    } finally {
      botBusy.value = false
    }
  }

  async function removeBot(bot) {
    if (!window.confirm(`删除机器人 ${bot.name}？`)) return
    try {
      await deleteBot(ctx.backendUrl, bot.bot_id)
      if (selectedBotId.value === bot.bot_id) selectedBotId.value = ''
      await refreshBots()
      ctx.showToast(`已删除 ${bot.name}`)
    } catch (error) {
      ctx.showToast(`删除失败：${error.message || '机器人服务不可用'}`)
    }
  }

  const state = reactive({ bots, botBusy, showBotForm, botDraft, selectedBotId, selectedBot, ciWorkflow, ciBusy })

  const actions = {
    refreshBots, selectBot, botSkillNames, botSkillList, openBotForm, submitBot, toggleBot, removeBot,
    botMeta, botAvatar, botAccent, refreshCiWorkflow, toggleCiWorkflow,
  }

  return { state, actions }
}
