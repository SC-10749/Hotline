import test from 'node:test'
import assert from 'node:assert/strict'
import { datasetCardView, failureKindLabel, relativeTime, runOptionLabel } from './readability.js'

const NOW = Date.parse('2026-11-23T12:00:00Z')

test('relative time understands the sqlite timestamp format', () => {
  assert.equal(relativeTime('2026-11-23 11:30:00', NOW), '30 分钟前')
  assert.equal(relativeTime('2026-11-23T11:59:30Z', NOW), '刚刚')
  assert.equal(relativeTime('', NOW), '—')
})

test('a run label shows agent, dataset, pass rate, epochs and time', () => {
  const label = runOptionLabel(
    { eval_run_id: 'eval-1', agent: 'chat', status: 'completed', epochs: 2,
      created_at: '2026-11-23 11:30:00', summary: { passRate: 0.5 } },
    '客服问答', NOW)
  assert.equal(label, '对话助手 · 客服问答 · 通过率 50.0% · 2 轮 · 30 分钟前')
})

test('a run without a summary still gets a readable label', () => {
  const label = runOptionLabel({ eval_run_id: 'eval-2', agent: 'skills', status: 'running' }, '', NOW)
  assert.equal(label, '技能助手 · eval-2 · 运行中')
})

test('a dataset card shows the real last run', () => {
  const view = datasetCardView(
    { dataset_id: 'd1', name: 'A', updated_at: '2026-11-23 08:00:00' },
    { status: 'completed', passRate: 0.5, createdAt: '2026-11-23 11:30:00' }, NOW)
  assert.equal(view.pass, '50.0%')
  assert.equal(view.state, '需关注')
  assert.equal(view.updated, '30 分钟前')
})

test('a dataset without a run is marked as not run', () => {
  const view = datasetCardView({ dataset_id: 'd1', name: 'A' }, null, NOW)
  assert.equal(view.pass, '—')
  assert.equal(view.state, '未运行')
})

test('a running dataset is marked as running', () => {
  const view = datasetCardView({ dataset_id: 'd1', name: 'A' }, { status: 'running' }, NOW)
  assert.equal(view.state, '运行中')
})

test('new failure kinds have Chinese labels', () => {
  assert.equal(failureKindLabel('missing_keyword'), '缺少关键词')
  assert.equal(failureKindLabel('semantic_mismatch'), '语义不达标')
  assert.equal(failureKindLabel('execution_error'), '执行异常')
  assert.equal(failureKindLabel('unknown'), '未知原因')
})
