import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { test } from 'node:test'
import { backendStatus } from './backend-status.js'

test('reports failure details and changes without repeating unchanged errors or readiness', async () => {
  const originalFetch = globalThis.fetch
  const httpServer = new EventEmitter()
  const messages = []
  const responses = ['offline', 'worker', 'registry', 'registry', 200, 200]
  let calls = 0
  globalThis.fetch = async () => {
    const response = responses[calls++]
    if (response === 'offline') {
      throw new TypeError('fetch failed', { cause: new Error('connection refused', { cause: null }) })
    }
    if (typeof response === 'string') {
      return new Response(JSON.stringify({ [response]: 'unavailable' }), { status: 503 })
    }
    return new Response(null, { status: response })
  }
  try {
    backendStatus('http://127.0.0.1:8888').configureServer({
      httpServer,
      config: { logger: {
        info: message => messages.push(message),
        error: message => messages.push(message),
      } },
    })
    httpServer.emit('listening')
    const deadline = Date.now() + 15000
    while (calls < responses.length && Date.now() < deadline) {
      await new Promise(resolve => setTimeout(resolve, 20))
    }
    assert.equal(calls, responses.length)
    assert.equal(messages.length, 4)
    assert.match(messages[0], /后端未连接/)
    assert.match(messages[0], /connection refused/)
    assert.match(messages[1], /后端尚未就绪/)
    assert.match(messages[1], /HTTP 503/)
    assert.match(messages[1], /"worker":"unavailable"/)
    assert.match(messages[2], /"registry":"unavailable"/)
    assert.match(messages[3], /Python 能力服务与执行 Worker 已就绪/)
  } finally {
    httpServer.emit('close')
    globalThis.fetch = originalFetch
  }
})
