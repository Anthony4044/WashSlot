/** My reservations (US-4.3) and cancel (US-5.3). Shapes match the contract. */
import { api } from './api.js'

/** GET /me/reservations → { reservations: [...] } newest first. Needs reservations:read. */
export function listMyReservations() {
  return api('/me/reservations')
}

/** GET /reservations/:id. Someone else's is ApiError not_found. */
export function getReservation(reservationId) {
  return api(`/reservations/${encodeURIComponent(reservationId)}`)
}

/**
 * DELETE /reservations/:id → 204. Only before the slot starts.
 * Already cancelled is also 204. too_late_to_cancel → 409.
 */
export function cancelReservation(reservationId) {
  return api(`/reservations/${encodeURIComponent(reservationId)}`, { method: 'DELETE' })
}
