import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '../api.js'
import { confirmHold, formatCountdown, formatSlotTime, getHold, secondsLeft } from '../holds.js'

/** /holds/:holdId (US-4.2): the hold's details, a countdown to expiresAt, and "Confirm". */
export function HoldReviewPage() {
  const { holdId } = useParams()
  const navigate = useNavigate()
  // What the last request returned, tagged with its holdId so a stale answer is never shown.
  const [loaded, setLoaded] = useState(null)
  const [confirmError, setConfirmError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    let cancelled = false
    getHold(holdId)
      .then((hold) => !cancelled && setLoaded({ holdId, hold }))
      .catch((err) => {
        if (!cancelled) {
          setLoaded({ holdId, error: err instanceof ApiError ? err : new ApiError(null, 0) })
        }
      })
    return () => {
      cancelled = true
    }
  }, [holdId])

  const current = loaded?.holdId === holdId ? loaded : null
  const hold = current?.hold ?? null
  const loadError = current?.error ?? null
  const ticking = hold?.status === 'HELD'
  useEffect(() => {
    if (!ticking) {
      return undefined
    }
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [ticking])

  async function onConfirm() {
    setBusy(true)
    setConfirmError(null)
    try {
      await confirmHold(holdId)
      navigate('/reservations')
    } catch (err) {
      if (err instanceof ApiError && err.code === 'hold_expired') {
        setLoaded((l) => ({ ...l, hold: { ...l.hold, status: 'EXPIRED' } }))
      } else {
        setConfirmError(err instanceof ApiError ? err.message : 'Something went wrong.')
      }
      setBusy(false)
    }
  }

  if (loadError) {
    return (
      <section className="page form-page">
        <h1>Hold not found</h1>
        <p className="form-error" role="alert">
          {loadError.code === 'not_found' ? 'We could not find this hold.' : loadError.message}
        </p>
        <p className="form-footer">
          <Link to="/laundromats">Back to laundromats</Link>
        </p>
      </section>
    )
  }

  if (!hold) {
    return (
      <section className="page form-page" aria-busy="true">
        <p className="lede">Loading your hold…</p>
      </section>
    )
  }

  const left = secondsLeft(hold.expiresAt, now)
  const expired = hold.status === 'EXPIRED' || (hold.status === 'HELD' && left === 0)
  const gridLink = `/laundromats/${hold.laundromatId}`

  return (
    <section className="page form-page">
      <p className="kicker">Your hold</p>
      <h1>
        {hold.machineLabel} at {hold.laundromatName}
      </h1>

      <dl className="details">
        <dt>When</dt>
        <dd>{formatSlotTime(hold.startTime, hold.endTime)}</dd>
        <dt>Machine</dt>
        <dd>
          {hold.machineLabel} ({hold.machineType === 'DRYER' ? 'dryer' : 'washer'})
        </dd>
        <dt>Confirmation to</dt>
        <dd>{hold.confirmationEmail}</dd>
      </dl>

      {hold.status === 'HELD' && !expired && (
        <>
          <p className="countdown" role="timer" aria-label="Time left to confirm">
            <span className="countdown-time">{formatCountdown(left)}</span> left to confirm
          </p>
          {confirmError && (
            <p className="form-error" role="alert">
              {confirmError}
            </p>
          )}
          <button type="button" className="button" onClick={onConfirm} disabled={busy}>
            {busy ? 'Confirming…' : 'Confirm'}
          </button>
        </>
      )}

      {expired && (
        <div className="notice" role="alert">
          <p>
            <strong>Hold expired.</strong> The 10 minutes ran out, so the slot is free for anyone again.
          </p>
          <Link to={gridLink}>Pick a slot again</Link>
        </div>
      )}

      {(hold.status === 'CONFIRMED' || hold.status === 'NO_SHOW') && (
        <div className="notice">
          <p>
            <strong>Already confirmed.</strong>
          </p>
          <Link to="/reservations">See my reservations</Link>
        </div>
      )}

      {hold.status === 'CANCELLED' && (
        <div className="notice">
          <p>
            <strong>This reservation was cancelled.</strong>
          </p>
          <Link to={gridLink}>Pick another slot</Link>
        </div>
      )}
    </section>
  )
}
