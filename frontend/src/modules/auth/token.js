// 共享密钥：与后端 HOTLINE_API_TOKEN 一致，存在 localStorage，读取一次后随请求发出。

const STORAGE_KEY = 'hotline-api-token'
export const TOKEN_HEADER = 'X-Hotline-Token'

// localStorage 不可用时（隐私模式、非浏览器环境）退回到内存，行为仍然一致。
let memoryToken = ''

export function apiToken() {
  try {
    const stored = globalThis.localStorage?.getItem(STORAGE_KEY)
    if (stored !== null && stored !== undefined) return stored
  } catch {
    // 读不到就退回内存值。
  }
  return memoryToken
}

export function setApiToken(value) {
  const token = (value || '').trim()
  memoryToken = token
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, token)
  } catch {
    // 隐私模式下 localStorage 不可用：只保留内存值。
  }
}

// 未配置密钥时不加请求头，后端也未启用校验，行为与启用前一致。
export async function apiFetch(url, options = {}) {
  const token = apiToken()
  if (!token) return globalThis.fetch(url, options)
  const headers = { ...(options.headers || {}), [TOKEN_HEADER]: token }
  return globalThis.fetch(url, { ...options, headers })
}
