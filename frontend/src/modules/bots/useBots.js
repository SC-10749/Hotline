import { computed, reactive, ref } from 'vue'
import { Brain, Bug, ClipboardCheck, ClipboardList, Code, Server, Wrench } from 'lucide-vue-next'
import { createBot, deleteBot, getBots, updateBot } from '../../api'
import botRequirementAvatar from '../../assets/bot-requirement-analysis-avatar.jpg'

// 角色机器人的头像与贴图角标：按机器人名称匹配，角标用 Lucide 图标 + 主题色。
// 只有正在使用的角色才有头像图片；其余角色保留角标与配色，没有头像时回落成 Lucide 机器人图标。
const BOT_META = {
  '需求分析助手': { avatar: botRequirementAvatar, icon: ClipboardCheck, accent: '#6366f1' },
  '产品经理': { icon: ClipboardList, accent: '#f59e0b' },
  '前端工程师': { icon: Code, accent: '#ec4899' },
  '后端工程师': { icon: Server, accent: '#14b8a6' },
  'AI 工程师': { icon: Brain, accent: '#8b5cf6' },
  '运维工程师': { icon: Wrench, accent: '#f97316' },
  '测试工程师': { icon: Bug, accent: '#84cc16' },
}

export function useBots(ctx, skills) {
  const bots = ref([])
  const botBusy = ref(false)
  const showBotForm = ref(false)
  const botDraft = ref({ botId: '', name: '', instruction: '', skills: [], enabled: false })
  const selectedBotId = ref('')

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
    // 不自动选中：右侧详情只在用户点左侧列表项时出现。
    if (!bots.value.some(bot => bot.bot_id === selectedBotId.value)) {
      selectedBotId.value = ''
    }
  }

  function selectBot(bot) {
    selectedBotId.value = bot.bot_id
  }

  function botSkillNames(bot) {
    const ids = bot?.skills || []
    return ids.length ? ids.map(id => skillNameMap.value.get(id) || id).join('、') : '未绑定'
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

  const state = reactive({ bots, botBusy, showBotForm, botDraft, selectedBotId, selectedBot })

  const actions = {
    refreshBots, selectBot, botSkillNames, openBotForm, submitBot, toggleBot, removeBot,
    botMeta, botAvatar, botAccent,
  }

  return { state, actions }
}
