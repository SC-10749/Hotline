import { computed, reactive, ref } from 'vue'
import { getSkills, removeSkill, setSkillEnabled, uploadSkill } from '../../api'

export function useSkills(ctx) {
  const showSkills = ref(false)
  const skills = ref([])
  const skillBusy = ref(false)
  const skillMessage = ref(null)
  const skillEntries = ref([])
  const skillEntryChoice = ref('')
  const deletingSkill = ref(null)
  let pendingSkillFile = null

  const enabledSkills = computed(() => skills.value.filter((skill) => skill.enabled))

  async function refreshSkills() {
    try {
      skills.value = await getSkills(ctx.backendUrl)
    } catch (error) {
      skills.value = []
      skillMessage.value = { type: 'error', text: `技能列表加载失败：${error.message}` }
    }
  }

  // 首屏静默拉一次技能列表：失败不打扰用户。
  async function loadSkillsSilently() {
    try {
      skills.value = await getSkills(ctx.backendUrl)
    } catch {
      // 首屏加载失败保持空列表即可
    }
  }

  function clearSkillEntry() {
    skillEntries.value = []
    skillEntryChoice.value = ''
    pendingSkillFile = null
  }

  function openSkills() {
    showSkills.value = true
    skillMessage.value = null
    clearSkillEntry()
    refreshSkills()
  }

  function closeSkills() {
    showSkills.value = false
    skillMessage.value = null
    clearSkillEntry()
  }

  async function installSkill(file, entry) {
    skillBusy.value = true
    skillMessage.value = null
    try {
      const result = await uploadSkill(ctx.backendUrl, file, entry)
      if (result.success) {
        clearSkillEntry()
        skillMessage.value = { type: 'ok', text: `技能「${result.skill.name}」已安装并启用` }
        await refreshSkills()
      } else {
        skillMessage.value = { type: 'error', text: result.message }
        skillEntries.value = result.entries
        skillEntryChoice.value = ''
        pendingSkillFile = file
      }
    } catch (error) {
      skillMessage.value = { type: 'error', text: `上传失败：${error.message}` }
    } finally {
      skillBusy.value = false
    }
  }

  function chooseSkillZip(event) {
    const file = event.target.files[0]
    event.target.value = ''
    if (file) installSkill(file, '')
  }

  function confirmSkillEntry() {
    if (pendingSkillFile && skillEntryChoice.value) installSkill(pendingSkillFile, skillEntryChoice.value)
  }

  async function toggleSkill(skill) {
    try {
      await setSkillEnabled(ctx.backendUrl, skill.id, !skill.enabled)
      await refreshSkills()
    } catch (error) {
      skillMessage.value = { type: 'error', text: `操作失败：${error.message}` }
    }
  }

  async function confirmRemoveSkill(skill) {
    try {
      await removeSkill(ctx.backendUrl, skill.id)
      deletingSkill.value = null
      skillMessage.value = { type: 'ok', text: `技能「${skill.name}」已删除` }
      await refreshSkills()
    } catch (error) {
      skillMessage.value = { type: 'error', text: `删除失败：${error.message}` }
    }
  }

  async function togglePlugin(skill) {
    try {
      await setSkillEnabled(ctx.backendUrl, skill.id, !skill.enabled)
      await refreshSkills()
      ctx.showToast(skill.enabled ? `已停用 ${skill.name}` : `已启用 ${skill.name}`)
    } catch (error) {
      ctx.showToast(`操作失败：${error.message || '技能服务不可用'}`)
    }
  }

  async function removePlugin(skill) {
    if (!window.confirm(`删除技能包 ${skill.name}？`)) return
    try {
      await removeSkill(ctx.backendUrl, skill.id)
      await refreshSkills()
      ctx.showToast(`已删除 ${skill.name}`)
    } catch (error) {
      ctx.showToast(`删除失败：${error.message || '技能服务不可用'}`)
    }
  }

  const state = reactive({
    showSkills, skills, skillBusy, skillMessage, skillEntries, skillEntryChoice, deletingSkill, enabledSkills,
  })

  const actions = {
    refreshSkills, loadSkillsSilently, clearSkillEntry, openSkills, closeSkills,
    installSkill, chooseSkillZip, confirmSkillEntry, toggleSkill, confirmRemoveSkill,
    togglePlugin, removePlugin,
  }

  return { state, actions }
}
