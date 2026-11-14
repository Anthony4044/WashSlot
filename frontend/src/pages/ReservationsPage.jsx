import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api.js'
import { isLoggedIn } from '../auth.js'
import { formatSlotTime } from '../holds.js'
import { listMyReservations } from '../reservations.js'

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
      <p className="lede">Only your bookings. Newest first.</p>

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
            <li key={r.reservationId} className="reservation-item">
              <span className="reservation-where">
                {r.laundromatName} · {r.machineLabel}
              </span>
              <span className="reservation-when">{formatSlotTime(r.startTime, r.endTime)}</span>
              <span className={`reservation-status status-${r.status.toLowerCase()}`}>{r.status}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
