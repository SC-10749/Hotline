import { unwrap, apiUrl } from '../../core/http.js'
import { apiFetch } from '../auth/token.js'

export async function getReleaseSummary(base) {
  const response = await apiFetch(apiUrl(base, '/release/summary'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function promoteRelease(base, payload) {
  const response = await apiFetch(apiUrl(base, '/release/promote'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function evaluateReleaseGate(base, payload) {
  const response = await apiFetch(apiUrl(base, '/release/gate'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000) })
  return unwrap(response)
}

export async function getReleaseGates(base) {
  const response = await apiFetch(apiUrl(base, '/release/gates'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getReleaseRecords(base) {
  const response = await apiFetch(apiUrl(base, '/release/records'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function advanceRollout(base, payload) {
  const response = await apiFetch(apiUrl(base, '/release/rollouts/advance'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function getReleaseConfig(base) {
  const response = await apiFetch(apiUrl(base, '/release/config'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function saveReleaseConfig(base, payload) {
  const response = await apiFetch(apiUrl(base, '/release/config'), {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function getReleaseGateThresholds(base) {
  const response = await apiFetch(apiUrl(base, '/release/gate-thresholds'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function saveReleaseGateThresholds(base, payload) {
  const response = await apiFetch(apiUrl(base, '/release/gate-thresholds'), {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function rollbackRelease(base, payload) {
  const response = await apiFetch(apiUrl(base, '/release/rollback'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function getReleaseObservations(base, { project = '', limit = 50 } = {}) {
  const query = new URLSearchParams({ limit: String(limit) })
  if (project) query.set('project', project)
  const response = await apiFetch(apiUrl(base, `/release/observations?${query}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function observeReleaseRollout(base, payload) {
  const response = await apiFetch(apiUrl(base, '/release/rollouts/observe'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(20000),
  })
  return unwrap(response)
}
