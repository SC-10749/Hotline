import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { test } from 'node:test'
import { backendStatus } from './backend-status.js'

test('reports offline, unready and ready states without repeating unchanged status', async () => {
  const originalFetch = globalThis.fetch
  const httpServer = new EventEmitter()
  const messages = []
  const responses = ['offline', 503, 200, 200]
  let calls = 0
  globalThis.fetch = async () => {
    const response = responses[calls++]
    if (response === 'offline') throw new Error('connection refused')
    return new Response(null, { status: response })
  }
  try {
    backendStatus('http://127.0.0.1:8888').configureServer({
      httpServer,
      config: { logger: { info: message => messages.push(message) } },
    })
    httpServer.emit('listening')
    const deadline = Date.now() + 10000
    while (calls < 4 && Date.now() < deadline) {
      await new Promise(resolve => setTimeout(resolve, 20))
    }
    assert.equal(calls, 4)
    assert.equal(messages.length, 3)
    assert.match(messages[0], /后端未连接/)
    assert.match(messages[1], /后端尚未就绪/)
    assert.match(messages[2], /Python 能力服务与执行 Worker 已就绪/)
  } finally {
    httpServer.emit('close')
    globalThis.fetch = originalFetch
  }
})
