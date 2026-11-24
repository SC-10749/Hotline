// 工具与 MCP：工具登记、MCP 连接器与连通性测试。
import { computed, ref } from 'vue'
import { getHarnessTool, createHarnessTool, updateHarnessTool } from '../../api'
import { callMcpTool } from '../../api'
import { getHarnessTools, getHarnessMcpServers, testHarnessTool } from '../../api'

export function useTools({ props, notify }) {
  const harnessTools = ref([])
  const toolsConnected = ref(false)
  const toolsError = ref('')
  const showToolDialog = ref(false)
  const editingTool = ref(null)
  const toolSaving = ref(false)
  const toolError = ref('')
  const toolTestBusy = ref('')
  const toolTestResults = ref({})
  const harnessMcpServers = ref([])
  const mcpServersError = ref('')
  const toolDraft = ref({ name: '', source: 'mcp', scope: 'workspace', risk: 'low', status: 'configured', description: '', approval_policy: 'risk-based' })
  const toolSchemaText = ref('{"type":"object","properties":{}}')
  const mcpToolPick = ref('')
  const mcpCallArgs = ref('{}')
  const mcpCallResult = ref(null)
  const mcpCallBusy = ref(false)
  const mcpCallError = ref('')
  const toolRows = computed(() => harnessTools.value)
  async function callSelectedMcpTool() {
    if (!mcpToolPick.value) { mcpCallError.value = '请选择要调用的工具'; return }
    let args = {}
    try { args = mcpCallArgs.value.trim() ? JSON.parse(mcpCallArgs.value) : {} }
    catch { mcpCallError.value = '调用参数不是合法 JSON'; return }
    const [toolId, toolName] = mcpToolPick.value.split('::')
    mcpCallBusy.value = true
    mcpCallError.value = ''
    mcpCallResult.value = null
    try {
      mcpCallResult.value = await callMcpTool(props.apiBase, toolId, toolName, args)
    } catch (error) { mcpCallError.value = error.message || '工具调用失败' }
    finally { mcpCallBusy.value = false }
  }

  async function refreshToolData() {
    try {
      const result = await getHarnessTools(props.apiBase)
      harnessTools.value = result.items
      toolsConnected.value = true
      toolsError.value = ''
    } catch (error) { toolsError.value = error.message || '工具目录暂不可用' }
    try {
      const result = await getHarnessMcpServers(props.apiBase)
      harnessMcpServers.value = result.items || []
      mcpServersError.value = ''
    } catch (error) {
      harnessMcpServers.value = []
      mcpServersError.value = error.message || 'MCP 连接器读取失败'
    }
  }

  async function testToolConnection(row) {
    if (toolTestBusy.value) return
    toolTestBusy.value = row.tool_id
    try {
      const result = await testHarnessTool(props.apiBase, row.tool_id)
      toolTestResults.value = { ...toolTestResults.value, [row.tool_id]: result }
      notify(result.ok ? `${row.name}：连接正常` : `${row.name}：连接失败，${result.message || '后端未返回原因'}`)
    } catch (error) {
      toolTestResults.value = { ...toolTestResults.value, [row.tool_id]: { ok: false, message: error.message || '连接测试失败' } }
      notify(`连接测试失败：${error.message}`)
    } finally {
      toolTestBusy.value = ''
    }
  }

  function openToolDialog() {
    editingTool.value = null
    toolDraft.value = { name: '', source: 'mcp', scope: 'workspace', risk: 'low', status: 'configured', description: '', approval_policy: 'risk-based' }
    toolSchemaText.value = JSON.stringify({ type: 'object', properties: {} }, null, 2)
    toolError.value = ''
    showToolDialog.value = true
  }

  async function openToolDetails(row) {
    if (row.tool_id.startsWith('demo-')) return notify('请连接工具目录后查看真实记录')
    try {
      const { tool } = await getHarnessTool(props.apiBase, row.tool_id)
      editingTool.value = tool
      toolDraft.value = { name: tool.name, source: tool.source, scope: tool.scope, risk: tool.risk, status: tool.status, description: tool.description, approval_policy: tool.approval_policy }
      toolSchemaText.value = JSON.stringify(tool.input_schema, null, 2)
      toolError.value = ''
      showToolDialog.value = true
    } catch (error) { notify(`读取工具失败：${error.message}`) }
  }

  async function saveTool() {
    if (toolSaving.value) return
    toolError.value = ''
    let schema
    try {
      schema = JSON.parse(toolSchemaText.value)
      if (!schema || Array.isArray(schema) || schema.type !== 'object') throw new Error()
    } catch {
      toolError.value = '参数 Schema 必须是根 type 为 object 的 JSON 对象'
      return
    }
    if (![toolDraft.value.name, toolDraft.value.source, toolDraft.value.scope, toolDraft.value.status].every(value => value.trim())) {
      toolError.value = '请填写名称、来源、范围和状态'
      return
    }
    toolSaving.value = true
    try {
      const payload = { ...toolDraft.value, input_schema: schema }
      const result = editingTool.value
        ? await updateHarnessTool(props.apiBase, editingTool.value.tool_id, { ...payload, revision: editingTool.value.revision })
        : await createHarnessTool(props.apiBase, payload)
      harnessTools.value = [result.tool, ...harnessTools.value.filter(item => item.tool_id !== result.tool.tool_id)]
      toolsConnected.value = true
      toolsError.value = ''
      showToolDialog.value = false
      notify('工具登记配置已保存')
    } catch (error) { toolError.value = error.message || '保存失败，请重试' }
    finally { toolSaving.value = false }
  }


  return {
    callSelectedMcpTool,
    editingTool,
    harnessMcpServers,
    harnessTools,
    mcpCallArgs,
    mcpCallBusy,
    mcpCallError,
    mcpCallResult,
    mcpServersError,
    mcpToolPick,
    openToolDetails,
    openToolDialog,
    refreshToolData,
    saveTool,
    showToolDialog,
    testToolConnection,
    toolDraft,
    toolError,
    toolRows,
    toolSaving,
    toolSchemaText,
    toolTestBusy,
    toolTestResults,
    toolsConnected,
    toolsError,
  }
}
