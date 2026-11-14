/** Browse laundromats and availability (US-3.1). Public — no token. */
import { api } from './api.js'

/** GET /laundromats → { laundromats: [...] } */
export function listLaundromats() {
  return api('/laundromats')
}

/** GET /laundromats/:id/slots?date=YYYY-MM-DD → { machines: [...] } */
export function listSlots(laundromatId, date) {
  const params = new URLSearchParams({ date })
  return api(`/laundromats/${encodeURIComponent(laundromatId)}/slots?${params}`)
}

/** Local calendar date as YYYY-MM-DD. */
export function todayDateInputValue(now = new Date()) {
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

/** Slot start as a short time label, e.g. "6:00 PM". */
export function formatSlotHour(startTime) {
  return new Date(startTime).toLocaleTimeString(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  })
}
