import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { isLoggedIn } from '../auth.js'
import { formatSlotHour } from '../browse.js'
import { listOperatorLaundromats, listTodaysBookings } from '../operator.js'

function TodayBookings({ laundromat }) {
  const [bookings, setBookings] = useState(null)
  const [error, setError] = useState(null)
  const [refresh, setRefresh] = useState(0)
  const { laundromatId, timezone } = laundromat

  useEffect(() => {
    let active = true
    listTodaysBookings(laundromatId)
      .then((data) => {
        if (active) setBookings(data)
      })
      .catch((err) => {
        if (active) setError(err.message)
      })
    return () => { active = false }
  }, [laundromatId, refresh])

  function reload() {
    setBookings(null)
    setError(null)
    setRefresh((count) => count + 1)
  }

  return (
    <div className="today-bookings">
      <button type="button" className="button-secondary" onClick={reload} disabled={!bookings && !error}>
        Refresh bookings
      </button>
      {error && <p className="form-error" role="alert">{error}</p>}
      {!error && !bookings && <p role="status">Loading bookings…</p>}
      {bookings && (
        <>
          <p className="reservation-when"><time dateTime={bookings.date}>{bookings.date}</time> · {timezone}</p>
          {bookings.reservations.length === 0 ? (
            <p>No bookings today.</p>
          ) : (
            <ul className="reservation-list">
              {bookings.reservations.map((booking) => (
                <li key={booking.reservationId} className="reservation-item">
                  <span className="reservation-where">{booking.machineLabel}</span>
                  <span className="reservation-when">
                    {formatSlotHour(booking.startTime, timezone)} – {formatSlotHour(booking.endTime, timezone)}
                  </span>
                  <span>{booking.customerEmail}</span>
                  <span className={`reservation-status status-${booking.status.toLowerCase()}`}>
                    {booking.status === 'NO_SHOW'
                      ? 'No-show'
                      : booking.checkedInAt
                        ? `Checked in at ${formatSlotHour(booking.checkedInAt, timezone)}`
                        : 'Awaiting check-in'}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}

export function OperatorTodayPage() {
  const [laundromats, setLaundromats] = useState(null)
  const [selectedId, setSelectedId] = useState('')
  const [error, setError] = useState(null)
  const loggedIn = isLoggedIn()

  useEffect(() => {
    if (!loggedIn) return undefined
    let active = true
    listOperatorLaundromats()
      .then((data) => {
        if (active) setLaundromats(data.laundromats)
      })
      .catch((err) => {
        if (active) setError(err.message)
      })
    return () => { active = false }
  }, [loggedIn])

  const selected = laundromats?.find((item) => item.laundromatId === selectedId) ?? laundromats?.[0]

  return (
    <section className="page">
      <h1>Today's bookings</h1>
      {!loggedIn && <Link to="/login?next=%2Foperator%2Ftoday">Log in as an operator</Link>}
      {loggedIn && !laundromats && !error && <p role="status">Loading laundromats…</p>}
      {error && <p className="form-error" role="alert">{error}</p>}
      {laundromats?.length === 0 && <p>No laundromats are assigned to your account.</p>}
      {selected && (
        <>
          <div className="field today-location">
            <label htmlFor="today-laundromat">Laundromat</label>
            <select id="today-laundromat" value={selected.laundromatId} onChange={(e) => setSelectedId(e.target.value)}>
              {laundromats.map((item) => (
                <option key={item.laundromatId} value={item.laundromatId}>{item.name}</option>
              ))}
            </select>
          </div>
          <TodayBookings key={selected.laundromatId} laundromat={selected} />
        </>
      )}
    </section>
  )
}
