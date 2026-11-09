import { computed, onScopeDispose, ref, watch } from 'vue'
import { executionEventsUrl, getExecutionEvents } from '../../api'

export function useRunEvents(selectedRun, apiBase) {
  const items = ref([])
  const loading = ref(false)
  const error = ref('')
  const streamState = ref('idle')
  let generation = 0
  let stream
  let cursor = 0

  function closeStream() {
    stream?.close()
    stream = undefined
  }

  function append(batch) {
    const added = batch.filter(item => item.event_id > cursor)
      .sort((a, b) => a.event_id - b.event_id)
    for (const item of added) {
      if (item.event_id <= cursor) continue
      items.value.push(item)
      cursor = item.event_id
    }
  }

  function connect(runId, base, request) {
    const source = new EventSource(executionEventsUrl(base, runId, cursor))
    stream = source
    streamState.value = 'connecting'
    source.onopen = () => {
      if (request !== generation || stream !== source) return
      streamState.value = 'live'
      error.value = ''
    }
    source.onmessage = message => {
      if (request !== generation || stream !== source) return
      try {
        append([JSON.parse(message.data)])
      } catch {
        error.value = '运行事件格式无效，请刷新事件'
        streamState.value = 'failed'
        closeStream()
      }
    }
    source.addEventListener('done', () => {
      if (request !== generation || stream !== source) return
      streamState.value = 'complete'
      error.value = ''
      closeStream()
    })
    source.onerror = () => {
      if (request !== generation || stream !== source) return
      const closed = source.readyState === EventSource.CLOSED
      streamState.value = closed ? 'failed' : 'reconnecting'
      error.value = closed ? '事件连接已关闭，请刷新事件重试' : '事件连接中断，正在从上次游标重连'
    }
  }

  async function refresh() {
    const runId = selectedRun.value?.id
    const request = ++generation
    const base = apiBase()
    closeStream()
    if (!runId) return
    loading.value = true
    error.value = ''
    try {
      const result = await getExecutionEvents(base, runId, cursor)
      if (request !== generation) return
      append(result.items || [])
    } catch (failure) {
      if (request === generation) error.value = failure.message || '运行事件读取失败'
    } finally {
      if (request === generation) {
        loading.value = false
        connect(runId, base, request)
      }
    }
  }

  watch([() => selectedRun.value?.id, apiBase], () => {
    generation += 1
    closeStream()
    cursor = 0
    items.value = []
    loading.value = false
    error.value = ''
    streamState.value = 'idle'
    refresh()
  }, { flush: 'sync', immediate: true })
  onScopeDispose(() => { generation += 1; closeStream() })

  const output = computed(() => items.value
    .filter(item => item.event?.type === 'text')
    .map(item => typeof item.event.content === 'string' ? item.event.content : '')
    .join(''))

  return { items, loading, error, output, streamState, refresh }
}
