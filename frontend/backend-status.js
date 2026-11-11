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
        try {
          const response = await fetch(`${backend}/health/ready`, {
            signal: AbortSignal.timeout(1500),
          })
          state = response.ok ? 'ready' : 'starting'
          await response.body?.cancel()
        } catch { /* Backend may be started separately after Vite. */ }
        if (stopped) return
        if (state !== previous) {
          const message = state === 'ready'
            ? `✓ Java 21、Python 能力服务与执行 Worker 已就绪  ${backend}/health/ready`
            : state === 'starting'
              ? '… 后端尚未就绪，请检查 Java、Python 能力服务和执行 Worker。'
              : '… 后端未连接，请在项目根目录运行 npm start；正在等待后端启动。'
          server.config.logger.info(`\n  ${message}\n`)
          previous = state
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
