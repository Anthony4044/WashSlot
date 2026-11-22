/**
 * Operator tools: my laundromats, their machines, the reservable switch, create slots (US-7.1), today's
 * bookings (US-7.2) and failed emails (US-7.3). Shapes are in the contract.
 */
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

/**
 * GET /operator/notifications (US-7.3). `status` is 'FAILED', 'PENDING', 'SENT' or empty for all.
 * Resolves to { notifications: [...] }, newest first: only the emails of the laundromats I operate.
 */
export function listNotifications(status) {
  const query = status ? `?status=${encodeURIComponent(status)}` : ''
  return api(`/operator/notifications${query}`)
}

/**
 * POST /operator/notifications/:id/retry. Resolves to the Notification as it is now (PENDING after a
 * retry; the worker sends it within seconds). Idempotent: retrying twice never sends it twice.
 */
export function retryNotification(notificationId) {
  return api(`/operator/notifications/${encodeURIComponent(notificationId)}/retry`, { method: 'POST' })
}

/** "Fri, Nov 27 · 6:00 PM – 7:00 PM" in the laundromat's time zone (not this computer's). */
export function formatInZone(startTime, endTime, timeZone) {
  const start = new Date(startTime)
  const day = start.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', timeZone })
  const time = { hour: 'numeric', minute: '2-digit', timeZone }
  return `${day} · ${start.toLocaleTimeString(undefined, time)} – ${new Date(endTime).toLocaleTimeString(undefined, time)}`
}

/** "YYYY-MM-DD" for today plus `days`, on this computer's calendar (the form's default dates). */
export function isoDay(days = 0, now = new Date()) {
  const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() + days)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
