import { useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '../api.js'
import { getEmail, isLoggedIn } from '../auth.js'
import { formatSlotTime, isUnknownOutcome, newAttemptKey, placeHold } from '../holds.js'

/**
 * /slots/:slotId/hold (US-4.1): show the slot, ask where to send the confirmation, "Hold this slot".
 *
 *   201 -> go to /holds/:holdId (US-4.2's page: countdown and "Confirm")
 *   409 -> "Someone just took this slot", with a link back to pick another one
 *
 * The page never decides whether the slot is free: the server does, with the slot row locked
 * (lecture Ch. 7). Two people can both see this page for the same slot; only one gets the 201.
 *
 * Slot details come from the availability grid (US-3.1), which links here with React Router state:
 *   <Link to={`/slots/${slotId}/hold`}
 *         state={{ laundromatId, laundromatName, machineLabel, machineType, startTime, endTime }}>
 * The contract has no "get one slot" operation, so if you open this URL directly we only know the slot id.
 *
 * Safe retries (US-5.2): one attempt = this slot + this email, named by one Idempotency-Key. The key
 * is kept until the attempt gets a final answer, so "Try again" after a network error or a 5xx sends
 * the SAME key, and the server replays the first hold if it did go through: never two holds.
 * Changing the email starts a new attempt with a new key.
 */
export function HoldPage() {
  const { slotId } = useParams()
  const slot = useLocation().state // the grid's details, or null when the URL was typed in
  const navigate = useNavigate()

  const [email, setEmail] = useState(() => getEmail()) // prefilled with the login email
  const [taken, setTaken] = useState(false) // true after a 409
  const [error, setError] = useState(null) // any other error, as a readable message
  const [busy, setBusy] = useState(false) // while the request is in flight (no double clicks)
  const [canRetry, setCanRetry] = useState(false) // the last failure was the network or the server
  const attempt = useRef(null) // { email, key } of the attempt in progress, or null

  const backLink = slot?.laundromatId ? `/laundromats/${slot.laundromatId}` : '/laundromats'
  const inThePast = slot?.startTime && Date.parse(slot.startTime) <= Date.now()

  async function onSubmit(event) {
    event.preventDefault()
    if (inThePast) {
      setError('That slot is already in the past. Pick a later time.')
      return
    }
    setBusy(true)
    setError(null)
    if (attempt.current?.email !== email) {
      attempt.current = { email, key: newAttemptKey() } // a new attempt: first click, or a new email
    }
    try {
      // 201 (or the replay of an earlier 201): the slot is ours for 10 minutes
      const hold = await placeHold(slotId, email, attempt.current.key)
      navigate(`/holds/${hold.holdId}`)
    } catch (err) {
      const retryable = isUnknownOutcome(err)
      if (!retryable) {
        attempt.current = null // a final answer: the next click is a new attempt
      }
      setCanRetry(retryable)
      if (err instanceof ApiError && err.code === 'slot_unavailable') {
        setTaken(true) // 409: past, or someone else holds / reserved it
      } else {
        setError(err instanceof ApiError ? err.message : 'Something went wrong.')
      }
      setBusy(false)
    }
  }

  function onEmailChange(value) {
    setEmail(value)
    setCanRetry(false) // a different email is a different attempt, so this is no longer a retry
  }

  // Holding needs a token (reservations:write). Send the user to log in, then back here.
  if (!isLoggedIn()) {
    return (
      <section className="page form-page">
        <h1>Hold this slot</h1>
        <div className="notice">
          <p>Log in to hold a slot.</p>
          <Link to={`/login?next=${encodeURIComponent(`/slots/${slotId}/hold`)}`}>Log in</Link>
        </div>
      </section>
    )
  }

  if (taken) {
    return (
      <section className="page form-page">
        <h1>Slot taken</h1>
        <div className="notice" role="alert">
          <p>
            <strong>That slot is not available.</strong> It may already be in the past, or someone
            else took it. Pick another one.
          </p>
          <Link to={backLink}>Back to the free slots</Link>
        </div>
      </section>
    )
  }

  if (inThePast) {
    return (
      <section className="page form-page">
        <h1>Slot in the past</h1>
        <div className="notice" role="alert">
          <p>
            <strong>You can’t reserve a time that already started.</strong> Pick a later slot.
          </p>
          <Link to={backLink}>Back to the free slots</Link>
        </div>
      </section>
    )
  }

  return (
    <section className="page form-page">
      <p className="kicker">Hold a slot</p>
      <h1>{slot ? `${slot.machineLabel} at ${slot.laundromatName}` : `Slot ${slotId}`}</h1>

      {slot && (
        <dl className="details">
          <dt>When</dt>
          <dd>{formatSlotTime(slot.startTime, slot.endTime)}</dd>
          <dt>Machine</dt>
          <dd>
            {slot.machineLabel} ({slot.machineType === 'DRYER' ? 'dryer' : 'washer'})
          </dd>
        </dl>
      )}

      <p className="lede">We keep it for you for 10 minutes while you confirm.</p>

      <form className="form" onSubmit={onSubmit}>
        <div className="field">
          <label htmlFor="hold-email">Send the confirmation to</label>
          <input
            id="hold-email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => onEmailChange(e.target.value)}
          />
        </div>

        {error && (
          <p className="form-error" role="alert">
            {error}
            {canRetry && ' Trying again is safe: you will never get two holds.'}
          </p>
        )}

        <button type="submit" className="button" disabled={busy}>
          {busy ? 'Holding…' : canRetry ? 'Try again' : 'Hold this slot'}
        </button>
      </form>

      <p className="form-footer">
        <Link to={backLink}>Back to the free slots</Link>
      </p>
    </section>
  )
}
