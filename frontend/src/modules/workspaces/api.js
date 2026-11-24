import { unwrap, apiUrl } from '../../core/http.js'
import { apiFetch } from '../auth/token.js'

export async function getHarnessWorkspaceRuns(base, workspaceId) {
  const response = await apiFetch(apiUrl(base, `/harness/workspaces/${encodeURIComponent(workspaceId)}/runs`), {
    signal: AbortSignal.timeout(8000),
  })
  return unwrap(response)
}

export async function createHarnessWorkspaceSnapshot(base, workspaceId) {
  const response = await apiFetch(apiUrl(base, `/harness/workspaces/${encodeURIComponent(workspaceId)}/snapshots`), {
    method: 'POST', signal: AbortSignal.timeout(30000),
  })
  return unwrap(response)
}

export async function getHarnessWorkspaceSnapshots(base, workspaceId) {
  const response = await apiFetch(apiUrl(base, `/harness/workspaces/${encodeURIComponent(workspaceId)}/snapshots`), {
    signal: AbortSignal.timeout(8000),
  })
  return unwrap(response)
}

export async function getHarnessWorkspaceChanges(base, workspaceId, snapshotId) {
  const response = await apiFetch(apiUrl(base, `/harness/workspaces/${encodeURIComponent(workspaceId)}/snapshots/${encodeURIComponent(snapshotId)}/changes`), {
    signal: AbortSignal.timeout(8000),
  })
  return unwrap(response)
}

export async function getHarnessWorkspaces(base) {
  const response = await apiFetch(apiUrl(base, '/harness/workspaces'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getHarnessWorkspace(base, workspaceId) {
  const response = await apiFetch(apiUrl(base, `/harness/workspaces/${encodeURIComponent(workspaceId)}`), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function getWorkspaceFiles(base, workspaceId) {
  const response = await apiFetch(apiUrl(base, `/harness/workspaces/${encodeURIComponent(workspaceId)}/files`), {
    signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function updateHarnessWorkspace(base, workspaceId, payload) {
  const response = await apiFetch(apiUrl(base, `/harness/workspaces/${encodeURIComponent(workspaceId)}`), {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function createHarnessWorkspace(base, payload) {
  const response = await apiFetch(apiUrl(base, '/harness/workspaces'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15000) })
  return unwrap(response)
}

export async function getWorkspaceCheckout(base, workspaceId) {
  const response = await apiFetch(apiUrl(base, `/harness/workspaces/${encodeURIComponent(workspaceId)}/checkout`), {
    signal: AbortSignal.timeout(8000),
  })
  return unwrap(response)
}

export async function checkoutWorkspace(base, workspaceId) {
  const response = await apiFetch(apiUrl(base, `/harness/workspaces/${encodeURIComponent(workspaceId)}/checkout`), {
    method: 'POST',
    signal: AbortSignal.timeout(120000),
  })
  return unwrap(response)
}

export async function importWorkspace(base, name, entries) {
  const form = new FormData()
  form.append('name', name)
  for (const entry of entries) {
    const path = entry.path.replaceAll('\\', '/').split('/').slice(1).join('/') || entry.name
    form.append('files', entry.file, path)
  }
  const response = await apiFetch(apiUrl(base, '/harness/workspaces/import'), {
    method: 'POST', body: form, signal: AbortSignal.timeout(120000),
  })
  return unwrap(response)
}
