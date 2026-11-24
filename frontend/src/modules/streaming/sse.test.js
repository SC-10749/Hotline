import { test } from 'node:test'
import assert from 'node:assert/strict'
import { parseSseFrames } from './sse.js'

// SSE 分帧必须能处理：分片到达、CRLF、多行 data、空行分隔与 [DONE]。

test('a frame split across chunks is only delivered once complete', () => {
  const state = parseSseFrames()
  assert.deepEqual(state.push('data: {"a":1}\n'), [])
  assert.deepEqual(state.push('\n'), ['{"a":1}'])
})

test('several frames in one chunk are delivered in order', () => {
  const state = parseSseFrames()
  assert.deepEqual(state.push('data: 1\n\ndata: 2\n\n'), ['1', '2'])
})

test('CRLF line endings are accepted', () => {
  const state = parseSseFrames()
  assert.deepEqual(state.push('data: 1\r\n\r\n'), ['1'])
})

test('multi-line data is joined with newlines', () => {
  const state = parseSseFrames()
  assert.deepEqual(state.push('data: a\ndata: b\n\n'), ['a\nb'])
})

test('the done marker is not delivered as data', () => {
  const state = parseSseFrames()
  assert.deepEqual(state.push('data: [DONE]\n\n'), [])
  assert.equal(state.done, true)
})

test('frames without data are skipped', () => {
  const state = parseSseFrames()
  assert.deepEqual(state.push(': keep-alive\n\n'), [])
  assert.deepEqual(state.push('event: ping\n\n'), [])
})

test('a frame split across two chunks is joined', () => {
  const state = parseSseFrames()
  assert.deepEqual(state.push('data: {"n'), [])
  assert.deepEqual(state.push('umber":2}\n\n'), ['{"number":2}'])
})
