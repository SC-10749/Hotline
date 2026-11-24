import test from 'node:test'
import assert from 'node:assert/strict'
import { buildOptionPanel, composeOptionAnswer, extractQuestionOptions } from './question-options.js'

test('reads options the model wrote as A. / B. / C. under unnumbered questions', () => {
  const parsed = extractQuestionOptions([
    '客户提的需求，现在是怎么进来的？',
    'A. 只有客服人工录入工单',
    'B. 客户自己在某个入口提交',
    'C. 电话、邮件、在线聊天都有',
    'D. 以上都有',
    '',
    '什么情况算「漏单」？',
    'A. 客户提了，但系统里根本没建单',
    'B. 建了单，但一直没人认领',
    'C. 认领了，但超过约定时间没回复',
  ].join('\n'))

  assert.equal(parsed.groups.length, 2)
  assert.equal(parsed.groups[0].question, '客户提的需求，现在是怎么进来的？')
  assert.deepEqual(parsed.groups[0].options.map(item => item.label), [
    '只有客服人工录入工单', '客户自己在某个入口提交', '电话、邮件、在线聊天都有', '以上都有',
  ])
  assert.equal(parsed.groups[1].options[0].letter, 'A')
  assert.equal(parsed.text.includes('客户提了，但系统里根本没建单'), false)
  assert.equal(parsed.text.includes('什么情况算「漏单」？'), true)
})

test('the panel keeps the letter the model used', () => {
  const panel = buildOptionPanel(extractQuestionOptions([
    '什么情况算「漏单」？',
    'A. 客户提了，但系统里根本没建单',
    'B. 建了单，但一直没人认领',
  ].join('\n')).groups)

  assert.deepEqual(panel[0].options.map(option => option.letter), ['A', 'B'])
  assert.equal(panel[0].options[0].key, '0:0')
})

test('a bullet list without a question above stays in the body', () => {
  const parsed = extractQuestionOptions('- FR-1 系统必须给每条需求记录归属人\n- FR-2 系统必须支持按负责人筛选')

  assert.equal(parsed.groups.length, 0)
  assert.equal(parsed.text.includes('FR-2 系统必须支持按负责人筛选'), true)
})
