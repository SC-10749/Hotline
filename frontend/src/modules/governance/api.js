import { unwrap, apiUrl } from '../../core/http.js'
import { apiFetch } from '../auth/token.js'

export async function getHarnessMachines(base) {
  const response = await apiFetch(apiUrl(base, '/harness/machines'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getHarnessApprovals(base, status) {
  const suffix = status ? `?status=${encodeURIComponent(status)}` : ''
  const response = await apiFetch(apiUrl(base, `/harness/approvals${suffix}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getHarnessApproval(base, requestId) {
  const response = await apiFetch(apiUrl(base, `/harness/approvals/${encodeURIComponent(requestId)}`), {
    signal: AbortSignal.timeout(8000),
  })
  return unwrap(response)
}

export async function decideHarnessApprovalsBatch(base, payload) {
  const response = await apiFetch(apiUrl(base, '/harness/approvals/decide-batch'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export function harnessApprovalAuditUrl(base) {
  return apiUrl(base, '/harness/approvals/audit')
}

export async function getMachineErrors(base, workerId) {
  const response = await apiFetch(apiUrl(base, `/harness/machines/${encodeURIComponent(workerId)}/errors`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function drainHarnessMachine(base, workerId, draining) {
  const response = await apiFetch(apiUrl(base, `/harness/machines/${encodeURIComponent(workerId)}/drain`), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ draining }),
    signal: AbortSignal.timeout(8000),
  })
  return unwrap(response)
}

export async function decideHarnessApproval(base, requestId, payload) {
  const response = await apiFetch(apiUrl(base, `/harness/approvals/${encodeURIComponent(requestId)}/decision`), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000) })
  return unwrap(response)
}

export async function getApprovalNotifications(base, { requestId = '', limit = 50 } = {}) {
  const query = new URLSearchParams({ limit: String(limit) })
  if (requestId) query.set('requestId', requestId)
  const response = await apiFetch(apiUrl(base, `/harness/approvals/notifications?${query}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getHarnessObservabilityRuns(base) {
  const response = await apiFetch(apiUrl(base, '/harness/observability/runs'), { signal: AbortSignal.timeout(8000) })
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
  const response = await apiFetch(apiUrl(base, `/harness/observability/runs/${encodeURIComponent(runId)}/events?${query}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getHarnessObservabilityMetrics(base) {
  const response = await apiFetch(apiUrl(base, '/harness/observability/metrics'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export function harnessTraceExportUrl(base, runId) {
  return apiUrl(base, `/harness/observability/runs/${encodeURIComponent(runId)}/export`)
}

export async function getObservabilityExports(base, { from = '', to = '', runId = '', format = 'json', limit = 1000 } = {}) {
  const query = new URLSearchParams({ format: String(format), limit: String(limit) })
  if (from) query.set('from', from)
  if (to) query.set('to', to)
  if (runId) query.set('runId', runId)
  const response = await apiFetch(apiUrl(base, `/harness/observability/exports?${query}`), { signal: AbortSignal.timeout(30000) })
  if (format === 'csv') {
    if (!response.ok) await unwrap(response)
    return { blob: await response.blob(), total: Number(response.headers.get('X-Harness-Total') || 0), truncated: response.headers.get('X-Harness-Truncated') === 'true' }
  }
  return unwrap(response)
}

export async function getObservabilityTrends(base, { bucket = 'hour', limit = 24 } = {}) {
  const query = new URLSearchParams({ bucket, limit: String(limit) })
  const response = await apiFetch(apiUrl(base, `/harness/observability/trends?${query}`), { signal: AbortSignal.timeout(15000) })
  return unwrap(response)
}
