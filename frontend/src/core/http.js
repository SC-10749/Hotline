import { apiFetch } from '../modules/auth/token.js'

export const unwrap = async (response) => {
  let payload
  try {
    payload = await response.json()
  } catch {
    throw new Error(`服务返回了无法识别的数据（HTTP ${response.status}）`)
  }
  if (!response.ok || (payload?.code && payload.code !== 200)) {
    const validationMessage = Array.isArray(payload?.detail) ? payload.detail.map(item => item.msg).join('；') : ''
    const error = new Error(payload?.message || (typeof payload?.detail === 'string' ? payload.detail : validationMessage) || `请求失败（HTTP ${response.status}）`)
    error.status = response.status
    throw error
  }
  return payload?.data ?? payload
}

export const apiUrl = (base, path) => `${base.replace(/\/+$/, '')}${path}`
