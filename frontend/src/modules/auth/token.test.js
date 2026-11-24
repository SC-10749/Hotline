import { test } from 'node:test'
import assert from 'node:assert/strict'
import { apiFetch, apiToken, setApiToken } from './token.js'

// 前端共享密钥：请求头只在配置了密钥时才带，未配置时行为与启用前一致。

test('no token means no auth header', async () => {
  setApiToken('')
  const calls = []
  const original = globalThis.fetch
  globalThis.fetch = async (url, options) => { calls.push([url, options]); return { ok: true } }
  try {
    await apiFetch('/session/list')
    assert.equal(calls[0][1].headers?.['X-Hotline-Token'], undefined)
  } finally {
    globalThis.fetch = original
  }
})

test('configured token is sent as a header', async () => {
  setApiToken('secret')
  const calls = []
  const original = globalThis.fetch
  globalThis.fetch = async (url, options) => { calls.push([url, options]); return { ok: true } }
  try {
    await apiFetch('/session/list')
    assert.equal(calls[0][1].headers['X-Hotline-Token'], 'secret')
  } finally {
    globalThis.fetch = original
    setApiToken('')
  }
})

test('existing headers are preserved', async () => {
  setApiToken('secret')
  const calls = []
  const original = globalThis.fetch
  globalThis.fetch = async (url, options) => { calls.push([url, options]); return { ok: true } }
  try {
    await apiFetch('/file/upload', { method: 'POST', headers: { 'Content-Type': 'application/json' } })
    assert.equal(calls[0][1].headers['Content-Type'], 'application/json')
    assert.equal(calls[0][1].headers['X-Hotline-Token'], 'secret')
  } finally {
    globalThis.fetch = original
    setApiToken('')
  }
})

test('token round-trips through storage when available', () => {
  const store = new Map()
  globalThis.localStorage = {
    getItem: (key) => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => store.set(key, value),
  }
  try {
    setApiToken('stored')
    assert.equal(apiToken(), 'stored')
    assert.equal(store.get('hotline-api-token'), 'stored')
    setApiToken('')
    assert.equal(store.get('hotline-api-token'), '')
  } finally {
    delete globalThis.localStorage
    setApiToken('')
  }
})
