import { unwrap, apiUrl } from '../../core/http.js'
import { apiFetch } from '../auth/token.js'

export async function getDocuments(base) {
  const response = await apiFetch(apiUrl(base, '/document/list'), { signal: AbortSignal.timeout(8000) })
  const result = await unwrap(response)
  return result?.documents || []
}

// MinerU converts asynchronously and a large PDF can queue for minutes, so this
// must not carry the short timeout the list endpoints use.
export async function uploadDocument(base, file) {
  const body = new FormData()
  body.append('file', file)
  const response = await apiFetch(apiUrl(base, '/document/upload'), {
    method: 'POST', body, signal: AbortSignal.timeout(960000),
  })
  return unwrap(response)
}

export async function vectorizeDocument(base, id) {
  const response = await apiFetch(apiUrl(base, `/document/${encodeURIComponent(id)}/vectorize`), {
    method: 'POST', signal: AbortSignal.timeout(300000),
  })
  return unwrap(response)
}

export async function getDocumentPreview(base, id) {
  const response = await apiFetch(apiUrl(base, `/document/${encodeURIComponent(id)}/preview`), {
    signal: AbortSignal.timeout(30000),
  })
  return unwrap(response)
}

export async function compensateDocuments(base) {
  const response = await apiFetch(apiUrl(base, '/document/compensate'), { method: 'POST', signal: AbortSignal.timeout(300000) })
  return unwrap(response)
}

export async function getDocumentVersions(base, id) {
  const response = await apiFetch(apiUrl(base, `/document/${encodeURIComponent(id)}/versions`))
  const result = await unwrap(response)
  return Array.isArray(result) ? result : []
}

export async function removeDocument(base, id) {
  const response = await apiFetch(apiUrl(base, `/document/${encodeURIComponent(id)}`), { method: 'DELETE' })
  return unwrap(response)
}
