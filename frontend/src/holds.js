/** Holds: place one (US-4.1), look at it and confirm it (US-4.2). Shapes are the Hold and Reservation schemas in the contract. */
import { api } from './api.js'

/**
 * POST /slots/:slotId/holds. Resolves to the Hold; a taken slot is ApiError slot_unavailable (409).
 *
 * Placing a hold is NOT idempotent (each success takes a slot), so the contract requires an
 * Idempotency-Key that names this one attempt. We make a fresh random one per click. (US-5.2 will
 * keep the same key when the browser retries the same attempt, so a retry can't take a second slot.)
 */
export function placeHold(slotId, confirmationEmail) {
  return api(`/slots/${encodeURIComponent(slotId)}/holds`, {
    method: 'POST',
    body: { confirmationEmail },
    idempotencyKey: crypto.randomUUID(),
  })
}

/** GET /holds/:holdId. Resolves to the Hold; someone else's or unknown hold is ApiError not_found. */
export function getHold(holdId) {
  return api(`/holds/${encodeURIComponent(holdId)}`)
}

/**
 * POST /holds/:holdId/confirm. Resolves to the Reservation.
 * Naturally idempotent on the server, so retrying after a network error is safe.
 */
export function confirmHold(holdId) {
  return api(`/holds/${encodeURIComponent(holdId)}/confirm`, { method: 'POST' })
}

/** Whole seconds left until expiresAt (never below 0). Display only: the server's clock decides. */
export function secondsLeft(expiresAt, now = Date.now()) {
  return Math.max(0, Math.ceil((Date.parse(expiresAt) - now) / 1000))
}

/** 125 -> "2:05" */
export function formatCountdown(seconds) {
  const minutes = Math.floor(seconds / 60)
  return `${minutes}:${String(seconds % 60).padStart(2, '0')}`
}

/** "Fri, Nov 20 · 6:00 – 7:00 PM" in the viewer's time zone. */
export function formatSlotTime(startTime, endTime) {
  const start = new Date(startTime)
  const day = start.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
  const time = { hour: 'numeric', minute: '2-digit' }
  return `${day} · ${start.toLocaleTimeString(undefined, time)} – ${new Date(endTime).toLocaleTimeString(undefined, time)}`
}
