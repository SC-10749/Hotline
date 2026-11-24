import test from 'node:test'
import assert from 'node:assert/strict'
import { matrixCellText, matrixChangeLabel, matrixRunSelection } from './matrix.js'

test('a matrix cell shows the verdict and score', () => {
  assert.equal(matrixCellText({ verdict: 'passed', score: 0.9 }), '通过 0.90')
})

test('a cell without a verdict shows a dash', () => {
  assert.equal(matrixCellText({ verdict: '', score: 0 }), '—')
})

test('a flaky cell is labelled as flaky', () => {
  assert.equal(matrixCellText({ verdict: 'flaky', score: 0.5 }), '不稳定 0.50')
})

test('changes are labelled in Chinese', () => {
  assert.equal(matrixChangeLabel('improved'), '变好')
  assert.equal(matrixChangeLabel('regressed'), '退化')
  assert.equal(matrixChangeLabel('unchanged'), '持平')
  assert.equal(matrixChangeLabel('added'), '新增')
  assert.equal(matrixChangeLabel('removed'), '缺失')
  assert.equal(matrixChangeLabel(''), '')
})

test('selection keeps the base run first and caps at eight runs', () => {
  const picked = matrixRunSelection(['eval-a', 'eval-b'], 'eval-c')
  assert.deepEqual(picked, ['eval-a', 'eval-b', 'eval-c'])

  let many = ['eval-0']
  for (let index = 1; index < 9; index += 1) many = matrixRunSelection(many, `eval-${index}`)
  assert.equal(many.length, 8)
})

test('selecting an already picked run removes it', () => {
  assert.deepEqual(matrixRunSelection(['eval-a', 'eval-b'], 'eval-a'), ['eval-b'])
})
