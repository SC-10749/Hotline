import { unwrap, apiUrl } from '../../../core/http.js'
import { apiFetch } from '../../auth/token.js'

export async function getHarnessAgents(base) {
  const response = await apiFetch(apiUrl(base, '/harness/agents'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getHarnessAgent(base, agentId) {
  const response = await apiFetch(apiUrl(base, `/harness/agents/${encodeURIComponent(agentId)}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function updateHarnessAgent(base, agentId, payload) {
  const response = await apiFetch(apiUrl(base, `/harness/agents/${encodeURIComponent(agentId)}`), {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function createHarnessAgent(base, payload) {
  const response = await apiFetch(apiUrl(base, '/harness/agents'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000) })
  return unwrap(response)
}

export async function setHarnessAgentStatus(base, agentId, enabled) {
  const response = await apiFetch(apiUrl(base, `/harness/agents/${encodeURIComponent(agentId)}/status`), {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled }),
    signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function bindHarnessAgentSkills(base, agentId, skillIds) {
  const response = await apiFetch(apiUrl(base, `/harness/agents/${encodeURIComponent(agentId)}/skills`), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ skillIds }),
    signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function unbindHarnessAgentSkill(base, agentId, skillId) {
  const response = await apiFetch(apiUrl(base, `/harness/agents/${encodeURIComponent(agentId)}/skills/${encodeURIComponent(skillId)}`), {
    method: 'DELETE', signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function getHarnessAgentVersions(base, agentId) {
  const response = await apiFetch(apiUrl(base, `/harness/agents/${encodeURIComponent(agentId)}/versions`), {
    signal: AbortSignal.timeout(8000),
  })
  return unwrap(response)
}

export async function getHarnessAgentDiff(base, agentId, baseVersion, targetVersion) {
  const query = new URLSearchParams({ base: baseVersion, target: targetVersion })
  const response = await apiFetch(apiUrl(base, `/harness/agents/${encodeURIComponent(agentId)}/diff?${query}`), {
    signal: AbortSignal.timeout(8000),
  })
  return unwrap(response)
}

export async function getHarnessAgentRuns(base, agentId) {
  const response = await apiFetch(apiUrl(base, `/harness/agents/${encodeURIComponent(agentId)}/runs`), {
    signal: AbortSignal.timeout(8000),
  })
  return unwrap(response)
}
