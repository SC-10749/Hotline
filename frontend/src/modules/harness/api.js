import { unwrap, apiUrl } from '../../core/http.js'
import { apiFetch } from '../auth/token.js'

export async function getHarnessOverview(base) {
  const response = await apiFetch(apiUrl(base, '/harness/overview'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getHarnessSettings(base) {
  const response = await apiFetch(apiUrl(base, '/harness/settings'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function saveHarnessSettings(base, payload) {
  const response = await apiFetch(apiUrl(base, '/harness/settings'), { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000) })
  return unwrap(response)
}
