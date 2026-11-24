// Agent 实例：目录、版本对比、启停与技能绑定。
import { computed, ref } from 'vue'
import { getHarnessAgent, updateHarnessAgent } from '../../api'
import { getHarnessAgents, createHarnessAgent, setHarnessAgentStatus, bindHarnessAgentSkills, unbindHarnessAgentSkill, getHarnessAgentVersions, getHarnessAgentDiff, getHarnessAgentRuns } from '../../api'

export function useAgents({ props, notify }) {
  const harnessAgents = ref([])
  const agentsConnected = ref(false)
  const agentsError = ref('')
  const showAgentDialog = ref(false)
  const editingAgent = ref(null)
  const agentSaving = ref(false)
  const agentError = ref('')
  const agentPolicyText = ref('{}')
  const agentStatusBusy = ref('')
  const agentVersions = ref([])
  const agentVersionsBusy = ref(false)
  const agentDiffBase = ref('')
  const agentDiffTarget = ref('')
  const agentDiff = ref(null)
  const agentDiffBusy = ref(false)
  const agentDiffError = ref('')
  const agentRuns = ref([])
  const agentRunsBusy = ref(false)
  const agentRunsError = ref('')
  const agentSkillPick = ref('')
  const agentSkillInput = ref('')
  const agentSkillBusy = ref(false)
  const agentSkillError = ref('')
  const agentDraft = ref({ name: '', description: '', version: 'v1', model: 'auto' })
  const agentRows = computed(() => harnessAgents.value)
  async function refreshAgentData() {
    try {
      const result = await getHarnessAgents(props.apiBase)
      harnessAgents.value = result.items
      agentsConnected.value = true
      agentsError.value = ''
    } catch (error) {
      agentsError.value = error.message || 'Agent 服务暂不可用'
    }
  }

  function openAgentDialog() {
    editingAgent.value = null
    agentPolicyText.value = '{}'
    agentError.value = ''
    agentDraft.value = { name: '', description: '', version: 'v1', model: 'auto' }
    showAgentDialog.value = true
  }

  async function openAgentDetails(row) {
    if (row.agent_id.startsWith('demo-')) return notify('演示 Agent 仅供查看，请连接资源服务后编辑真实配置')
    try {
      const result = await getHarnessAgent(props.apiBase, row.agent_id)
      const agent = result.agent
      const rawPolicy = typeof agent.policy === 'string' ? (agent.policy || '{}') : agent.policy
      let policy = {}
      try { policy = rawPolicy ? JSON.parse(rawPolicy) : {} } catch { policy = {} }
      if (!policy || Array.isArray(policy) || typeof policy !== 'object') policy = {}
      editingAgent.value = agent
      agentDraft.value = { name: agent.name, description: agent.description, version: agent.version, model: agent.model }
      agentPolicyText.value = JSON.stringify(policy, null, 2)
      agentError.value = ''
      agentSkillError.value = ''
      agentSkillInput.value = ''
      agentSkillPick.value = ''
      showAgentDialog.value = true
      await Promise.all([loadAgentVersions(agent.agent_id), loadAgentRuns(agent.agent_id)])
    } catch (error) { notify(`读取 Agent 失败：${error.message}`) }
  }

  async function toggleAgentStatus(row) {
    if (agentStatusBusy.value) return
    agentStatusBusy.value = row.agent_id
    try {
      const result = await setHarnessAgentStatus(props.apiBase, row.agent_id, !row.enabled)
      harnessAgents.value = harnessAgents.value.map(item => item.agent_id === result.agent.agent_id ? result.agent : item)
      if (editingAgent.value?.agent_id === result.agent.agent_id) editingAgent.value = result.agent
      notify(result.agent.enabled ? 'Agent 已启用' : 'Agent 已停用')
    } catch (error) {
      notify(`Agent 启停失败：${error.message || '资源服务不可用'}`)
    } finally {
      agentStatusBusy.value = ''
    }
  }

  async function loadAgentVersions(agentId) {
    agentVersionsBusy.value = true
    try {
      const result = await getHarnessAgentVersions(props.apiBase, agentId)
      agentVersions.value = result.items || []
      agentDiffTarget.value = agentVersions.value[0]?.version_id || ''
      agentDiffBase.value = agentVersions.value[1]?.version_id || agentVersions.value[0]?.version_id || ''
      agentDiff.value = null
      agentDiffError.value = ''
    } catch (error) {
      agentVersions.value = []
      agentDiffError.value = error.message || '版本历史读取失败'
    } finally {
      agentVersionsBusy.value = false
    }
  }

  function formatDiffValue(value) {
    if (value == null) return '—'
    if (typeof value === 'object') return JSON.stringify(value)
    return String(value)
  }

  async function compareAgentVersions() {
    if (!agentDiffBase.value || !agentDiffTarget.value) { agentDiffError.value = '请选择两个版本快照'; return }
    agentDiffBusy.value = true
    try {
      agentDiff.value = await getHarnessAgentDiff(props.apiBase, editingAgent.value.agent_id, agentDiffBase.value, agentDiffTarget.value)
      agentDiffError.value = ''
    } catch (error) {
      agentDiff.value = null
      agentDiffError.value = error.message || '版本比较失败'
    } finally {
      agentDiffBusy.value = false
    }
  }

  async function loadAgentRuns(agentId) {
    agentRunsBusy.value = true
    try {
      const result = await getHarnessAgentRuns(props.apiBase, agentId)
      agentRuns.value = result.items || []
      agentRunsError.value = ''
    } catch (error) {
      agentRuns.value = []
      agentRunsError.value = error.message || '关联运行读取失败'
    } finally {
      agentRunsBusy.value = false
    }
  }
  const pendingAgentSkillId = computed(() => agentSkillInput.value.trim() || agentSkillPick.value)
  async function bindAgentSkill() {
    const skillId = pendingAgentSkillId.value
    if (!skillId) { agentSkillError.value = '请选择或输入要绑定的 skillId'; return }
    const current = [...(editingAgent.value?.skills || [])]
    if (current.includes(skillId)) { agentSkillError.value = '该 Skill 已绑定'; return }
    agentSkillBusy.value = true
    try {
      const result = await bindHarnessAgentSkills(props.apiBase, editingAgent.value.agent_id, [...current, skillId])
      editingAgent.value = result.agent
      harnessAgents.value = harnessAgents.value.map(item => item.agent_id === result.agent.agent_id ? result.agent : item)
      agentSkillInput.value = ''
      agentSkillPick.value = ''
      agentSkillError.value = ''
      notify(`已绑定 Skill ${skillId}`)
    } catch (error) {
      agentSkillError.value = error.message || 'Skill 绑定失败'
    } finally {
      agentSkillBusy.value = false
    }
  }

  async function unbindAgentSkill(skillId) {
    agentSkillBusy.value = true
    try {
      const result = await unbindHarnessAgentSkill(props.apiBase, editingAgent.value.agent_id, skillId)
      editingAgent.value = result.agent
      harnessAgents.value = harnessAgents.value.map(item => item.agent_id === result.agent.agent_id ? result.agent : item)
      agentSkillError.value = ''
      notify(`已解绑 Skill ${skillId}`)
    } catch (error) {
      agentSkillError.value = error.message || 'Skill 解绑失败'
    } finally {
      agentSkillBusy.value = false
    }
  }

  async function submitAgent() {
    if (agentSaving.value) return
    agentError.value = ''
    let policy
    try {
      policy = JSON.parse(agentPolicyText.value)
      if (!policy || Array.isArray(policy) || typeof policy !== 'object') throw new Error()
    } catch {
      agentError.value = '运行策略必须是 JSON 对象'
      return
    }
    if (![agentDraft.value.name, agentDraft.value.version, agentDraft.value.model].every(value => value.trim())) {
      agentError.value = '请填写名称、版本和模型路由'
      return
    }
    agentSaving.value = true
    try {
      const payload = { ...agentDraft.value, policy }
      const result = editingAgent.value
        ? await updateHarnessAgent(props.apiBase, editingAgent.value.agent_id, { ...payload, revision: editingAgent.value.revision })
        : await createHarnessAgent(props.apiBase, payload)
      harnessAgents.value = [result.agent, ...harnessAgents.value.filter(item => item.agent_id !== result.agent.agent_id)]
      agentsConnected.value = true
      agentsError.value = ''
      showAgentDialog.value = false
      notify(editingAgent.value ? 'Agent 配置已保存' : 'Agent 已创建')
    } catch (error) {
      agentError.value = error.message || '保存失败，请重试'
    } finally { agentSaving.value = false }
  }


  return {
    agentDiff,
    agentDiffBase,
    agentDiffBusy,
    agentDiffError,
    agentDiffTarget,
    agentDraft,
    agentError,
    agentPolicyText,
    agentRows,
    agentRuns,
    agentRunsBusy,
    agentRunsError,
    agentSaving,
    agentSkillBusy,
    agentSkillError,
    agentSkillInput,
    agentSkillPick,
    agentStatusBusy,
    agentVersions,
    agentVersionsBusy,
    agentsConnected,
    agentsError,
    bindAgentSkill,
    compareAgentVersions,
    editingAgent,
    formatDiffValue,
    harnessAgents,
    openAgentDetails,
    openAgentDialog,
    pendingAgentSkillId,
    refreshAgentData,
    showAgentDialog,
    submitAgent,
    toggleAgentStatus,
    unbindAgentSkill,
  }
}
