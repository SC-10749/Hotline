import test from 'node:test'
import assert from 'node:assert/strict'
import { getCiWorkflow, setCiWorkflow } from './api.js'

function stubFetch(payload, { ok = true, status = 200 } = {}) {
  const calls = []
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, method: options.method || 'GET', body: options.body })
    return { ok, status, json: async () => payload }
  }
  return calls
}

test('reads the ci workflow state from the harness api', async () => {
  const calls = stubFetch({ configured: true, enabled: false, state: 'disabled_manually' })

  const result = await getCiWorkflow('http://127.0.0.1:8888')

  assert.equal(calls[0].url, 'http://127.0.0.1:8888/harness/ci-workflow')
  assert.equal(calls[0].method, 'GET')
  assert.equal(result.enabled, false)
  assert.equal(result.state, 'disabled_manually')
})

test('turning the workflow off posts the disabled intent', async () => {
  const calls = stubFetch({ configured: true, enabled: false, state: 'disabled_manually' })

  await setCiWorkflow('http://127.0.0.1:8888/', false)

  assert.equal(calls[0].method, 'POST')
  assert.equal(calls[0].url, 'http://127.0.0.1:8888/harness/ci-workflow')
  assert.deepEqual(JSON.parse(calls[0].body), { enabled: false })
})

test('a failing switch surfaces the backend message', async () => {
  stubFetch({ detail: '未配置 GitHub Token 与仓库地址，无法启停工作流' }, { ok: false, status: 409 })

  await assert.rejects(() => setCiWorkflow('http://127.0.0.1:8888', true),
    /未配置 GitHub Token/)
})
