/** Holds: place one (US-4.1, safe retries US-5.2), look at it and confirm it (US-4.2). Shapes are the Hold and Reservation schemas in the contract. */
import { ApiError, api } from './api.js'

// Waits before the 2nd and 3rd try when the server or the network fails (5xx or no response).
const RETRY_DELAYS_MS = [500, 1500]

/**
 * A fresh Idempotency-Key naming ONE attempt to hold a slot. Make one per attempt, and send the
 * same one again for every retry of that attempt.
 */
export function newAttemptKey() {
  return crypto.randomUUID()
}

/**
 * True when we can't know whether the hold went through: no response at all, or a 5xx (CODING_GUIDE
 * §3: retry a 5xx with the same Idempotency-Key). A 4xx, like 409, is a final answer.
 */
export function isUnknownOutcome(err) {
  return err instanceof ApiError && (err.retryable || err.status === 0 || err.status >= 500)
}

/**
 * POST /slots/:slotId/holds. Resolves to the Hold; a taken slot is ApiError slot_unavailable (409).
 *
 * Placing a hold is NOT idempotent (each success takes a slot), so the contract requires an
 * Idempotency-Key that names this attempt. When the network or the server fails we can't tell
 * whether the hold went through, so we retry up to twice with the SAME key: if the first try did
 * succeed, the server replays that hold (Idempotency-Replayed: true) instead of taking a second one.
 * Any other error (409, 4xx) is a final answer and is never retried.
 */
export async function placeHold(slotId, confirmationEmail, idempotencyKey) {
  const send = () =>
    api(`/slots/${encodeURIComponent(slotId)}/holds`, {
      method: 'POST',
      body: { confirmationEmail },
      idempotencyKey,
    })
  for (const delay of RETRY_DELAYS_MS) {
    try {
      return await send()
    } catch (err) {
      if (!isUnknownOutcome(err)) {
        throw err
      }
      await new Promise((resolve) => setTimeout(resolve, delay))
    }
  }
  return send() // the last try: if it fails too, the page shows the error and a "Try again" button
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
