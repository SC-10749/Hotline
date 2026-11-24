import test from 'node:test'
import assert from 'node:assert/strict'
import { buildOptionPanel, extractQuestionOptions } from './question-options.js'

test('drops the letter prefix when the model wrote a bullet plus a letter', () => {
  const parsed = extractQuestionOptions([
    '1. 客户提的需求，现在是怎么进来的？',
    '   - A. 只有客服人工录入工单',
    '   - B. 客户自己在某个入口提交',
    '   - C. 电话、邮件、在线聊天都有',
  ].join('\n'))

  assert.equal(parsed.groups.length, 1)
  assert.equal(parsed.groups[0].options[0].label, '只有客服人工录入工单')
  assert.equal(parsed.groups[0].options[0].letter, 'A')
  assert.equal(parsed.groups[0].options[2].letter, 'C')

  const panel = buildOptionPanel(parsed.groups)
  assert.deepEqual(panel[0].options.map(option => option.letter), ['A', 'B', 'C'])
  assert.equal(panel[0].options[0].label, '只有客服人工录入工单')
})
