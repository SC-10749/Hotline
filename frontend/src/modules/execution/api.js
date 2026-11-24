import { unwrap, apiUrl } from '../../core/http.js'
import { apiFetch } from '../auth/token.js'

export async function getExecutionRuns(base, params = {}) {
  const query = new URLSearchParams()
  if (params.status) query.set('status', params.status)
  if (params.search) query.set('search', params.search)
  if (params.limit) query.set('limit', String(params.limit))
  if (params.offset) query.set('offset', String(params.offset))
  const suffix = query.toString() ? `?${query}` : ''
  const response = await apiFetch(apiUrl(base, `/execution/runs${suffix}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function createExecutionRun(base, payload) {
  const response = await apiFetch(apiUrl(base, '/execution/runs'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function createParallelRuns(base, payload) {
  return unwrap(await apiFetch(apiUrl(base, '/execution/runs/parallel'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }))
}

export function parallelStreamUrl(base, runIds) {
  return apiUrl(base, `/execution/parallel/stream?runIds=${encodeURIComponent(runIds.join(','))}`)
}

export async function getExecutionRun(base, runId) {
  const response = await apiFetch(apiUrl(base, `/execution/runs/${encodeURIComponent(runId)}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getExecutionEvents(base, runId, after = 0) {
  const response = await apiFetch(apiUrl(base, `/execution/runs/${encodeURIComponent(runId)}/events?after=${after}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export function executionEventsUrl(base, runId, after = 0) {
  return apiUrl(base, `/execution/runs/${encodeURIComponent(runId)}/stream?after=${after}`)
}

export async function cancelExecutionRun(base, runId) {
  const response = await apiFetch(apiUrl(base, `/execution/runs/${encodeURIComponent(runId)}/cancel`), {
    method: 'POST',
    signal: AbortSignal.timeout(8000),
  })
  return unwrap(response)
}

export async function retryExecutionRun(base, runId) {
  const response = await apiFetch(apiUrl(base, `/execution/runs/${encodeURIComponent(runId)}/retry`), {
    method: 'POST', signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}
