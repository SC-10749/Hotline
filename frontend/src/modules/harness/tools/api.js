import { unwrap, apiUrl } from '../../../core/http.js'
import { apiFetch } from '../../auth/token.js'

export async function getHarnessTools(base) {
  const response = await apiFetch(apiUrl(base, '/harness/tools'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getHarnessTool(base, toolId) {
  const response = await apiFetch(apiUrl(base, `/harness/tools/${encodeURIComponent(toolId)}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function createHarnessTool(base, payload) {
  const response = await apiFetch(apiUrl(base, '/harness/tools'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function updateHarnessTool(base, toolId, payload) {
  const response = await apiFetch(apiUrl(base, `/harness/tools/${encodeURIComponent(toolId)}`), {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function testHarnessTool(base, toolId) {
  const response = await apiFetch(apiUrl(base, `/harness/tools/${encodeURIComponent(toolId)}/test`), {
    method: 'POST', signal: AbortSignal.timeout(20000),
  })
  return unwrap(response)
}

export async function getHarnessMcpServers(base) {
  const response = await apiFetch(apiUrl(base, '/harness/mcp/servers'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function callMcpTool(base, toolId, toolName, args = {}) {
  const response = await apiFetch(apiUrl(base, `/harness/mcp/servers/${encodeURIComponent(toolId)}/tools/${encodeURIComponent(toolName)}/call`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ arguments: args }),
    signal: AbortSignal.timeout(60000),
  })
  return unwrap(response)
}
