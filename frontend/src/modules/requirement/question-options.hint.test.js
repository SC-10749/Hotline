import test from 'node:test'
import assert from 'node:assert/strict'
import { buildOptionPanel, composeOptionAnswer, extractQuestionOptions } from './question-options.js'

test('keeps the question itself and drops a trailing hint after the question mark', () => {
  const parsed = extractQuestionOptions([
    '1. 客户需求从哪些渠道进来？（可多选）',
    '   - 只有电话/在线客服人工录入',
    '   - 人工录入 + 邮件',
    '   - 以上都有，还有别的',
  ].join('\n'))

  assert.equal(parsed.groups.length, 1)
  assert.equal(parsed.groups[0].question, '客户需求从哪些渠道进来？')
  assert.equal(parsed.groups[0].options.length, 3)
  assert.equal(parsed.text.includes('人工录入 + 邮件'), false)
  assert.equal(parsed.text.includes('客户需求从哪些渠道进来？'), true)
})

test('a numbered line without a question mark is not a question', () => {
  const parsed = extractQuestionOptions('1. 用户故事\n   - 作为客服主管，我要看漏单情况\n   - FR-1 系统必须给每条需求记录归属人')

  assert.equal(parsed.groups.length, 0)
  assert.equal(parsed.text.includes('FR-1 系统必须给每条需求记录归属人'), true)
})
