import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { parse, compileScript } from '@vue/compiler-sfc'

const srcRoot = join(dirname(fileURLToPath(import.meta.url)), '..', '..')

function collectComponents(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) collectComponents(full, out)
    else if (name.endsWith('.vue')) out.push(full)
  }
  return out
}

test('模板里的每个标识符都有绑定，不会渲染成空白页', () => {
  const problems = []
  let index = 0
  for (const file of collectComponents(srcRoot)) {
    const { descriptor } = parse(readFileSync(file, 'utf-8'), { filename: file })
    if (!descriptor.template) continue
    index += 1
    const code = compileScript(descriptor, { id: 'binding-check-' + index, inlineTemplate: true }).content
    const unresolved = new Set()
    const pattern = /_ctx\.([A-Za-z_$][\w$]*)/g
    let match
    while ((match = pattern.exec(code))) {
      if (match[1] === '$emit' || match[1] === '$refs') continue
      unresolved.add(match[1])
    }
    if (unresolved.size) {
      problems.push(relative(srcRoot, file) + ' -> ' + [...unresolved].sort().join(', '))
    }
  }
  assert.deepEqual(problems, [], '模板里有未定义的绑定：\n' + problems.join('\n'))
})
