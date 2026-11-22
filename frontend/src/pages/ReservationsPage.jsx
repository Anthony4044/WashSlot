import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api.js'
import { isLoggedIn } from '../auth.js'
import { formatSlotTime } from '../holds.js'
import { cancelReservation, checkInReservation, listMyReservations } from '../reservations.js'

/** hold_7 and res_7 are the same row — open the hold page for countdown + Confirm. */
function holdPathFromReservationId(reservationId) {
  return `/holds/${reservationId.replace(/^res_/, 'hold_')}`
}

function canCancel(reservation, now = Date.now()) {
  if (reservation.status !== 'CONFIRMED' && reservation.status !== 'HELD') {
    return false
  }
  return Date.parse(reservation.startTime) > now
}

function ReservationRow({ reservation: r, onCancel, onCheckIn, pending }) {
  const cancellable = canCancel(r)
  const disabled = pending !== null
  const ownAction = pending?.reservationId === r.reservationId ? pending.action : null

  const details = (
    <>
      <span className="reservation-where">
        {r.laundromatName} · {r.machineLabel}
      </span>
      <span className="reservation-when">{formatSlotTime(r.startTime, r.endTime)}</span>
      <span className={`reservation-status status-${r.status.toLowerCase()}`}>
        {r.status === 'CONFIRMED' && r.checkedInAt ? 'Checked in' : r.status}
      </span>
    </>
  )

  if (r.status === 'HELD') {
    return (
      <li className="reservation-item reservation-item-actions">
        <Link to={holdPathFromReservationId(r.reservationId)} className="reservation-main-link">
          {details}
          <span className="reservation-action">Open to see the timer and confirm</span>
        </Link>
        {cancellable && (
          <button type="button" className="button-secondary" disabled={disabled} onClick={() => onCancel(r)}>
            {ownAction === 'cancel' ? 'Cancelling…' : 'Cancel hold'}
          </button>
        )}
      </li>
    )
  }

  const cancelled = r.status === 'CANCELLED'

  return (
    <li
      className={`reservation-item reservation-item-actions${cancelled ? ' reservation-item-cancelled' : ''}`}
    >
      <div className="reservation-main">{details}</div>
      <div className="reservation-buttons">
        {r.status === 'CONFIRMED' && !r.checkedInAt && (
          <button type="button" className="button-secondary" disabled={disabled} onClick={() => onCheckIn(r)}>
            {ownAction === 'check-in' ? 'Checking in…' : "I'm here"}
          </button>
        )}
        {cancellable && (
          <button type="button" className="button-secondary" disabled={disabled} onClick={() => onCancel(r)}>
            {ownAction === 'cancel' ? 'Cancelling…' : 'Cancel'}
          </button>
        )}
      </div>
    </li>
  )
}

/** The customer's bookings, cancellation and check-in. */
export function ReservationsPage() {
  const [reservations, setReservations] = useState(null)
  const [error, setError] = useState(null)
  const [pending, setPending] = useState(null)

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

  async function onCancel(reservation) {
    const when = formatSlotTime(reservation.startTime, reservation.endTime)
    const ok = window.confirm(
      `Cancel this booking?\n\n${reservation.laundromatName} · ${reservation.machineLabel}\n${when}\n\nYou can only cancel before the slot starts.`,
    )
    if (!ok) {
      return
    }
    setPending({ reservationId: reservation.reservationId, action: 'cancel' })
    setError(null)
    try {
      await cancelReservation(reservation.reservationId)
      setReservations((list) =>
        list.map((item) =>
          item.reservationId === reservation.reservationId ? { ...item, status: 'CANCELLED' } : item,
        ),
      )
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not cancel.')
    } finally {
      setPending(null)
    }
  }

  async function onCheckIn(reservation) {
    const { reservationId } = reservation
    setPending({ reservationId, action: 'check-in' })
    setError(null)
    try {
      const checkedIn = await checkInReservation(reservationId)
      setReservations((list) => list.map((item) => item.reservationId === reservationId ? checkedIn : item))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not check in.')
    } finally {
      setPending(null)
    }
  }

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
      <p className="lede">
        Only your bookings. Newest first. Tap HELD to confirm. Cancel a booking any time before its
        start.
      </p>

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
            <ReservationRow
              key={r.reservationId}
              reservation={r}
              onCancel={onCancel}
              onCheckIn={onCheckIn}
              pending={pending}
            />
          ))}
        </ul>
      )}
    </section>
  )
}
