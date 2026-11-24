import { computed, reactive, ref } from 'vue'
import {
  compensateDocuments, getDocumentPreview, getDocumentVersions, getDocuments,
  removeDocument, uploadDocument, vectorizeDocument,
} from '../../api'
import { downloadHref as makeDownloadHref } from '../app/format'

const DOC_STATUS = {
  PENDING: '待转换', CONVERTING: '解析中', CONVERTED: '已转换',
  VECTORIZING: '向量化中', VECTORIZED: '已向量化', FAILED: '失败',
}

export function useDocuments(ctx) {
  const showDocs = ref(false)
  const docs = ref([])
  const docBusy = ref(false)
  const docMessage = ref(null)
  const deletingDoc = ref(null)
  const expandingDoc = ref(null)
  const docVersions = ref({})
  const showDocPreview = ref(false)
  const previewDoc = ref(null)
  const docPreview = ref(null)
  const docPreviewBusy = ref(false)
  const docPreviewError = ref('')
  const docPreviewTab = ref('chunks')
  let docPollTimer = null

  const docCounts = computed(() => {
    const counts = { waiting: 0, vectorized: 0, failed: 0 }
    for (const doc of docs.value) {
      if (doc.status === 'VECTORIZED') counts.vectorized += 1
      else if (doc.status === 'FAILED') counts.failed += 1
      else if (['PENDING', 'CONVERTING', 'CONVERTED', 'VECTORIZING'].includes(doc.status)) counts.waiting += 1
    }
    return counts
  })

  function docStatusLabel(status) {
    return DOC_STATUS[status] || status || '未知'
  }

  function docStatusClass(status) {
    if (status === 'FAILED') return 'bad'
    if (status === 'VECTORIZED') return 'on'
    if (['CONVERTING', 'VECTORIZING'].includes(status)) return 'working'
    return ''
  }

  function stopDocPolling() {
    clearTimeout(docPollTimer)
    docPollTimer = null
  }

  function scheduleDocPolling() {
    stopDocPolling()
    if (!showDocs.value || !docs.value.some((doc) => ['CONVERTING', 'VECTORIZING'].includes(doc.status))) return
    docPollTimer = setTimeout(() => refreshDocs(), 1400)
  }

  async function refreshDocs() {
    try {
      docs.value = await getDocuments(ctx.backendUrl)
    } catch (error) {
      docMessage.value = { type: 'error', text: `读取文档列表失败：${error.message}` }
    } finally {
      scheduleDocPolling()
    }
  }

  async function openDocs() {
    showDocs.value = true
    docMessage.value = null
    await refreshDocs()
  }

  function closeDocs() {
    showDocs.value = false
    docBusy.value = false
    stopDocPolling()
  }

  async function openDocPreview(doc) {
    showDocs.value = false
    stopDocPolling()
    previewDoc.value = doc
    docPreview.value = null
    docPreviewError.value = ''
    docPreviewTab.value = 'chunks'
    showDocPreview.value = true
    docPreviewBusy.value = true
    try {
      docPreview.value = await getDocumentPreview(ctx.backendUrl, doc.fileId)
    } catch (error) {
      docPreviewError.value = error.message || '读取预览失败'
    } finally {
      docPreviewBusy.value = false
    }
  }

  function closeDocPreview(returnToDocs = true) {
    showDocPreview.value = false
    previewDoc.value = null
    docPreview.value = null
    docPreviewError.value = ''
    if (returnToDocs) {
      showDocs.value = true
      refreshDocs()
    }
  }

  async function submitDocument(file) {
    docBusy.value = true
    docMessage.value = { type: 'info', text: `正在转换「${file.name}」… PDF/Word 要走 MinerU 解析，可能需要几分钟` }
    try {
      const record = await uploadDocument(ctx.backendUrl, file)
      const notes = record.errorMsg ? `；${record.errorMsg}` : ''
      docMessage.value = {
        type: 'ok',
        text: `「${record.fileName}」已转换为 Markdown：${record.imageCount} 张图已托管，${record.captionCount} 张有描述${notes}`,
      }
      await refreshDocs()
    } catch (error) {
      docMessage.value = { type: 'error', text: `转换失败：${error.message}` }
    } finally {
      docBusy.value = false
    }
  }

  function chooseDocFile(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (file) submitDocument(file)
  }

  async function runVectorize(doc) {
    docBusy.value = true
    docMessage.value = { type: 'info', text: `正在对「${doc.fileName}」做父子分段并向量化…` }
    try {
      const result = await vectorizeDocument(ctx.backendUrl, doc.fileId)
      if (result.alreadyVectorized) {
        docMessage.value = { type: 'ok', text: `「${doc.fileName}」已经完成向量化，无需重复操作` }
        await refreshDocs()
        return
      }
      if (result.inProgress) {
        docMessage.value = { type: 'info', text: `「${doc.fileName}」正在向量化，请稍后` }
        await refreshDocs()
        return
      }
      docMessage.value = { type: 'ok', text: `已向量化：${result.children} 个子分段（其中 ${result.parents} 个父分段存库不向量化）` }
      await refreshDocs()
    } catch (error) {
      docMessage.value = { type: 'error', text: `向量化失败：${error.message}` }
    } finally {
      docBusy.value = false
    }
  }

  async function runCompensation() {
    docBusy.value = true
    try {
      const outcomes = await compensateDocuments(ctx.backendUrl)
      docMessage.value = { type: 'ok', text: outcomes.length ? `兜底补偿检查了 ${outcomes.length} 个待处理文档` : '没有需要补偿的文档' }
      await refreshDocs()
    } catch (error) {
      docMessage.value = { type: 'error', text: `补偿失败：${error.message}` }
    } finally {
      docBusy.value = false
    }
  }

  async function toggleDocVersions(doc) {
    if (expandingDoc.value === doc.fileId) {
      expandingDoc.value = null
      return
    }
    expandingDoc.value = doc.fileId
    if (docVersions.value[doc.fileId]) return
    try {
      docVersions.value = { ...docVersions.value, [doc.fileId]: await getDocumentVersions(ctx.backendUrl, doc.fileId) }
    } catch (error) {
      docMessage.value = { type: 'error', text: `读取版本失败：${error.message}` }
    }
  }

  async function confirmRemoveDoc(doc) {
    try {
      await removeDocument(ctx.backendUrl, doc.fileId)
      deletingDoc.value = null
      docMessage.value = { type: 'ok', text: `「${doc.fileName}」已删除` }
      await refreshDocs()
    } catch (error) {
      docMessage.value = { type: 'error', text: `删除失败：${error.message}` }
    }
  }

  function downloadHref(file) {
    return makeDownloadHref(ctx.backendUrl, file)
  }

  const state = reactive({
    showDocs, docs, docBusy, docMessage, deletingDoc, expandingDoc, docVersions,
    showDocPreview, previewDoc, docPreview, docPreviewBusy, docPreviewError, docPreviewTab,
    docCounts,
  })

  const actions = {
    refreshDocs, openDocs, closeDocs, openDocPreview, closeDocPreview,
    submitDocument, chooseDocFile, runVectorize, runCompensation,
    toggleDocVersions, confirmRemoveDoc, docStatusLabel, docStatusClass, downloadHref,
  }

  return { state, actions }
}
