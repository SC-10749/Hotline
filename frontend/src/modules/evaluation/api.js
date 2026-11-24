import { unwrap, apiUrl } from '../../core/http.js'
import { apiFetch } from '../auth/token.js'

export async function getBenchmarkTools(base) {
  return unwrap(await apiFetch(apiUrl(base, '/evaluation/benchmarks/tools'), { signal: AbortSignal.timeout(20000) }))
}

export async function getBenchmarkRuns(base, kind) {
  return unwrap(await apiFetch(apiUrl(base, `/evaluation/benchmarks/runs?kind=${encodeURIComponent(kind)}`)))
}

export async function startBenchmark(base, payload) {
  return unwrap(await apiFetch(apiUrl(base, '/evaluation/benchmarks/runs'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }))
}

export async function getBenchmarkRun(base, id) {
  return unwrap(await apiFetch(apiUrl(base, `/evaluation/benchmarks/runs/${encodeURIComponent(id)}`)))
}

export async function cancelBenchmark(base, id, keepalive = false) {
  return unwrap(await apiFetch(apiUrl(base, `/evaluation/benchmarks/runs/${encodeURIComponent(id)}/cancel`), {
    method: 'POST', keepalive,
  }))
}

export async function getEvaluationSemanticMetrics(base) {
  const response = await apiFetch(apiUrl(base, '/evaluation/semantic-metrics'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getEvaluationDatasets(base) {
  const response = await apiFetch(apiUrl(base, '/evaluation/datasets'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function createEvaluationDataset(base, payload) {
  const response = await apiFetch(apiUrl(base, '/evaluation/datasets'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function getEvaluationDataset(base, datasetId) {
  const response = await apiFetch(apiUrl(base, `/evaluation/datasets/${encodeURIComponent(datasetId)}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function addEvaluationCase(base, datasetId, payload) {
  const response = await apiFetch(apiUrl(base, `/evaluation/datasets/${encodeURIComponent(datasetId)}/cases`), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000) })
  return unwrap(response)
}

export async function updateEvaluationCase(base, datasetId, caseId, payload) {
  const response = await apiFetch(apiUrl(base, `/evaluation/datasets/${encodeURIComponent(datasetId)}/cases/${encodeURIComponent(caseId)}`), { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000) })
  return unwrap(response)
}

export async function deleteEvaluationDataset(base, datasetId) {
  const response = await apiFetch(apiUrl(base, `/evaluation/datasets/${encodeURIComponent(datasetId)}`), {
    method: 'DELETE', signal: AbortSignal.timeout(8000),
  })
  return unwrap(response)
}

export async function deleteEvaluationCase(base, datasetId, caseId) {
  const response = await apiFetch(apiUrl(base, `/evaluation/datasets/${encodeURIComponent(datasetId)}/cases/${encodeURIComponent(caseId)}`), {
    method: 'DELETE', signal: AbortSignal.timeout(8000),
  })
  return unwrap(response)
}

export async function importEvaluationCases(base, datasetId, cases) {
  const response = await apiFetch(apiUrl(base, `/evaluation/datasets/${encodeURIComponent(datasetId)}/cases/batch`), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ cases }),
    signal: AbortSignal.timeout(30000),
  })
  return unwrap(response)
}

export async function createEvaluationSnapshot(base, datasetId) {
  const response = await apiFetch(apiUrl(base, `/evaluation/datasets/${encodeURIComponent(datasetId)}/snapshots`), {
    method: 'POST', signal: AbortSignal.timeout(8000),
  })
  return unwrap(response)
}

export async function getEvaluationSnapshots(base, datasetId) {
  const response = await apiFetch(apiUrl(base, `/evaluation/datasets/${encodeURIComponent(datasetId)}/snapshots`), {
    signal: AbortSignal.timeout(8000),
  })
  return unwrap(response)
}

export async function getEvaluationRun(base, evalRunId) {
  const response = await apiFetch(apiUrl(base, `/evaluation/runs/${encodeURIComponent(evalRunId)}`), {
    signal: AbortSignal.timeout(8000),
  })
  return unwrap(response)
}

export async function replayEvaluationRun(base, evalRunId, caseIds = []) {
  const response = await apiFetch(apiUrl(base, `/evaluation/runs/${encodeURIComponent(evalRunId)}/replay`), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ caseIds }),
    signal: AbortSignal.timeout(30000),
  })
  return unwrap(response)
}

export async function getEvaluationConfig(base) {
  const response = await apiFetch(apiUrl(base, '/evaluation/config'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function saveEvaluationConfig(base, payload) {
  const response = await apiFetch(apiUrl(base, '/evaluation/config'), {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function createEvaluationRun(base, payload) {
  const response = await apiFetch(apiUrl(base, '/evaluation/runs'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function getEvaluationRuns(base) {
  const response = await apiFetch(apiUrl(base, '/evaluation/runs'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function compareEvaluationRuns(base, baseRunId, targetRunId) {
  const query = new URLSearchParams({ base: baseRunId, target: targetRunId })
  const response = await apiFetch(apiUrl(base, `/evaluation/runs/compare?${query}`), { signal: AbortSignal.timeout(15000) })
  return unwrap(response)
}

export async function getEvaluationMatrix(base, runIds = []) {
  const query = new URLSearchParams({ runs: runIds.join(',') })
  const response = await apiFetch(apiUrl(base, `/evaluation/runs/matrix?${query}`), { signal: AbortSignal.timeout(15000) })
  return unwrap(response)
}

export async function downloadEvaluationRun(base, evalRunId, format = 'csv') {
  const response = await apiFetch(apiUrl(base, `/evaluation/runs/${encodeURIComponent(evalRunId)}/export?format=${format}`), {
    signal: AbortSignal.timeout(30000),
  })
  if (!response.ok) await unwrap(response)
  return response.blob()
}

export async function getEvaluationTrace(base, runId, caseId, epoch) {
  const query = `caseId=${encodeURIComponent(caseId)}&epoch=${encodeURIComponent(epoch)}`
  const response = await apiFetch(apiUrl(base, `/evaluation/runs/${encodeURIComponent(runId)}/trace?${query}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function checkEvaluationGates(base, payload) {
  const response = await apiFetch(apiUrl(base, '/evaluation/gates/check'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000)
  })
  return unwrap(response)
}
