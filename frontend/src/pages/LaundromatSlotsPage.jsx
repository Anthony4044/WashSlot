import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api.js'
import { formatSlotHour, listLaundromats, listSlots, todayDateInputValue } from '../browse.js'

/**
 * /laundromats/:id — availability grid (US-3.1).
 * Date picker + machines × times. AVAILABLE slots link to /slots/:slotId/hold with router state
 * so the hold page can show machine/time without a "get one slot" endpoint.
 */
export function LaundromatSlotsPage() {
  const { id } = useParams()
  const [date, setDate] = useState(() => todayDateInputValue())
  const [laundromat, setLaundromat] = useState(null)
  const [machines, setMachines] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    listLaundromats()
      .then((data) => {
        if (cancelled) return
        const match = data.laundromats.find((lm) => lm.laundromatId === id) ?? null
        setLaundromat(match)
      })
      .catch(() => {
        /* name is nice-to-have; the grid still loads */
      })
    return () => {
      cancelled = true
    }
  }, [id])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    setMachines(null)
    listSlots(id, date)
      .then((data) => {
        if (!cancelled) {
          setMachines(data.machines)
          setLoading(false)
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : 'Could not load slots.')
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [id, date])

  const hours = useMemo(() => {
    if (!machines) return []
    const labels = new Map()
    for (const machine of machines) {
      for (const slot of machine.slots) {
        const key = slot.startTime
        if (!labels.has(key)) labels.set(key, formatSlotHour(slot.startTime))
      }
    }
    return [...labels.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([startTime, label]) => ({ startTime, label }))
  }, [machines])

  const title = laundromat?.name ?? 'Availability'

  return (
    <section className="page availability-page">
      <p className="kicker">
        <Link to="/laundromats">Laundromats</Link>
      </p>
      <h1>{title}</h1>
      {laundromat && <p className="lede">{laundromat.address}</p>}

      <div className="date-picker">
        <label htmlFor="slot-date">Date</label>
        <input
          id="slot-date"
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
      </div>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      {loading && <p className="lede">Loading…</p>}

      {!loading && !error && machines && machines.length === 0 && (
        <p className="lede">No reservable machines have slots on this day.</p>
      )}

      {!loading && !error && machines && machines.length > 0 && (
        <div className="slot-grid-wrap">
          <table className="slot-grid">
            <thead>
              <tr>
                <th scope="col">Machine</th>
                {hours.map((hour) => (
                  <th key={hour.startTime} scope="col">
                    {hour.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {machines.map((machine) => {
                const byStart = new Map(machine.slots.map((s) => [s.startTime, s]))
                return (
                  <tr key={machine.machineId}>
                    <th scope="row">
                      <span className="machine-label">{machine.label}</span>
                      <span className="machine-type">
                        {machine.type === 'DRYER' ? 'Dryer' : 'Washer'}
                      </span>
                    </th>
                    {hours.map((hour) => {
                      const slot = byStart.get(hour.startTime)
                      if (!slot) {
                        return <td key={hour.startTime} className="slot-empty" />
                      }
                      if (slot.status !== 'AVAILABLE') {
                        return (
                          <td key={hour.startTime} className="slot-taken">
                            Taken
                          </td>
                        )
                      }
                      return (
                        <td key={hour.startTime} className="slot-free">
                          <Link
                            to={`/slots/${slot.slotId}/hold`}
                            state={{
                              laundromatId: id,
                              laundromatName: laundromat?.name ?? title,
                              machineLabel: machine.label,
                              machineType: machine.type,
                              startTime: slot.startTime,
                              endTime: slot.endTime,
                            }}
                          >
                            Free
                          </Link>
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
