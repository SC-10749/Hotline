import { spawn } from 'node:child_process'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = dirname(fileURLToPath(import.meta.url))
const children = []
let closing = false
const shutdown = async (code = 0) => {
  if (closing) return
  closing = true
  await Promise.all(children.map(child => {
    if (!child.pid || child.exitCode !== null) return
    if (process.platform !== 'win32') { child.kill('SIGTERM'); return }
    return new Promise(resolve => {
      const killer = spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' })
      killer.on('error', resolve)
      killer.on('close', resolve)
    })
  }))
  process.exitCode = code
}
const start = (args, cwd) => {
  const child = spawn(process.execPath, args, { cwd, windowsHide: true, stdio: 'inherit', env: process.env })
  children.push(child)
  child.on('error', () => { console.error('Hotline 开发服务启动失败。'); void shutdown(1) })
  child.on('exit', code => { if (!closing) void shutdown(code ?? 1) })
}
start(['start-services.mjs'], root)
start([join(root, 'frontend/node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', process.env.DODO_DEV_FRONTEND_PORT || '5180', '--strictPort'], join(root, 'frontend'))
process.on('SIGINT', () => void shutdown())
process.on('SIGTERM', () => void shutdown())
