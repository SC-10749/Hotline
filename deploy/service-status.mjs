import { createConnection } from 'node:net'

export async function inspectService(name, port, healthPath, expectedService) {
  const listening = await new Promise(resolve => {
    const socket = createConnection({ host: '127.0.0.1', port: Number(port) })
    const finish = value => { socket.destroy(); resolve(value) }
    socket.setTimeout(1000, () => finish(true))
    socket.once('connect', () => finish(true))
    socket.once('error', error => finish(error.code !== 'ECONNREFUSED'))
  })
  if (!listening) return false
  try {
    const response = await fetch(`http://127.0.0.1:${port}${healthPath}`, {
      signal: AbortSignal.timeout(2000),
    })
    const payload = await response.json()
    if (response.ok && payload.service === expectedService && payload.status === 'UP') return true
  } catch { /* Occupied ports require a verified service identity before reuse. */ }
  throw new Error(`${name} 端口 ${port} 已被占用，现有进程未通过 Hotline 身份与健康检查。请检查占用进程后重试。`)
}

export async function isReady(port) {
  try {
    const response = await fetch(`http://127.0.0.1:${port}/health/ready`, {
      signal: AbortSignal.timeout(1500),
    })
    await response.body?.cancel()
    return response.ok
  } catch {
    return false
  }
}
