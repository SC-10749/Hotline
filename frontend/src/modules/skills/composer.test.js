import test from 'node:test'
import assert from 'node:assert/strict'
import { skillComposerCopy } from './composer.js'

test('the skill assistant takes over the bottom composer', () => {
  const copy = skillComposerCopy('skills')

  assert.equal(copy.bar.includes('技能接手'), true)
  assert.equal(copy.placeholder, '在这里回复技能助手…')
  assert.equal(copy.hintLabel, '技能助手模式')
  assert.equal(copy.hintKey, 'Enter')
})

test('other modes leave the bottom composer alone', () => {
  assert.equal(skillComposerCopy('chat'), null)
  assert.equal(skillComposerCopy('file'), null)
  assert.equal(skillComposerCopy('ppt'), null)
  assert.equal(skillComposerCopy('deep'), null)
})
