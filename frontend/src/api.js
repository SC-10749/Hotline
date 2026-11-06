const unwrap = async (response) => {
  let payload
  try {
    payload = await response.json()
  } catch {
    throw new Error(`服务返回了无法识别的数据（HTTP ${response.status}）`)
  }
  if (!response.ok || (payload?.code && payload.code !== 200)) {
    throw new Error(payload?.message || `请求失败（HTTP ${response.status}）`)
  }
  return payload?.data ?? payload
}

export const apiUrl = (base, path) => `${base.replace(/\/+$/, '')}${path}`

export async function getSessions(base) {
  const response = await fetch(apiUrl(base, '/session/list?pageNum=1&pageSize=100'), { signal: AbortSignal.timeout(8000) })
  const result = await unwrap(response)
  return result?.records || []
}

export async function getAllSessions(base) {
  const pageSize = 1000
  const records = []
  let pageNum = 1
  let total = Infinity
  while (records.length < total) {
    const response = await fetch(apiUrl(base, `/session/list?pageNum=${pageNum}&pageSize=${pageSize}`), { signal: AbortSignal.timeout(15000) })
    const result = await unwrap(response)
    const page = result?.records || []
    records.push(...page)
    total = Number(result?.total ?? records.length)
    if (page.length < pageSize || page.length === 0) break
    pageNum += 1
  }
  return records
}

export async function getSession(base, id) {
  const response = await fetch(apiUrl(base, `/session/${encodeURIComponent(id)}`))
  return unwrap(response)
}

export async function removeSession(base, id) {
  const response = await fetch(apiUrl(base, `/session/${encodeURIComponent(id)}`), { method: 'DELETE' })
  return unwrap(response)
}

export async function uploadFile(base, file, filename) {
  const body = new FormData()
  body.append('file', file, filename || file.name)
  const response = await fetch(apiUrl(base, '/file/upload'), { method: 'POST', body })
  const result = await unwrap(response)
  if (!result?.fileId) throw new Error('上传成功，但服务未返回文件编号')
  return result
}

export async function testBackend(base) {
  const response = await fetch(apiUrl(base, '/health'), { signal: AbortSignal.timeout(8000) })
  await unwrap(response)
  return true
}

export async function stopAgent(base, id) {
  const response = await fetch(apiUrl(base, `/agent/stop?conversationId=${encodeURIComponent(id)}`))
  return unwrap(response)
}

export async function getExecutionRuns(base, params = {}) {
  const query = new URLSearchParams()
  if (params.status) query.set('status', params.status)
  if (params.search) query.set('search', params.search)
  if (params.limit) query.set('limit', String(params.limit))
  if (params.offset) query.set('offset', String(params.offset))
  const suffix = query.toString() ? `?${query}` : ''
  const response = await fetch(apiUrl(base, `/execution/runs${suffix}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function createExecutionRun(base, payload) {
  const response = await fetch(apiUrl(base, '/execution/runs'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function getExecutionRun(base, runId) {
  const response = await fetch(apiUrl(base, `/execution/runs/${encodeURIComponent(runId)}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getExecutionEvents(base, runId, after = 0) {
  const response = await fetch(apiUrl(base, `/execution/runs/${encodeURIComponent(runId)}/events?after=${after}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function cancelExecutionRun(base, runId) {
  const response = await fetch(apiUrl(base, `/execution/runs/${encodeURIComponent(runId)}/cancel`), {
    method: 'POST',
    signal: AbortSignal.timeout(8000),
  })
  return unwrap(response)
}

export async function retryExecutionRun(base, runId) {
  const response = await fetch(apiUrl(base, `/execution/runs/${encodeURIComponent(runId)}/retry`), {
    method: 'POST', signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function getEvaluationDatasets(base) {
  const response = await fetch(apiUrl(base, '/evaluation/datasets'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function createEvaluationDataset(base, payload) {
  const response = await fetch(apiUrl(base, '/evaluation/datasets'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function getEvaluationDataset(base, datasetId) {
  const response = await fetch(apiUrl(base, `/evaluation/datasets/${encodeURIComponent(datasetId)}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function addEvaluationCase(base, datasetId, payload) {
  const response = await fetch(apiUrl(base, `/evaluation/datasets/${encodeURIComponent(datasetId)}/cases`), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000) })
  return unwrap(response)
}

export async function updateEvaluationCase(base, datasetId, caseId, payload) {
  const response = await fetch(apiUrl(base, `/evaluation/datasets/${encodeURIComponent(datasetId)}/cases/${encodeURIComponent(caseId)}`), { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000) })
  return unwrap(response)
}

export async function getEvaluationConfig(base) {
  const response = await fetch(apiUrl(base, '/evaluation/config'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function saveEvaluationConfig(base, payload) {
  const response = await fetch(apiUrl(base, '/evaluation/config'), {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function createEvaluationRun(base, payload) {
  const response = await fetch(apiUrl(base, '/evaluation/runs'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function getEvaluationRuns(base) {
  const response = await fetch(apiUrl(base, '/evaluation/runs'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getReleaseSummary(base) {
  const response = await fetch(apiUrl(base, '/release/summary'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function promoteRelease(base, payload) {
  const response = await fetch(apiUrl(base, '/release/promote'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function evaluateReleaseGate(base, payload) {
  const response = await fetch(apiUrl(base, '/release/gate'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000) })
  return unwrap(response)
}

export async function getReleaseGates(base) {
  const response = await fetch(apiUrl(base, '/release/gates'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function rollbackRelease(base, payload) {
  const response = await fetch(apiUrl(base, '/release/rollback'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function getHarnessAgents(base) {
  const response = await fetch(apiUrl(base, '/harness/agents'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function createHarnessAgent(base, payload) {
  const response = await fetch(apiUrl(base, '/harness/agents'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000) })
  return unwrap(response)
}

export async function getHarnessWorkspaces(base) {
  const response = await fetch(apiUrl(base, '/harness/workspaces'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function createHarnessWorkspace(base, payload) {
  const response = await fetch(apiUrl(base, '/harness/workspaces'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000) })
  return unwrap(response)
}

export async function getHarnessTools(base) {
  const response = await fetch(apiUrl(base, '/harness/tools'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getHarnessModels(base) {
  const response = await fetch(apiUrl(base, '/harness/models'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getHarnessMachines(base) {
  const response = await fetch(apiUrl(base, '/harness/machines'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getHarnessApprovals(base, status) {
  const suffix = status ? `?status=${encodeURIComponent(status)}` : ''
  const response = await fetch(apiUrl(base, `/harness/approvals${suffix}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function decideHarnessApproval(base, requestId, payload) {
  const response = await fetch(apiUrl(base, `/harness/approvals/${encodeURIComponent(requestId)}/decision`), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000) })
  return unwrap(response)
}

export async function getHarnessArtifacts(base, runId) {
  const suffix = runId ? `?runId=${encodeURIComponent(runId)}` : ''
  const response = await fetch(apiUrl(base, `/harness/artifacts${suffix}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getHarnessObservabilityRuns(base) {
  const response = await fetch(apiUrl(base, '/harness/observability/runs'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getHarnessTrace(base, runId, after = 0) {
  const response = await fetch(apiUrl(base, `/harness/observability/runs/${encodeURIComponent(runId)}/events?after=${after}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getSkills(base) {
  const response = await fetch(apiUrl(base, '/skill/list'), { signal: AbortSignal.timeout(8000) })
  const result = await unwrap(response)
  return result?.skills || []
}

// The backend answers 400 with the archive's file list when SKILL.md is ambiguous,
// so this one cannot go through unwrap().
export async function uploadSkill(base, file, entry) {
  const body = new FormData()
  body.append('file', file)
  if (entry) body.append('entry', entry)
  const response = await fetch(apiUrl(base, '/skill/upload'), { method: 'POST', body })
  const payload = await response.json().catch(() => null)
  if (payload?.code === 200 && payload.data?.id) return { success: true, skill: payload.data }
  return {
    success: false,
    message: payload?.message || `上传失败（HTTP ${response.status}）`,
    entries: payload?.data?.entries || [],
  }
}

export async function setSkillEnabled(base, id, enabled) {
  const response = await fetch(apiUrl(base, `/skill/${encodeURIComponent(id)}/toggle?enabled=${enabled}`), { method: 'POST' })
  return unwrap(response)
}

export async function removeSkill(base, id) {
  const response = await fetch(apiUrl(base, `/skill/${encodeURIComponent(id)}`), { method: 'DELETE' })
  return unwrap(response)
}

export async function getDocuments(base) {
  const response = await fetch(apiUrl(base, '/document/list'), { signal: AbortSignal.timeout(8000) })
  const result = await unwrap(response)
  return result?.documents || []
}

// MinerU converts asynchronously and a large PDF can queue for minutes, so this
// must not carry the short timeout the list endpoints use.
export async function uploadDocument(base, file) {
  const body = new FormData()
  body.append('file', file)
  const response = await fetch(apiUrl(base, '/document/upload'), {
    method: 'POST', body, signal: AbortSignal.timeout(960000),
  })
  return unwrap(response)
}

export async function vectorizeDocument(base, id) {
  const response = await fetch(apiUrl(base, `/document/${encodeURIComponent(id)}/vectorize`), {
    method: 'POST', signal: AbortSignal.timeout(300000),
  })
  return unwrap(response)
}

export async function getDocumentPreview(base, id) {
  const response = await fetch(apiUrl(base, `/document/${encodeURIComponent(id)}/preview`), {
    signal: AbortSignal.timeout(30000),
  })
  return unwrap(response)
}

export async function compensateDocuments(base) {
  const response = await fetch(apiUrl(base, '/document/compensate'), { method: 'POST', signal: AbortSignal.timeout(300000) })
  return unwrap(response)
}

export async function getDocumentVersions(base, id) {
  const response = await fetch(apiUrl(base, `/document/${encodeURIComponent(id)}/versions`))
  const result = await unwrap(response)
  return Array.isArray(result) ? result : []
}

export async function removeDocument(base, id) {
  const response = await fetch(apiUrl(base, `/document/${encodeURIComponent(id)}`), { method: 'DELETE' })
  return unwrap(response)
}

export function streamUrl(base, mode, query, conversationId, fileId) {
  // A skill run must keep its skill even when a file is attached.
  const route = mode === 'skills'
    ? '/agent/skills/stream'
    : (fileId ? '/agent/file/stream' : ({ chat: '/agent/chat/stream', ppt: '/agent/pptx/stream', deep: '/agent/deep/stream' }[mode] || '/agent/chat/stream'))
  const params = new URLSearchParams({ query, conversationId })
  if (fileId) params.set('fileId', fileId)
  return `${apiUrl(base, route)}?${params}`
}
