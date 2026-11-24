import { unwrap, apiUrl } from '../../core/http.js'
import { apiFetch } from '../auth/token.js'

export async function getSessions(base) {
  const response = await apiFetch(apiUrl(base, '/session/list?pageNum=1&pageSize=100'), { signal: AbortSignal.timeout(8000) })
  const result = await unwrap(response)
  return result?.records || []
}

export async function getAllSessions(base) {
  const pageSize = 1000
  const records = []
  let pageNum = 1
  let total = Infinity
  while (records.length < total) {
    const response = await apiFetch(apiUrl(base, `/session/list?pageNum=${pageNum}&pageSize=${pageSize}`), { signal: AbortSignal.timeout(15000) })
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
  const response = await apiFetch(apiUrl(base, `/session/${encodeURIComponent(id)}`))
  return unwrap(response)
}

export async function removeSession(base, id) {
  const response = await apiFetch(apiUrl(base, `/session/${encodeURIComponent(id)}`), { method: 'DELETE' })
  return unwrap(response)
}

export async function uploadFile(base, file, filename) {
  const body = new FormData()
  body.append('file', file, filename || file.name)
  const response = await apiFetch(apiUrl(base, '/file/upload'), { method: 'POST', body })
  const result = await unwrap(response)
  if (!result?.fileId) throw new Error('上传成功，但服务未返回文件编号')
  return result
}

export async function testBackend(base) {
  const response = await apiFetch(apiUrl(base, '/health'), { signal: AbortSignal.timeout(8000) })
  await unwrap(response)
  return true
}

export async function stopAgent(base, id) {
  const response = await apiFetch(apiUrl(base, `/agent/stop?conversationId=${encodeURIComponent(id)}`))
  return unwrap(response)
}

export function streamUrl(base, mode, query, conversationId, fileId, workspaceId = '') {
  // A skill run must keep its skill even when a file is attached.
  const route = mode === 'skills'
    ? '/agent/skills/stream'
    : (fileId ? '/agent/file/stream' : ({ chat: '/agent/chat/stream', ppt: '/agent/pptx/stream', deep: '/agent/deep/stream' }[mode] || '/agent/chat/stream'))
  const params = new URLSearchParams({ query, conversationId })
  if (fileId) params.set('fileId', fileId)
  if (workspaceId) params.set('workspaceId', workspaceId)
  return `${apiUrl(base, route)}?${params}`
}
