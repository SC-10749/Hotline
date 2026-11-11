import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { once } from 'node:events'
import { test } from 'node:test'
import { inspectService } from './service-status.mjs'

test('reuses only a healthy identified service and recognizes a free port', async () => {
  let service = 'hotline-agent'
  const server = createServer((request, response) => {
    response.setHeader('Content-Type', 'application/json')
    response.end(JSON.stringify({ status: 'UP', service }))
  })
  server.listen(0, '127.0.0.1')
  await once(server, 'listening')
  const port = server.address().port
  try {
    assert.equal(await inspectService('Python', port, '/health', 'hotline-agent'), true)
    service = 'another-app'
    await assert.rejects(inspectService('Python', port, '/health', 'hotline-agent'), /端口.*已被占用/)
  } finally {
    server.closeAllConnections()
    await new Promise(resolve => server.close(resolve))
  }
  assert.equal(await inspectService('Python', port, '/health', 'hotline-agent'), false)
})
