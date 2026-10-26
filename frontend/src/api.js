const unwrap = async (response) => {
  let payload
  try {
    payload = await response.json()
  } catch {
    throw new Error(`服务返回了无法识别的数据（HTTP ${response.status}）`)
  }
  if (!response.ok || (payload?.code && payload.code !== 200)) {
    throw new Error(payload?.message || `请求失败（HTTP ${response.status}）`)
  }
  return payload?.data ?? payload
}

export const apiUrl = (base, path) => `${base.replace(/\/+$/, '')}${path}`

export async function getSessions(base) {
  const response = await fetch(apiUrl(base, '/session/list?pageNum=1&pageSize=100'), { signal: AbortSignal.timeout(8000) })
  const result = await unwrap(response)
  return result?.records || []
}

export async function getAllSessions(base) {
  const pageSize = 1000
  const records = []
  let pageNum = 1
  let total = Infinity
  while (records.length < total) {
    const response = await fetch(apiUrl(base, `/session/list?pageNum=${pageNum}&pageSize=${pageSize}`), { signal: AbortSignal.timeout(15000) })
    const result = await unwrap(response)
    const page = result?.records || []
    records.push(...page)
    total = Number(result?.total ?? records.length)
    if (page.length < pageSize || page.length === 0) break
    pageNum += 1
  }
  return records
}

export async function getSession(base, id) {
  const response = await fetch(apiUrl(base, `/session/${encodeURIComponent(id)}`))
  return unwrap(response)
}

export async function removeSession(base, id) {
  const response = await fetch(apiUrl(base, `/session/${encodeURIComponent(id)}`), { method: 'DELETE' })
  return unwrap(response)
}

export async function uploadFile(base, file) {
  const body = new FormData()
  body.append('file', file)
  const response = await fetch(apiUrl(base, '/file/upload'), { method: 'POST', body })
  const result = await unwrap(response)
  if (!result?.fileId) throw new Error('上传成功，但服务未返回文件编号')
  return result
}

export async function testBackend(base) {
  const response = await fetch(apiUrl(base, '/health'), { signal: AbortSignal.timeout(8000) })
  await unwrap(response)
  return true
}

export async function stopAgent(base, id) {
  const response = await fetch(apiUrl(base, `/agent/stop?conversationId=${encodeURIComponent(id)}`))
  return unwrap(response)
}

export async function getSkills(base) {
  const response = await fetch(apiUrl(base, '/skill/list'), { signal: AbortSignal.timeout(8000) })
  const result = await unwrap(response)
  return result?.skills || []
}

// The backend answers 400 with the archive's file list when SKILL.md is ambiguous,
// so this one cannot go through unwrap().
export async function uploadSkill(base, file, entry) {
  const body = new FormData()
  body.append('file', file)
  if (entry) body.append('entry', entry)
  const response = await fetch(apiUrl(base, '/skill/upload'), { method: 'POST', body })
  const payload = await response.json().catch(() => null)
  if (payload?.code === 200 && payload.data?.id) return { success: true, skill: payload.data }
  return {
    success: false,
    message: payload?.message || `上传失败（HTTP ${response.status}）`,
    entries: payload?.data?.entries || [],
  }
}

export async function setSkillEnabled(base, id, enabled) {
  const response = await fetch(apiUrl(base, `/skill/${encodeURIComponent(id)}/toggle?enabled=${enabled}`), { method: 'POST' })
  return unwrap(response)
}

export async function removeSkill(base, id) {
  const response = await fetch(apiUrl(base, `/skill/${encodeURIComponent(id)}`), { method: 'DELETE' })
  return unwrap(response)
}

export async function getDocuments(base) {
  const response = await fetch(apiUrl(base, '/document/list'), { signal: AbortSignal.timeout(8000) })
  const result = await unwrap(response)
  return result?.documents || []
}

// MinerU converts asynchronously and a large PDF can queue for minutes, so this
// must not carry the short timeout the list endpoints use.
export async function uploadDocument(base, file) {
  const body = new FormData()
  body.append('file', file)
  const response = await fetch(apiUrl(base, '/document/upload'), {
    method: 'POST', body, signal: AbortSignal.timeout(960000),
  })
  return unwrap(response)
}

export async function vectorizeDocument(base, id) {
  const response = await fetch(apiUrl(base, `/document/${encodeURIComponent(id)}/vectorize`), {
    method: 'POST', signal: AbortSignal.timeout(300000),
  })
  return unwrap(response)
}

export async function getDocumentPreview(base, id) {
  const response = await fetch(apiUrl(base, `/document/${encodeURIComponent(id)}/preview`), {
    signal: AbortSignal.timeout(30000),
  })
  return unwrap(response)
}

export async function compensateDocuments(base) {
  const response = await fetch(apiUrl(base, '/document/compensate'), { method: 'POST', signal: AbortSignal.timeout(300000) })
  return unwrap(response)
}

export async function getDocumentVersions(base, id) {
  const response = await fetch(apiUrl(base, `/document/${encodeURIComponent(id)}/versions`))
  const result = await unwrap(response)
  return Array.isArray(result) ? result : []
}

export async function removeDocument(base, id) {
  const response = await fetch(apiUrl(base, `/document/${encodeURIComponent(id)}`), { method: 'DELETE' })
  return unwrap(response)
}

export function streamUrl(base, mode, query, conversationId, fileId) {
  // A skill run must keep its skill even when a file is attached.
  const route = mode === 'skills'
    ? '/agent/skills/stream'
    : (fileId ? '/agent/file/stream' : ({ chat: '/agent/chat/stream', ppt: '/agent/pptx/stream', deep: '/agent/deep/stream' }[mode] || '/agent/chat/stream'))
  const params = new URLSearchParams({ query, conversationId })
  if (fileId) params.set('fileId', fileId)
  return `${apiUrl(base, route)}?${params}`
}
