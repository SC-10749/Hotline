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

// CI 工作流开关：直接启停仓库里的 GitHub Actions 工作流。
// 浏览器超时抛的是原始英文异常，这里换成用户看得懂的中文再往外抛。
function friendlyError(error) {
  const message = error?.message || ''
  if (/timed out/i.test(message)) return '请求超时，请稍后重试'
  return message
}

export async function getCiWorkflow(base) {
  try {
    const response = await apiFetch(apiUrl(base, '/harness/ci-workflow'), { signal: AbortSignal.timeout(20000) })
    const result = await unwrap(response)
    return result || {}
  } catch (error) {
    throw new Error(friendlyError(error) || 'CI 工作流服务不可用')
  }
}

export async function setCiWorkflow(base, enabled) {
  try {
    const response = await apiFetch(apiUrl(base, '/harness/ci-workflow'), {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled }),
      signal: AbortSignal.timeout(20000),
    })
    const result = await unwrap(response)
    return result || {}
  } catch (error) {
    throw new Error(friendlyError(error) || 'CI 工作流服务不可用')
  }
}
