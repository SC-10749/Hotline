import { unwrap, apiUrl } from '../../core/http.js'
import { apiFetch } from '../auth/token.js'

// 归属请求头名由 Harness 设置决定；拿到设置前用默认名。
let artifactOwnerHeader = 'X-Harness-Owner'

export function setArtifactOwnerHeader(name) {
  const value = String(name || '').trim()
  artifactOwnerHeader = value || 'X-Harness-Owner'
}

const ownerHeaders = (owner) => (owner ? { [artifactOwnerHeader]: owner } : {})

export async function getCodeMapStatus(base) {
  const response = await apiFetch(apiUrl(base, '/code-map'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getHarnessArtifacts(base, runId, { limit = 25, offset = 0, owner = '' } = {}) {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (runId) query.set('runId', runId)
  if (owner) query.set('owner', owner)
  const response = await apiFetch(apiUrl(base, `/harness/artifacts?${query}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function downloadHarnessArtifact(base, artifactId, owner = '') {
  const response = await apiFetch(apiUrl(base, `/harness/artifacts/${encodeURIComponent(artifactId)}/download`), {
    headers: ownerHeaders(owner),
    signal: AbortSignal.timeout(60000),
  })
  if (!response.ok) await unwrap(response)
  return response.blob()
}

export async function getHarnessArtifactPreview(base, artifactId, owner = '') {
  const response = await apiFetch(apiUrl(base, `/harness/artifacts/${encodeURIComponent(artifactId)}/preview`), {
    headers: ownerHeaders(owner),
    signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function cleanupHarnessArtifacts(base, payload) {
  const response = await apiFetch(apiUrl(base, '/harness/artifacts/cleanup'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    signal: AbortSignal.timeout(30000),
  })
  return unwrap(response)
}
