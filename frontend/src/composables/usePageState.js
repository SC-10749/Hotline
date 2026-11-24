import { ref, watch } from 'vue'

// Navigation belongs to this browser tab; no form contents or credentials are stored.
export function usePageState(key, fallback, choices, storage = () => window.sessionStorage) {
  const storageKey = `hotline-navigation:${key}`
  let initial = fallback
  try {
    const saved = storage().getItem(storageKey)
    if (choices.includes(saved)) initial = saved
  } catch { /* Navigation still works when browser storage is unavailable. */ }
  const state = ref(initial)
  watch(state, value => {
    try {
      storage().setItem(storageKey, choices.includes(value) ? value : fallback)
    } catch { /* Storage restrictions must not prevent switching pages. */ }
  }, { flush: 'sync' })
  return state
}
