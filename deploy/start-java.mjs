import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { existsSync, readFileSync } from 'node:fs'

// Match Python's shared local configuration without printing private values.
const envFile = process.env.DODO_ENV_FILE || fileURLToPath(new URL('../.env', import.meta.url))
if (existsSync(envFile)) {
  const values = {}
  for (const line of readFileSync(envFile, 'utf8').split(/\r?\n/)) {
    const separator = line.indexOf('=')
    if (separator < 1 || line.trimStart().startsWith('#')) continue
    values[line.slice(0, separator).trim()] = line.slice(separator + 1).trim()
  }
  if (process.env.DODO_ENV_PROFILE === 'remote') {
    for (const [key, value] of Object.entries(values)) {
      if (key.startsWith('REMOTE_')) values[key.slice(7)] = value
    }
  }
  for (const [key, value] of Object.entries(values)) {
    if (key.startsWith('HOTLINE_') && process.env[key] === undefined && value) process.env[key] = value
  }
}

const windows = process.platform === 'win32'
const child = spawn(windows ? (process.env.ComSpec || 'cmd.exe') : './mvnw',
  windows ? ['/d', '/c', 'mvnw.cmd', '-q', 'spring-boot:run'] : ['-q', 'spring-boot:run'], {
    cwd: fileURLToPath(new URL('../java_backend/', import.meta.url)),
    windowsHide: true,
    stdio: 'inherit',
    env: process.env,
  })
child.on('error', () => { console.error('Java 21 服务启动失败，请检查 JDK 和 Maven Wrapper。'); process.exitCode = 1 })
child.on('exit', code => { process.exitCode = code ?? 1 })
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill(signal))
