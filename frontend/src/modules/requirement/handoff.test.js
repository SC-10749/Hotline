import test from 'node:test'
import assert from 'node:assert/strict'
import { handoffFor, recommendationLabel } from './handoff.js'

test('a plain recommendation keeps its text', () => {
  assert.equal(recommendationLabel('请进一步解释：做个工单系统'), '请进一步解释：做个工单系统')
})

test('a structured recommendation shows its label', () => {
  assert.equal(recommendationLabel({ label: '按 TDD 把这些需求写成测试', skill: 'hotline-tdd' }),
    '按 TDD 把这些需求写成测试')
})

test('a structured recommendation hands over to the named skill', () => {
  const handoff = handoffFor({ label: '按 TDD 把这些需求写成测试', skill: 'hotline-tdd' })

  assert.equal(handoff.mode, 'skills')
  assert.equal(handoff.skill, 'hotline-tdd')
  assert.equal(handoff.query, '按 TDD 把这些需求写成测试')
})

test('a plain recommendation is not a handover', () => {
  assert.equal(handoffFor('给出一个实际案例'), null)
})
