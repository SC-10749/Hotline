// Report changes only, so a long-running dev terminal stays readable.
export function backendStatus(backend) {
  return {
    name: 'hotline-backend-status',
    configureServer(server) {
      let timer
      let stopped = false
      let previous
      const check = async () => {
        let state = 'offline'
        let detail = ''
        try {
          const response = await fetch(`${backend}/health/ready`, {
            signal: AbortSignal.timeout(1500),
          })
          state = response.ok ? 'ready' : 'starting'
          if (!response.ok) {
            detail = `HTTP ${response.status} ${response.statusText}`.trim()
            const body = (await response.text()).trim()
            if (body) detail += `\n  ${body}`
          } else {
            await response.body?.cancel()
          }
        } catch (error) {
          detail = [error.message, error.cause?.code, error.cause?.message]
            .filter(Boolean).join(' · ')
        }
        if (stopped) return
        const status = `${state}:${detail}`
        if (status !== previous) {
          const message = state === 'ready'
            ? `✓ Java 21、Python 能力服务与执行 Worker 已就绪  ${backend}/health/ready`
            : state === 'starting'
              ? '… 后端尚未就绪，请检查 Java、Python 能力服务和执行 Worker。'
              : '… 后端未连接，请在项目根目录运行 npm start；正在等待后端启动。'
          const output = `\n  ${message}${detail ? `\n  ${backend}/health/ready\n  ${detail}` : ''}\n`
          if (state === 'ready') server.config.logger.info(output)
          else server.config.logger.error(output)
          previous = status
        }
        timer = setTimeout(check, 2000)
        timer.unref()
      }
      server.httpServer?.once('listening', () => { void check() })
      server.httpServer?.once('close', () => {
        stopped = true
        clearTimeout(timer)
      })
    },
  }
}
