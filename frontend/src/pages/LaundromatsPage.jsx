import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api.js'
import { listLaundromats } from '../browse.js'

/** /laundromats — pick a laundromat (US-3.1). */
export function LaundromatsPage() {
  const [laundromats, setLaundromats] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    listLaundromats()
      .then((data) => {
        if (!cancelled) setLaundromats(data.laundromats)
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : 'Could not load laundromats.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <section className="page">
      <p className="kicker">Browse</p>
      <h1>Laundromats</h1>
      <p className="lede">Pick a location, then a date and a free washer or dryer.</p>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      {laundromats === null && !error && <p className="lede">Loading…</p>}

      {laundromats && laundromats.length === 0 && (
        <p className="lede">No laundromats yet. Run the seed script on the back end.</p>
      )}

      {laundromats && laundromats.length > 0 && (
        <ul className="laundromat-list">
          {laundromats.map((lm) => (
            <li key={lm.laundromatId}>
              <Link to={`/laundromats/${lm.laundromatId}`} className="laundromat-link">
                <span className="laundromat-name">{lm.name}</span>
                <span className="laundromat-address">{lm.address}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
