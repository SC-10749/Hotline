import { unwrap, apiUrl } from '../../core/http.js'
import { apiFetch } from '../auth/token.js'

export async function getBots(base) {
  const response = await apiFetch(apiUrl(base, '/harness/bots'), { signal: AbortSignal.timeout(8000) })
  const result = await unwrap(response)
  return result?.items || []
}

export async function createBot(base, payload) {
  const response = await apiFetch(apiUrl(base, '/harness/bots'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    signal: AbortSignal.timeout(15000),
  })
  const result = await unwrap(response)
  return result?.bot
}

export async function updateBot(base, botId, payload) {
  const response = await apiFetch(apiUrl(base, `/harness/bots/${encodeURIComponent(botId)}`), {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    signal: AbortSignal.timeout(15000),
  })
  const result = await unwrap(response)
  return result?.bot
}

export async function deleteBot(base, botId) {
  const response = await apiFetch(apiUrl(base, `/harness/bots/${encodeURIComponent(botId)}`), {
    method: 'DELETE', signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}
