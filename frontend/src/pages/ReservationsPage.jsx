import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api.js'
import { isLoggedIn } from '../auth.js'
import { formatSlotTime } from '../holds.js'
import { listMyReservations } from '../reservations.js'

/** hold_7 and res_7 are the same row — open the hold page for countdown + Confirm. */
function holdPathFromReservationId(reservationId) {
  return `/holds/${reservationId.replace(/^res_/, 'hold_')}`
}

function ReservationRow({ reservation: r }) {
  const body = (
    <>
      <span className="reservation-where">
        {r.laundromatName} · {r.machineLabel}
      </span>
      <span className="reservation-when">{formatSlotTime(r.startTime, r.endTime)}</span>
      <span className={`reservation-status status-${r.status.toLowerCase()}`}>{r.status}</span>
      {r.status === 'HELD' && (
        <span className="reservation-action">Open to see the timer and confirm</span>
      )}
    </>
  )

  if (r.status === 'HELD') {
    return (
      <li>
        <Link to={holdPathFromReservationId(r.reservationId)} className="reservation-item reservation-link">
          {body}
        </Link>
      </li>
    )
  }

  return <li className="reservation-item">{body}</li>
}

/** /reservations — only the caller's bookings (US-4.3). */
export function ReservationsPage() {
  const [reservations, setReservations] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!isLoggedIn()) {
      return undefined
    }
    let cancelled = false
    listMyReservations()
      .then((data) => {
        if (!cancelled) setReservations(data.reservations)
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : 'Could not load reservations.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (!isLoggedIn()) {
    return (
      <section className="page form-page">
        <p className="kicker">Account</p>
        <h1>My reservations</h1>
        <div className="notice">
          <p>Log in to see your bookings.</p>
          <Link to={`/login?next=${encodeURIComponent('/reservations')}`}>Log in</Link>
        </div>
      </section>
    )
  }

  return (
    <section className="page">
      <p className="kicker">Account</p>
      <h1>My reservations</h1>
      <p className="lede">Only your bookings. Newest first. Tap a HELD row to confirm before it expires.</p>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      {reservations === null && !error && <p className="lede">Loading…</p>}

      {reservations && reservations.length === 0 && (
        <p className="lede">
          No reservations yet. <Link to="/laundromats">Browse laundromats</Link> to book a slot.
        </p>
      )}

      {reservations && reservations.length > 0 && (
        <ul className="reservation-list">
          {reservations.map((r) => (
            <ReservationRow key={r.reservationId} reservation={r} />
          ))}
        </ul>
      )}
    </section>
  )
}
