const unwrap = async (response) => {
  let payload
  try {
    payload = await response.json()
  } catch {
    throw new Error(`服务返回了无法识别的数据（HTTP ${response.status}）`)
  }
  if (!response.ok || (payload?.code && payload.code !== 200)) {
    const validationMessage = Array.isArray(payload?.detail) ? payload.detail.map(item => item.msg).join('；') : ''
    throw new Error(payload?.message || (typeof payload?.detail === 'string' ? payload.detail : validationMessage) || `请求失败（HTTP ${response.status}）`)
  }
  return payload?.data ?? payload
}

export const apiUrl = (base, path) => `${base.replace(/\/+$/, '')}${path}`

export async function getCodeMapStatus(base) {
  const response = await fetch(apiUrl(base, '/code-map'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

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

export async function getSchedules(base) {
  const response = await fetch(apiUrl(base, '/harness/schedules'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function createSchedule(base, payload) {
  const response = await fetch(apiUrl(base, '/harness/schedules'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function updateSchedule(base, taskId, payload) {
  const response = await fetch(apiUrl(base, `/harness/schedules/${encodeURIComponent(taskId)}`), {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function deleteSchedule(base, taskId) {
  const response = await fetch(apiUrl(base, `/harness/schedules/${encodeURIComponent(taskId)}`), {
    method: 'DELETE', signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function runSchedule(base, taskId) {
  const response = await fetch(apiUrl(base, `/harness/schedules/${encodeURIComponent(taskId)}/run`), {
    method: 'POST', signal: AbortSignal.timeout(30000),
  })
  return unwrap(response)
}
export async function getHarnessOverview(base) {
  const response = await fetch(apiUrl(base, '/harness/overview'), { signal: AbortSignal.timeout(8000) })
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

export function executionEventsUrl(base, runId, after = 0) {
  return apiUrl(base, `/execution/runs/${encodeURIComponent(runId)}/stream?after=${after}`)
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

export async function deleteEvaluationDataset(base, datasetId) {
  const response = await fetch(apiUrl(base, `/evaluation/datasets/${encodeURIComponent(datasetId)}`), {
    method: 'DELETE', signal: AbortSignal.timeout(8000),
  })
  return unwrap(response)
}

export async function deleteEvaluationCase(base, datasetId, caseId) {
  const response = await fetch(apiUrl(base, `/evaluation/datasets/${encodeURIComponent(datasetId)}/cases/${encodeURIComponent(caseId)}`), {
    method: 'DELETE', signal: AbortSignal.timeout(8000),
  })
  return unwrap(response)
}

export async function importEvaluationCases(base, datasetId, cases) {
  const response = await fetch(apiUrl(base, `/evaluation/datasets/${encodeURIComponent(datasetId)}/cases/batch`), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ cases }),
    signal: AbortSignal.timeout(30000),
  })
  return unwrap(response)
}

export async function createEvaluationSnapshot(base, datasetId) {
  const response = await fetch(apiUrl(base, `/evaluation/datasets/${encodeURIComponent(datasetId)}/snapshots`), {
    method: 'POST', signal: AbortSignal.timeout(8000),
  })
  return unwrap(response)
}

export async function getEvaluationSnapshots(base, datasetId) {
  const response = await fetch(apiUrl(base, `/evaluation/datasets/${encodeURIComponent(datasetId)}/snapshots`), {
    signal: AbortSignal.timeout(8000),
  })
  return unwrap(response)
}

export async function getEvaluationRun(base, evalRunId) {
  const response = await fetch(apiUrl(base, `/evaluation/runs/${encodeURIComponent(evalRunId)}`), {
    signal: AbortSignal.timeout(8000),
  })
  return unwrap(response)
}

export async function replayEvaluationRun(base, evalRunId, caseIds = []) {
  const response = await fetch(apiUrl(base, `/evaluation/runs/${encodeURIComponent(evalRunId)}/replay`), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ caseIds }),
    signal: AbortSignal.timeout(30000),
  })
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

export async function getReleaseRecords(base) {
  const response = await fetch(apiUrl(base, '/release/records'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function advanceRollout(base, payload) {
  const response = await fetch(apiUrl(base, '/release/rollouts/advance'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function getReleaseConfig(base) {
  const response = await fetch(apiUrl(base, '/release/config'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function saveReleaseConfig(base, payload) {
  const response = await fetch(apiUrl(base, '/release/config'), {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function getReleaseGateThresholds(base) {
  const response = await fetch(apiUrl(base, '/release/gate-thresholds'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function saveReleaseGateThresholds(base, payload) {
  const response = await fetch(apiUrl(base, '/release/gate-thresholds'), {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    signal: AbortSignal.timeout(15000),
  })
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

export async function getHarnessAgent(base, agentId) {
  const response = await fetch(apiUrl(base, `/harness/agents/${encodeURIComponent(agentId)}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function updateHarnessAgent(base, agentId, payload) {
  const response = await fetch(apiUrl(base, `/harness/agents/${encodeURIComponent(agentId)}`), {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function createHarnessAgent(base, payload) {
  const response = await fetch(apiUrl(base, '/harness/agents'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000) })
  return unwrap(response)
}

export async function setHarnessAgentStatus(base, agentId, enabled) {
  const response = await fetch(apiUrl(base, `/harness/agents/${encodeURIComponent(agentId)}/status`), {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled }),
    signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function bindHarnessAgentSkills(base, agentId, skillIds) {
  const response = await fetch(apiUrl(base, `/harness/agents/${encodeURIComponent(agentId)}/skills`), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ skillIds }),
    signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function unbindHarnessAgentSkill(base, agentId, skillId) {
  const response = await fetch(apiUrl(base, `/harness/agents/${encodeURIComponent(agentId)}/skills/${encodeURIComponent(skillId)}`), {
    method: 'DELETE', signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function getHarnessAgentVersions(base, agentId) {
  const response = await fetch(apiUrl(base, `/harness/agents/${encodeURIComponent(agentId)}/versions`), {
    signal: AbortSignal.timeout(8000),
  })
  return unwrap(response)
}

export async function getHarnessAgentDiff(base, agentId, baseVersion, targetVersion) {
  const query = new URLSearchParams({ base: baseVersion, target: targetVersion })
  const response = await fetch(apiUrl(base, `/harness/agents/${encodeURIComponent(agentId)}/diff?${query}`), {
    signal: AbortSignal.timeout(8000),
  })
  return unwrap(response)
}

export async function getHarnessAgentRuns(base, agentId) {
  const response = await fetch(apiUrl(base, `/harness/agents/${encodeURIComponent(agentId)}/runs`), {
    signal: AbortSignal.timeout(8000),
  })
  return unwrap(response)
}

export async function getHarnessWorkspaceRuns(base, workspaceId) {
  const response = await fetch(apiUrl(base, `/harness/workspaces/${encodeURIComponent(workspaceId)}/runs`), {
    signal: AbortSignal.timeout(8000),
  })
  return unwrap(response)
}

export async function createHarnessWorkspaceSnapshot(base, workspaceId) {
  const response = await fetch(apiUrl(base, `/harness/workspaces/${encodeURIComponent(workspaceId)}/snapshots`), {
    method: 'POST', signal: AbortSignal.timeout(30000),
  })
  return unwrap(response)
}

export async function getHarnessWorkspaceSnapshots(base, workspaceId) {
  const response = await fetch(apiUrl(base, `/harness/workspaces/${encodeURIComponent(workspaceId)}/snapshots`), {
    signal: AbortSignal.timeout(8000),
  })
  return unwrap(response)
}

export async function getHarnessWorkspaceChanges(base, workspaceId, snapshotId) {
  const response = await fetch(apiUrl(base, `/harness/workspaces/${encodeURIComponent(workspaceId)}/snapshots/${encodeURIComponent(snapshotId)}/changes`), {
    signal: AbortSignal.timeout(8000),
  })
  return unwrap(response)
}

export async function getHarnessWorkspaces(base) {
  const response = await fetch(apiUrl(base, '/harness/workspaces'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getHarnessWorkspace(base, workspaceId) {
  const response = await fetch(apiUrl(base, `/harness/workspaces/${encodeURIComponent(workspaceId)}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getWorkspaceFiles(base, workspaceId) {
  const response = await fetch(apiUrl(base, `/harness/workspaces/${encodeURIComponent(workspaceId)}/files`), {
    signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function updateHarnessWorkspace(base, workspaceId, payload) {
  const response = await fetch(apiUrl(base, `/harness/workspaces/${encodeURIComponent(workspaceId)}`), {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000),
  })
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

export async function getHarnessTool(base, toolId) {
  const response = await fetch(apiUrl(base, `/harness/tools/${encodeURIComponent(toolId)}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function createHarnessTool(base, payload) {
  const response = await fetch(apiUrl(base, '/harness/tools'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function updateHarnessTool(base, toolId, payload) {
  const response = await fetch(apiUrl(base, `/harness/tools/${encodeURIComponent(toolId)}`), {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function testHarnessTool(base, toolId) {
  const response = await fetch(apiUrl(base, `/harness/tools/${encodeURIComponent(toolId)}/test`), {
    method: 'POST', signal: AbortSignal.timeout(20000),
  })
  return unwrap(response)
}

export async function getHarnessMcpServers(base) {
  const response = await fetch(apiUrl(base, '/harness/mcp/servers'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function testHarnessModel(base, modelId) {
  const response = await fetch(apiUrl(base, `/harness/models/${encodeURIComponent(modelId)}/test`), {
    method: 'POST', signal: AbortSignal.timeout(20000),
  })
  return unwrap(response)
}

export async function getModelFallbackChain(base, modelId) {
  const response = await fetch(apiUrl(base, `/harness/models/${encodeURIComponent(modelId)}/fallback-chain`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getHarnessModels(base) {
  const response = await fetch(apiUrl(base, '/harness/models'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getHarnessModel(base, modelId) {
  const response = await fetch(apiUrl(base, `/harness/models/${encodeURIComponent(modelId)}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function createHarnessModel(base, payload) {
  const response = await fetch(apiUrl(base, '/harness/models'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function updateHarnessModel(base, modelId, payload) {
  const response = await fetch(apiUrl(base, `/harness/models/${encodeURIComponent(modelId)}`), {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000),
  })
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

export async function getHarnessApproval(base, requestId) {
  const response = await fetch(apiUrl(base, `/harness/approvals/${encodeURIComponent(requestId)}`), {
    signal: AbortSignal.timeout(8000),
  })
  return unwrap(response)
}

export async function decideHarnessApprovalsBatch(base, payload) {
  const response = await fetch(apiUrl(base, '/harness/approvals/decide-batch'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export function harnessApprovalAuditUrl(base) {
  return apiUrl(base, '/harness/approvals/audit')
}

export async function getMachineErrors(base, workerId) {
  const response = await fetch(apiUrl(base, `/harness/machines/${encodeURIComponent(workerId)}/errors`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function drainHarnessMachine(base, workerId, draining) {
  const response = await fetch(apiUrl(base, `/harness/machines/${encodeURIComponent(workerId)}/drain`), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ draining }),
    signal: AbortSignal.timeout(8000),
  })
  return unwrap(response)
}

export async function decideHarnessApproval(base, requestId, payload) {
  const response = await fetch(apiUrl(base, `/harness/approvals/${encodeURIComponent(requestId)}/decision`), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000) })
  return unwrap(response)
}

export async function getHarnessArtifacts(base, runId, { limit = 25, offset = 0, owner = '' } = {}) {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (runId) query.set('runId', runId)
  if (owner) query.set('owner', owner)
  const response = await fetch(apiUrl(base, `/harness/artifacts?${query}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

// 归属身份走请求头，后端按产物登记的 owner 校验；owner 为空的旧产物仍然放行。
const ownerHeaders = (owner) => (owner ? { 'X-Harness-Owner': owner } : {})

export async function downloadHarnessArtifact(base, artifactId, owner = '') {
  const response = await fetch(apiUrl(base, `/harness/artifacts/${encodeURIComponent(artifactId)}/download`), {
    headers: ownerHeaders(owner),
    signal: AbortSignal.timeout(60000),
  })
  if (!response.ok) await unwrap(response)
  return response.blob()
}

export async function getHarnessArtifactPreview(base, artifactId, owner = '') {
  const response = await fetch(apiUrl(base, `/harness/artifacts/${encodeURIComponent(artifactId)}/preview`), {
    headers: ownerHeaders(owner),
    signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function cleanupHarnessArtifacts(base, payload) {
  const response = await fetch(apiUrl(base, '/harness/artifacts/cleanup'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    signal: AbortSignal.timeout(30000),
  })
  return unwrap(response)
}

export async function getHarnessObservabilityRuns(base) {
  const response = await fetch(apiUrl(base, '/harness/observability/runs'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getHarnessTrace(base, runId, { after = 0, level = '', tool = '', hasError = false, since = '', until = '', type = '' } = {}) {
  const query = new URLSearchParams({ after: String(after) })
  if (level) query.set('level', level)
  if (tool) query.set('tool', tool)
  if (hasError) query.set('hasError', 'true')
  if (since) query.set('since', since)
  if (until) query.set('until', until)
  if (type) query.set('type', type)
  const response = await fetch(apiUrl(base, `/harness/observability/runs/${encodeURIComponent(runId)}/events?${query}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getHarnessObservabilityMetrics(base) {
  const response = await fetch(apiUrl(base, '/harness/observability/metrics'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export function harnessTraceExportUrl(base, runId) {
  return apiUrl(base, `/harness/observability/runs/${encodeURIComponent(runId)}/export`)
}

export async function getApprovalNotifications(base, { requestId = '', limit = 50 } = {}) {
  const query = new URLSearchParams({ limit: String(limit) })
  if (requestId) query.set('requestId', requestId)
  const response = await fetch(apiUrl(base, `/harness/approvals/notifications?${query}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function compareEvaluationRuns(base, baseRunId, targetRunId) {
  const query = new URLSearchParams({ base: baseRunId, target: targetRunId })
  const response = await fetch(apiUrl(base, `/evaluation/runs/compare?${query}`), { signal: AbortSignal.timeout(15000) })
  return unwrap(response)
}

export async function downloadEvaluationRun(base, evalRunId, format = 'csv') {
  const response = await fetch(apiUrl(base, `/evaluation/runs/${encodeURIComponent(evalRunId)}/export?format=${format}`), {
    signal: AbortSignal.timeout(30000),
  })
  if (!response.ok) await unwrap(response)
  return response.blob()
}

export async function getReleaseObservations(base, { project = '', limit = 50 } = {}) {
  const query = new URLSearchParams({ limit: String(limit) })
  if (project) query.set('project', project)
  const response = await fetch(apiUrl(base, `/release/observations?${query}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function observeReleaseRollout(base, payload) {
  const response = await fetch(apiUrl(base, '/release/rollouts/observe'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(20000),
  })
  return unwrap(response)
}

export async function getObservabilityExports(base, { from = '', to = '', runId = '', format = 'json', limit = 1000 } = {}) {
  const query = new URLSearchParams({ format: String(format), limit: String(limit) })
  if (from) query.set('from', from)
  if (to) query.set('to', to)
  if (runId) query.set('runId', runId)
  const response = await fetch(apiUrl(base, `/harness/observability/exports?${query}`), { signal: AbortSignal.timeout(30000) })
  if (format === 'csv') {
    if (!response.ok) await unwrap(response)
    return { blob: await response.blob(), total: Number(response.headers.get('X-Harness-Total') || 0), truncated: response.headers.get('X-Harness-Truncated') === 'true' }
  }
  return unwrap(response)
}

export async function getObservabilityTrends(base, { bucket = 'hour', limit = 24 } = {}) {
  const query = new URLSearchParams({ bucket, limit: String(limit) })
  const response = await fetch(apiUrl(base, `/harness/observability/trends?${query}`), { signal: AbortSignal.timeout(15000) })
  return unwrap(response)
}

export async function getWorkspaceCheckout(base, workspaceId) {
  const response = await fetch(apiUrl(base, `/harness/workspaces/${encodeURIComponent(workspaceId)}/checkout`), {
    signal: AbortSignal.timeout(8000),
  })
  return unwrap(response)
}

export async function checkoutWorkspace(base, workspaceId) {
  const response = await fetch(apiUrl(base, `/harness/workspaces/${encodeURIComponent(workspaceId)}/checkout`), {
    method: 'POST',
    signal: AbortSignal.timeout(120000),
  })
  return unwrap(response)
}

export async function bindCatalogSkill(base, payload) {
  const response = await fetch(apiUrl(base, '/harness/skills/catalog/bind'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function unbindCatalogSkill(base, payload) {
  const response = await fetch(apiUrl(base, '/harness/skills/catalog/bind'), {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function callMcpTool(base, toolId, toolName, args = {}) {
  const response = await fetch(apiUrl(base, `/harness/mcp/servers/${encodeURIComponent(toolId)}/tools/${encodeURIComponent(toolName)}/call`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ arguments: args }),
    signal: AbortSignal.timeout(60000),
  })
  return unwrap(response)
}

export async function getHarnessSettings(base) {
  const response = await fetch(apiUrl(base, '/harness/settings'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function saveHarnessSettings(base, payload) {
  const response = await fetch(apiUrl(base, '/harness/settings'), { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000) })
  return unwrap(response)
}

export async function getSkills(base) {
  const response = await fetch(apiUrl(base, '/skill/list'), { signal: AbortSignal.timeout(8000) })
  const result = await unwrap(response)
  return result?.skills || []
}

export async function getSkillDetail(base, skillId) {
  const response = await fetch(apiUrl(base, `/skill/${encodeURIComponent(skillId)}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getCatalogSkills(base) {
  const response = await fetch(apiUrl(base, '/harness/skills/catalog'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getCatalogVersion(base, name, version) {
  const query = new URLSearchParams({ name, version })
  const response = await fetch(apiUrl(base, `/harness/skills/catalog/version?${query}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function compareCatalogVersions(base, name, baseVersion, version) {
  const query = new URLSearchParams({ name, baseVersion, version })
  const response = await fetch(apiUrl(base, `/harness/skills/catalog/compare?${query}`), { signal: AbortSignal.timeout(15000) })
  return unwrap(response)
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

export function streamUrl(base, mode, query, conversationId, fileId, workspaceId = '') {
  // A skill run must keep its skill even when a file is attached.
  const route = mode === 'skills'
    ? '/agent/skills/stream'
    : (fileId ? '/agent/file/stream' : ({ chat: '/agent/chat/stream', ppt: '/agent/pptx/stream', deep: '/agent/deep/stream' }[mode] || '/agent/chat/stream'))
  const params = new URLSearchParams({ query, conversationId })
  if (fileId) params.set('fileId', fileId)
  if (workspaceId) params.set('workspaceId', workspaceId)
  return `${apiUrl(base, route)}?${params}`
}

export async function importWorkspace(base, name, entries) {
  const form = new FormData()
  form.append('name', name)
  for (const entry of entries) {
    const path = entry.path.replaceAll('\\', '/').split('/').slice(1).join('/') || entry.name
    form.append('files', entry.file, path)
  }
  const response = await fetch(apiUrl(base, '/harness/workspaces/import'), {
    method: 'POST', body: form, signal: AbortSignal.timeout(120000),
  })
  return unwrap(response)
}

export async function getBots(base) {
  const response = await fetch(apiUrl(base, '/harness/bots'), { signal: AbortSignal.timeout(8000) })
  const result = await unwrap(response)
  return result?.items || []
}

export async function createBot(base, payload) {
  const response = await fetch(apiUrl(base, '/harness/bots'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    signal: AbortSignal.timeout(15000),
  })
  const result = await unwrap(response)
  return result?.bot
}

export async function updateBot(base, botId, payload) {
  const response = await fetch(apiUrl(base, `/harness/bots/${encodeURIComponent(botId)}`), {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    signal: AbortSignal.timeout(15000),
  })
  const result = await unwrap(response)
  return result?.bot
}

export async function deleteBot(base, botId) {
  const response = await fetch(apiUrl(base, `/harness/bots/${encodeURIComponent(botId)}`), {
    method: 'DELETE', signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function bindBotSession(base, botId, conversationId) {
  const response = await fetch(apiUrl(base, `/harness/bots/${encodeURIComponent(botId)}/sessions`), {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conversationId }), signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function getProfile(base) {
  const response = await fetch(apiUrl(base, '/harness/profile'), { signal: AbortSignal.timeout(8000) })
  const result = await unwrap(response)
  return result?.profile || {}
}

export async function saveProfile(base, payload) {
  const response = await fetch(apiUrl(base, '/harness/profile'), {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    signal: AbortSignal.timeout(15000),
  })
  const result = await unwrap(response)
  return result?.profile || {}
}

export async function getCredential(base) {
  const response = await fetch(apiUrl(base, '/harness/profile/credentials'), { signal: AbortSignal.timeout(8000) })
  const result = await unwrap(response)
  return result?.credential || null
}

export async function saveCredential(base, payload) {
  const response = await fetch(apiUrl(base, '/harness/profile/credentials'), {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    signal: AbortSignal.timeout(15000),
  })
  const result = await unwrap(response)
  return result?.credential || null
}

export async function deleteCredential(base) {
  const response = await fetch(apiUrl(base, '/harness/profile/credentials'), {
    method: 'DELETE', signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function testCredential(base, payload) {
  const response = await fetch(apiUrl(base, '/harness/profile/credentials/test'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    signal: AbortSignal.timeout(60000),
  })
  return unwrap(response)
}
