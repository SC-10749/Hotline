// 模型路由：模型登记、备用链与连通性测试。
import { computed, ref } from 'vue'
import { getHarnessModel, createHarnessModel, updateHarnessModel } from '../../api'
import { getModelFallbackChain } from '../../api'
import { getHarnessModels, testHarnessModel } from '../../api'

export function useModels({ props, notify }) {
  const harnessModels = ref([])
  const modelsConnected = ref(false)
  const modelsError = ref('')
  const showModelDialog = ref(false)
  const editingModel = ref(null)
  const modelSaving = ref(false)
  const modelError = ref('')
  const modelTestBusy = ref('')
  const modelTestResults = ref({})
  const modelFallbackChain = ref([])
  const modelDraft = ref({ name: '', provider: '', route: 'default', status: 'configured', cost_policy: '', fallback_model_id: null })
  const modelRows = computed(() => harnessModels.value)
  async function refreshModelData() {
    try {
      const result = await getHarnessModels(props.apiBase)
      harnessModels.value = result.items
      modelsConnected.value = true
      modelsError.value = ''
    } catch (error) { modelsError.value = error.message || '模型路由目录暂不可用' }
  }

  async function testModelConnection(row) {
    if (modelTestBusy.value) return
    modelTestBusy.value = row.model_id
    try {
      const result = await testHarnessModel(props.apiBase, row.model_id)
      modelTestResults.value = { ...modelTestResults.value, [row.model_id]: result }
      notify(result.ok ? `${row.name}：连接正常` : `${row.name}：连接失败，${result.message || '后端未返回原因'}`)
    } catch (error) {
      modelTestResults.value = { ...modelTestResults.value, [row.model_id]: { ok: false, message: error.message || '连接测试失败' } }
      notify(`连接测试失败：${error.message}`)
    } finally {
      modelTestBusy.value = ''
    }
  }

  function openModelDialog() {
    editingModel.value = null
    modelDraft.value = { name: '', provider: '', route: 'default', status: 'configured', cost_policy: '', fallback_model_id: null }
    modelError.value = ''
    modelFallbackChain.value = []
    showModelDialog.value = true
  }

  async function loadModelFallbackChain(modelId) {
    if (!modelId) { modelFallbackChain.value = []; return }
    try {
      const result = await getModelFallbackChain(props.apiBase, modelId)
      modelFallbackChain.value = result.chain || []
    } catch (error) {
      modelFallbackChain.value = []
    }
  }

  async function openModelDetails(row) {
    if (row.model_id.startsWith('demo-')) return notify('请连接模型目录后查看真实记录')
    try {
      const { model } = await getHarnessModel(props.apiBase, row.model_id)
      editingModel.value = model
      modelDraft.value = { name: model.name, provider: model.provider, route: model.route, status: model.status, cost_policy: model.cost_policy, fallback_model_id: model.fallback_model_id }
      modelError.value = ''
      showModelDialog.value = true
      await loadModelFallbackChain(model.model_id)
    } catch (error) { notify(`读取模型路由失败：${error.message}`) }
  }

  async function saveModel() {
    if (modelSaving.value) return
    modelError.value = ''
    if (![modelDraft.value.name, modelDraft.value.route, modelDraft.value.status].every(value => value.trim())) {
      modelError.value = '请填写模型名称、路由用途和登记状态'
      return
    }
    modelSaving.value = true
    try {
      const payload = { ...modelDraft.value }
      const result = editingModel.value
        ? await updateHarnessModel(props.apiBase, editingModel.value.model_id, { ...payload, revision: editingModel.value.revision })
        : await createHarnessModel(props.apiBase, payload)
      harnessModels.value = [result.model, ...harnessModels.value.filter(item => item.model_id !== result.model.model_id)]
      modelsConnected.value = true
      modelsError.value = ''
      showModelDialog.value = false
      notify('模型路由登记信息已保存')
    } catch (error) { modelError.value = error.message || '保存失败，请重试' }
    finally { modelSaving.value = false }
  }


  return {
    editingModel,
    harnessModels,
    modelDraft,
    modelError,
    modelFallbackChain,
    modelRows,
    modelSaving,
    modelTestBusy,
    modelTestResults,
    modelsConnected,
    modelsError,
    openModelDetails,
    openModelDialog,
    refreshModelData,
    saveModel,
    showModelDialog,
    testModelConnection,
  }
}
