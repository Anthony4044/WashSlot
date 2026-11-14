/** My reservations (US-4.3). Shapes match the Reservation schema in the contract. */
import { api } from './api.js'

/** GET /me/reservations → { reservations: [...] } newest first. Needs reservations:read. */
export function listMyReservations() {
  return api('/me/reservations')
}

/** GET /reservations/:id. Someone else's is ApiError not_found. */
export function getReservation(reservationId) {
  return api(`/reservations/${encodeURIComponent(reservationId)}`)
}
