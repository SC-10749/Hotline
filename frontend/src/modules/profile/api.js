import { unwrap, apiUrl } from '../../core/http.js'
import { apiFetch } from '../auth/token.js'

export async function getProfile(base) {
  const response = await apiFetch(apiUrl(base, '/harness/profile'), { signal: AbortSignal.timeout(8000) })
  const result = await unwrap(response)
  return result?.profile || {}
}

export async function saveProfile(base, payload) {
  const response = await apiFetch(apiUrl(base, '/harness/profile'), {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    signal: AbortSignal.timeout(15000),
  })
  const result = await unwrap(response)
  return result?.profile || {}
}

export async function getCredential(base) {
  const response = await apiFetch(apiUrl(base, '/harness/profile/credentials'), { signal: AbortSignal.timeout(8000) })
  const result = await unwrap(response)
  return result?.credential || null
}

export async function saveCredential(base, payload) {
  const response = await apiFetch(apiUrl(base, '/harness/profile/credentials'), {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    signal: AbortSignal.timeout(15000),
  })
  const result = await unwrap(response)
  return result?.credential || null
}

export async function deleteCredential(base) {
  const response = await apiFetch(apiUrl(base, '/harness/profile/credentials'), {
    method: 'DELETE', signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function testCredential(base, payload) {
  const response = await apiFetch(apiUrl(base, '/harness/profile/credentials/test'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    signal: AbortSignal.timeout(60000),
  })
  return unwrap(response)
}
