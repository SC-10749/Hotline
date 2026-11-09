import assert from 'node:assert/strict'
import test from 'node:test'
import { workspacePathAllowed } from './paths.js'
import { streamUrl } from '../../api.js'

test('workspace imports exclude private and dependency paths', () => {
  for (const path of ['project/.env', 'project/.ENV.backup', 'project/settings.local.json',
    'project/private/notes.md', 'project/secrets/key.txt', 'project/node_modules/a.js',
    'project/tls/server.pem', '../outside.md', '/absolute.md', 'C:\\private.txt']) {
    assert.equal(workspacePathAllowed(path), false, path)
  }
  assert.equal(workspacePathAllowed('project/AGENTS.md'), true)
  assert.equal(workspacePathAllowed('project/docs/guide.md'), true)
})

test('all chat modes carry the selected workspace id', () => {
  for (const mode of ['chat', 'file', 'ppt', 'deep', 'skills']) {
    const url = new URL(streamUrl('http://127.0.0.1', mode, 'fixture', 'session', null, 'workspace-fixture'))
    assert.equal(url.searchParams.get('workspaceId'), 'workspace-fixture')
  }
  const legacy = new URL(streamUrl('http://127.0.0.1', 'chat', 'fixture', 'session', null))
  assert.equal(legacy.searchParams.has('workspaceId'), false)
})
