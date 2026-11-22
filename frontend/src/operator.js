/** Operator tools (US-7.1): my laundromats, their machines, the reservable switch, create slots. Shapes are in the contract. */
import { api } from './api.js'

const lm = (laundromatId) => `/operator/laundromats/${encodeURIComponent(laundromatId)}`

/** GET /operator/laundromats. Resolves to { laundromats: [...] }: only the ones I operate. */
export function listMyLaundromats() {
  return api('/operator/laundromats')
}

/** GET /operator/laundromats/:id/today. Returns the bookings for the laundromat's local day. */
export function listTodaysBookings(laundromatId) {
  return api(`${lm(laundromatId)}/today`)
}

/** GET /operator/laundromats/:id/machines. Resolves to { machines: [{ machineId, label, type, reservable }] }. */
export function listMachines(laundromatId) {
  return api(`${lm(laundromatId)}/machines`)
}

/** PATCH .../machines/:machineId. Resolves to the Machine. Idempotent, so retrying is safe. */
export function setReservable(laundromatId, machineId, reservable) {
  return api(`${lm(laundromatId)}/machines/${encodeURIComponent(machineId)}`, {
    method: 'PATCH',
    body: { reservable },
  })
}

/**
 * POST .../slots. `request` is { fromDate, toDate, openTime, closeTime, slotMinutes, machineIds? }
 * (no machineIds: every reservable machine). Resolves to { created, skipped }. Idempotent.
 */
export function createSlots(laundromatId, request) {
  return api(`${lm(laundromatId)}/slots`, { method: 'POST', body: request })
}

/** "YYYY-MM-DD" for today plus `days`, on this computer's calendar (the form's default dates). */
export function isoDay(days = 0, now = new Date()) {
  const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() + days)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
