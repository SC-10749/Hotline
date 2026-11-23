import test from 'node:test'
import assert from 'node:assert/strict'
import { buildOptionPanel, composeOptionAnswer, extractQuestionOptions } from './question-options.js'

const message = [
  '第 2 轮，共 4 轮，把验收标准说清楚。',
  '',
  '1. 「不漏单」怎么算达标？',
  '   - 每条进来的需求都有归属人，没有「无人认领」超过 X 分钟',
  '   - 客户提的需求 100% 进系统，一条都不能只留在微信里',
  '   - 有超时未处理的单会自动提醒到人',
  '',
  '2. 「能找到人」指哪种？',
  '   - 看到工单就知道现在归谁，能直接找到这个人',
  '   - 能查到某个人手上现在有哪些单',
  '',
  '3. 用户故事',
  '   - 作为客服主管，我要看漏单情况',
  '   - FR-1 系统必须给每条需求记录归属人',
].join('\n')

test('pulls candidate answers out of the body and groups them by question', () => {
  const parsed = extractQuestionOptions(message)

  assert.equal(parsed.groups.length, 2)
  assert.equal(parsed.groups[0].question, '「不漏单」怎么算达标？')
  assert.equal(parsed.groups[0].options.length, 3)
  assert.equal(parsed.groups[1].question, '「能找到人」指哪种？')
  assert.equal(parsed.groups[1].options[0].label, '看到工单就知道现在归谁，能直接找到这个人')
  assert.equal(parsed.text.includes('客户提的需求 100% 进系统'), false)
  assert.equal(parsed.text.includes('「不漏单」怎么算达标？'), true)
  assert.equal(parsed.text.includes('第 2 轮，共 4 轮'), true)
})

test('keeps ordinary lists that are not candidate answers', () => {
  const parsed = extractQuestionOptions(message)

  assert.equal(parsed.text.includes('作为客服主管'), true)
  assert.equal(parsed.text.includes('FR-1 系统必须给每条需求记录归属人'), true)
})

test('a single bullet under a question is not an option group', () => {
  const parsed = extractQuestionOptions('1. 范围有多大？\n   - 只做客服内部')

  assert.equal(parsed.groups.length, 0)
  assert.equal(parsed.text.includes('只做客服内部'), true)
})

test('every question numbers its own options from A', () => {
  const panel = buildOptionPanel(extractQuestionOptions(message).groups)

  assert.equal(panel.length, 2)
  assert.deepEqual(panel[0].options.map(option => option.letter), ['A', 'B', 'C'])
  assert.deepEqual(panel[1].options.map(option => option.letter), ['A', 'B'])
  assert.equal(panel[0].options[0].key, '0:0')
  assert.equal(panel[1].options[0].key, '1:0')
})

test('the follow-up keeps every picked option with its question and letter', () => {
  const panel = buildOptionPanel(extractQuestionOptions(message).groups)
  const answer = composeOptionAnswer(panel, ['0:1', '1:0'])

  assert.equal(answer.includes('按 TDD 追问'), false)
  assert.match(answer, /「不漏单」怎么算达标？——B\. 客户提的需求 100% 进系统，一条都不能只留在微信里/)
  assert.match(answer, /「能找到人」指哪种？——A\. 看到工单就知道现在归谁，能直接找到这个人/)
  assert.equal(composeOptionAnswer(panel, []), '')
})
