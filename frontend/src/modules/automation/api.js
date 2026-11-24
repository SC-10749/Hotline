import { unwrap, apiUrl } from '../../core/http.js'
import { apiFetch } from '../auth/token.js'

export async function getSchedules(base) {
  const response = await apiFetch(apiUrl(base, '/harness/schedules'), { signal: AbortSignal.timeout(8000) })
  return unwrap(response)
}

export async function createSchedule(base, payload) {
  const response = await apiFetch(apiUrl(base, '/harness/schedules'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function updateSchedule(base, taskId, payload) {
  const response = await apiFetch(apiUrl(base, `/harness/schedules/${encodeURIComponent(taskId)}`), {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function deleteSchedule(base, taskId) {
  const response = await apiFetch(apiUrl(base, `/harness/schedules/${encodeURIComponent(taskId)}`), {
    method: 'DELETE', signal: AbortSignal.timeout(15000),
  })
  return unwrap(response)
}

export async function runSchedule(base, taskId) {
  const response = await apiFetch(apiUrl(base, `/harness/schedules/${encodeURIComponent(taskId)}/run`), {
    method: 'POST', signal: AbortSignal.timeout(30000),
  })
  return unwrap(response)
}
