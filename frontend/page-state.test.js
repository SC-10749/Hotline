import assert from 'node:assert/strict'
import { effectScope } from 'vue'
import { usePageState } from './src/composables/usePageState.js'

const values = new Map()
const storage = () => ({ getItem: key => values.get(key), setItem: (key, value) => values.set(key, value) })
const choices = ['home', 'harness', 'docs']
function mount(key = 'page', allowed = choices, access = storage) {
  const scope = effectScope()
  const state = scope.run(() => usePageState(key, allowed[0], allowed, access))
  return { state, unmount: () => scope.stop() }
}

for (const page of choices) {
  const first = mount()
  first.state.value = page
  first.unmount()
  const refreshed = mount()
  assert.equal(refreshed.state.value, page, `refresh restores ${page}`)
  refreshed.unmount()
}
const parent = mount()
parent.state.value = 'harness'
const child = mount('evaluation-tab', ['overview', 'rag', 'bird', 'load'])
child.state.value = 'rag'
child.unmount()
const restoredChild = mount('evaluation-tab', ['overview', 'rag', 'bird', 'load'])
assert.equal(restoredChild.state.value, 'rag')
assert.equal(parent.state.value, 'harness')
parent.unmount()
restoredChild.unmount()

values.set('hotline-navigation:page', 'removed-page')
const invalid = mount()
assert.equal(invalid.state.value, 'home')
invalid.unmount()
const blocked = mount('blocked', choices, () => { throw new Error('Storage disabled') })
assert.equal(blocked.state.value, 'home')
blocked.state.value = 'docs'
assert.equal(blocked.state.value, 'docs')
blocked.unmount()
console.log('Page restoration, nested tabs, stale values and blocked storage passed.')
