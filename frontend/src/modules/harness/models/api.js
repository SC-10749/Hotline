import { unwrap, apiUrl } from '../../../core/http.js'
import { apiFetch } from '../../auth/token.js'

export async function testHarnessModel(base, modelId) {
  const response = await apiFetch(apiUrl(base, `/harness/models/${encodeURIComponent(modelId)}/test`), {
    method: 'POST', signal: AbortSignal.timeout(20000),
  })
  return unwrap(response)
}

export async function getModelFallbackChain(base, modelId) {
  const response = await apiFetch(apiUrl(base, `/harness/models/${encodeURIComponent(modelId)}/fallback-chain`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getHarnessModels(base) {
  const response = await apiFetch(apiUrl(base, '/harness/models'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getHarnessModel(base, modelId) {
  const response = await apiFetch(apiUrl(base, `/harness/models/${encodeURIComponent(modelId)}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function createHarnessModel(base, payload) {
  const response = await apiFetch(apiUrl(base, '/harness/models'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function updateHarnessModel(base, modelId, payload) {
  const response = await apiFetch(apiUrl(base, `/harness/models/${encodeURIComponent(modelId)}`), {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}
