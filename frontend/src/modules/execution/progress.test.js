import test from 'node:test'
import assert from 'node:assert/strict'
import { appendProgressEvent, finishProgress, progressEntryLabel, progressLabel } from './progress.js'

const message = () => ({ timeline: [], content: '' })

test('initial progress and backend acknowledgement share one step', () => {
  const state = message()
  const event = { type: 'step', stage: 'understanding', content: '正在理解问题', status: 'running' }
  appendProgressEvent(state, event, 100)
  appendProgressEvent(state, event, 110)
  assert.equal(state.timeline.length, 1)
  assert.equal(progressLabel(state), '正在理解问题')
})

test('rewriting appears only when its event is received', () => {
  const state = message()
  appendProgressEvent(state, { type: 'step', stage: 'understanding', status: 'running' }, 100)
  assert.equal(state.timeline.some(item => item.stage === 'query_rewrite'), false)
  appendProgressEvent(state, { type: 'step', stage: 'query_rewrite', status: 'running' }, 120)
  assert.equal(progressLabel(state), '正在改写问题')
  assert.equal(state.timeline[0].status, 'completed')
})

test('completed phases update existing entries after nested work', () => {
  const state = message()
  appendProgressEvent(state, { type: 'step', stage: 'retrieval', status: 'running' }, 100)
  appendProgressEvent(state, { type: 'step', stage: 'text2sql', status: 'running' }, 110)
  appendProgressEvent(state, { type: 'step', stage: 'retrieval', content: '已找到 3 条片段', durationMs: 50 }, 150)
  assert.equal(state.timeline.length, 2)
  assert.equal(state.timeline[0].content, '已找到 3 条片段')
  assert.equal(state.timeline[0].t0, 100)
})

test('document names and search sources stay visible', () => {
  const state = message()
  appendProgressEvent(state, { type: 'step', stage: 'retrieval_request', content: '正在检索《操作手册.pdf》', status: 'running' }, 100)
  assert.match(progressLabel(state), /操作手册.pdf/)
  appendProgressEvent(state, { type: 'step', stage: 'web_search', content: '已找到参考资料', details: { documents: ['操作手册', null] } }, 120)
  assert.deepEqual(state.timeline.at(-1).sources, ['操作手册'])
})

test('concurrent tool calls keep their identities and failure states', () => {
  const state = message()
  appendProgressEvent(state, { type: 'tool_start', toolCallId: 'a', toolName: 'read_skill', arguments: { skill_id: 'doc-review' } }, 100)
  appendProgressEvent(state, { type: 'tool_start', toolCallId: 'b', toolName: 'document_search' }, 110)
  appendProgressEvent(state, { type: 'tool_end', toolCallId: 'b', status: 'failed', durationMs: 20 }, 130)
  assert.equal(state.timeline[1].status, 'failed')
  assert.equal(state.timeline[1].t0, 110)
  assert.equal(progressLabel(state), '正在读取技能「doc-review」')
  appendProgressEvent(state, { type: 'tool_end', toolCallId: 'a', toolName: 'read_skill', status: 'completed' }, 150)
  appendProgressEvent(state, { type: 'tool_start', toolCallId: 'a', toolName: 'read_skill' }, 160)
  assert.equal(state.timeline.length, 2)
  assert.equal(state.timeline[0].status, 'completed')
})

test('text streaming updates the current label and terminal events close all steps', () => {
  const state = message()
  appendProgressEvent(state, { type: 'step', stage: 'llm', status: 'running' }, 100)
  state.pendingText = '回答'
  assert.equal(progressLabel(state), '正在生成回答')
  finishProgress(state, 'cancelled', 130)
  assert.equal(state.timeline[0].endedAt, 130)
  assert.equal(state.timeline[0].status, 'cancelled')
  assert.equal(progressEntryLabel(state.timeline[0]), '组织回答')
})

test('legacy startup events remain readable and unrelated events pass through', () => {
  const state = message()
  appendProgressEvent(state, { type: 'thinking', content: '正在启动 chat 智能体...' }, 100)
  assert.equal(progressLabel(state), '正在理解问题')
  assert.equal(appendProgressEvent(state, { type: 'text', content: '回答' }), false)
})
