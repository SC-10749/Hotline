import { unwrap, apiUrl } from '../../core/http.js'
import { apiFetch } from '../auth/token.js'

export async function getSkills(base) {
  const response = await apiFetch(apiUrl(base, '/skill/list'), { signal: AbortSignal.timeout(8000) })
  const result = await unwrap(response)
  return result?.skills || []
}

export async function getSkillDetail(base, skillId) {
  const response = await apiFetch(apiUrl(base, `/skill/${encodeURIComponent(skillId)}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getCatalogSkills(base) {
  const response = await apiFetch(apiUrl(base, '/harness/skills/catalog'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getCatalogVersion(base, name, version) {
  const query = new URLSearchParams({ name, version })
  const response = await apiFetch(apiUrl(base, `/harness/skills/catalog/version?${query}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function compareCatalogVersions(base, name, baseVersion, version) {
  const query = new URLSearchParams({ name, baseVersion, version })
  const response = await apiFetch(apiUrl(base, `/harness/skills/catalog/compare?${query}`), { signal: AbortSignal.timeout(15000) })
  return unwrap(response)
}

// The backend answers 400 with the archive's file list when SKILL.md is ambiguous,
// so this one cannot go through unwrap().
export async function uploadSkill(base, file, entry) {
  const body = new FormData()
  body.append('file', file)
  if (entry) body.append('entry', entry)
  const response = await apiFetch(apiUrl(base, '/skill/upload'), { method: 'POST', body })
  const payload = await response.json().catch(() => null)
  if (payload?.code === 200 && payload.data?.id) return { success: true, skill: payload.data }
  return {
    success: false,
    message: payload?.message || `上传失败（HTTP ${response.status}）`,
    entries: payload?.data?.entries || [],
  }
}

export async function setSkillEnabled(base, id, enabled) {
  const response = await apiFetch(apiUrl(base, `/skill/${encodeURIComponent(id)}/toggle?enabled=${enabled}`), { method: 'POST' })
  return unwrap(response)
}

export async function removeSkill(base, id) {
  const response = await apiFetch(apiUrl(base, `/skill/${encodeURIComponent(id)}`), { method: 'DELETE' })
  return unwrap(response)
}

export async function bindCatalogSkill(base, payload) {
  const response = await apiFetch(apiUrl(base, '/harness/skills/catalog/bind'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function unbindCatalogSkill(base, payload) {
  const response = await apiFetch(apiUrl(base, '/harness/skills/catalog/bind'), {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}
