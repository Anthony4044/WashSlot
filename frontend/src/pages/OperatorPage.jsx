import { useEffect, useState, useSyncExternalStore } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api.js'
import { isLoggedIn, isOperator, subscribe } from '../auth.js'
import { createSlots, isoDay, listMachines, listMyLaundromats, setReservable } from '../operator.js'

const SLOT_LENGTHS = [30, 60, 90] // minutes; the contract's CreateSlotsRequest.slotMinutes

function messageOf(err) {
  return err instanceof ApiError ? err.message : 'Something went wrong.'
}

/**
 * /operator (US-7.1): the operator's machines with on/off switches (reservable or walk-in only),
 * and a "Create slots" form.
 *
 * The page only shows these tools to a token with operator:manage, but that is cosmetic: the server
 * checks the scope (403) and that the laundromat is this operator's own (404) on every request.
 */
export function OperatorPage() {
  const loggedIn = useSyncExternalStore(subscribe, isLoggedIn, () => false)
  const operator = useSyncExternalStore(subscribe, isOperator, () => false)

  if (!loggedIn) {
    return (
      <section className="page form-page">
        <h1>Machines and slots</h1>
        <div className="notice">
          <p>Log in with an operator account to manage your laundromat.</p>
          <Link to={`/login?next=${encodeURIComponent('/operator')}`}>Log in</Link>
        </div>
      </section>
    )
  }
  if (!operator) {
    return (
      <section className="page form-page">
        <h1>Operators only</h1>
        <div className="notice" role="alert">
          <p>This page is for laundromat operators. Your account is a customer account.</p>
          <Link to="/laundromats">Back to laundromats</Link>
        </div>
      </section>
    )
  }
  return <OperatorTools />
}

/** Loads the laundromats I operate, lets me pick one if there are several. */
function OperatorTools() {
  const [laundromats, setLaundromats] = useState(null)
  const [loadError, setLoadError] = useState(null)
  const [chosenId, setChosenId] = useState(null)

  useEffect(() => {
    let cancelled = false
    listMyLaundromats()
      .then((data) => !cancelled && setLaundromats(data.laundromats))
      .catch((err) => !cancelled && setLoadError(messageOf(err)))
    return () => {
      cancelled = true
    }
  }, [])

  if (loadError) {
    return (
      <section className="page">
        <h1>Machines and slots</h1>
        <p className="form-error" role="alert">
          {loadError}
        </p>
      </section>
    )
  }
  if (!laundromats) {
    return (
      <section className="page" aria-busy="true">
        <p className="lede">Loading your laundromats…</p>
      </section>
    )
  }
  if (laundromats.length === 0) {
    return (
      <section className="page">
        <h1>Machines and slots</h1>
        <div className="notice">
          <p>No laundromat is linked to your account yet.</p>
        </div>
      </section>
    )
  }

  const laundromat = laundromats.find((l) => l.laundromatId === chosenId) ?? laundromats[0]

  return (
    <section className="page operator-page">
      <p className="kicker">Operator</p>
      <h1>Machines and slots</h1>
      {laundromats.length > 1 ? (
        <div className="field operator-pick">
          <label htmlFor="operator-laundromat">Laundromat</label>
          <select
            id="operator-laundromat"
            value={laundromat.laundromatId}
            onChange={(e) => setChosenId(e.target.value)}
          >
            {laundromats.map((l) => (
              <option key={l.laundromatId} value={l.laundromatId}>
                {l.name}
              </option>
            ))}
          </select>
        </div>
      ) : (
        <p className="lede">
          {laundromat.name} · {laundromat.address}
        </p>
      )}

      {/* key: switching laundromats starts the tools fresh, so nothing from the other one lingers */}
      <LaundromatTools key={laundromat.laundromatId} laundromat={laundromat} />

      <ul className="stub-links">
        <li>
          <Link to="/operator/today">Today's bookings</Link>
        </li>
        <li>
          <Link to="/operator/notifications">Failed emails</Link>
        </li>
      </ul>
    </section>
  )
}

/** The machines of one laundromat (with their switches) and the "Create slots" form. */
function LaundromatTools({ laundromat }) {
  const [machines, setMachines] = useState(null)
  const [loadError, setLoadError] = useState(null)

  useEffect(() => {
    let cancelled = false
    listMachines(laundromat.laundromatId)
      .then((data) => !cancelled && setMachines(data.machines))
      .catch((err) => !cancelled && setLoadError(messageOf(err)))
    return () => {
      cancelled = true
    }
  }, [laundromat.laundromatId])

  if (loadError) {
    return (
      <p className="form-error" role="alert">
        {loadError}
      </p>
    )
  }
  if (!machines) {
    return <p className="lede">Loading machines…</p>
  }

  function replace(updated) {
    setMachines((all) => all.map((m) => (m.machineId === updated.machineId ? updated : m)))
  }

  return (
    <>
      <h2 className="operator-heading">Machines</h2>
      <p className="field-hint">
        Reservable machines appear in the slot grid. Switching one off stops new holds; bookings
        already made stay valid.
      </p>
      {machines.length === 0 ? (
        <p className="lede">This laundromat has no machines yet.</p>
      ) : (
        <ul className="machine-list">
          {machines.map((m) => (
            <MachineSwitch
              key={m.machineId}
              laundromatId={laundromat.laundromatId}
              machine={m}
              onSaved={replace}
            />
          ))}
        </ul>
      )}

      <h2 className="operator-heading">Create slots</h2>
      <CreateSlotsForm laundromat={laundromat} machines={machines} />
    </>
  )
}

/** One machine and its on/off switch. The new state is shown only once the server has saved it. */
function MachineSwitch({ laundromatId, machine, onSaved }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const id = `reservable-${machine.machineId}`

  async function toggle() {
    setBusy(true)
    setError(null)
    try {
      onSaved(await setReservable(laundromatId, machine.machineId, !machine.reservable))
    } catch (err) {
      setError(messageOf(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <li className="machine-row">
      <div>
        <span className="machine-label">{machine.label}</span>
        <span className="machine-type">{machine.type === 'DRYER' ? 'Dryer' : 'Washer'}</span>
      </div>
      <div className="switch">
        <input
          id={id}
          type="checkbox"
          role="switch"
          checked={machine.reservable}
          onChange={toggle}
          disabled={busy}
        />
        <label htmlFor={id}>{machine.reservable ? 'Reservable' : 'Walk-in only'}</label>
      </div>
      {error && (
        <p className="form-error machine-error" role="alert">
          {error}
        </p>
      )}
    </li>
  )
}

/** Dates + daily hours + slot length, for one machine or every reservable one. */
function CreateSlotsForm({ laundromat, machines }) {
  const [machineId, setMachineId] = useState('') // '' = every reservable machine
  const [fromDate, setFromDate] = useState(() => isoDay(0))
  const [toDate, setToDate] = useState(() => isoDay(6))
  const [openTime, setOpenTime] = useState('08:00')
  const [closeTime, setCloseTime] = useState('20:00')
  const [slotMinutes, setSlotMinutes] = useState(60)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const noneReservable = machineId === '' && !machines.some((m) => m.reservable)

  async function onSubmit(event) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const request = { fromDate, toDate, openTime, closeTime, slotMinutes }
      if (machineId) {
        request.machineIds = [machineId]
      }
      setResult(await createSlots(laundromat.laundromatId, request))
    } catch (err) {
      setError(
        err instanceof ApiError && err.code === 'invalid_request'
          ? 'Check the form: the last day must not be before the first (31 days at most), and at least one slot must fit between opening and closing.'
          : messageOf(err),
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="form slots-form" onSubmit={onSubmit}>
      <div className="field">
        <label htmlFor="slots-machine">Machines</label>
        <select id="slots-machine" value={machineId} onChange={(e) => setMachineId(e.target.value)}>
          <option value="">Every reservable machine</option>
          {machines.map((m) => (
            <option key={m.machineId} value={m.machineId}>
              {m.label}
              {m.reservable ? '' : ' (walk-in only)'}
            </option>
          ))}
        </select>
      </div>

      <div className="field-row">
        <div className="field">
          <label htmlFor="slots-from">First day</label>
          <input id="slots-from" type="date" required value={fromDate} onChange={(e) => setFromDate(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="slots-to">Last day</label>
          <input id="slots-to" type="date" required value={toDate} onChange={(e) => setToDate(e.target.value)} />
        </div>
      </div>

      <div className="field-row">
        <div className="field">
          <label htmlFor="slots-open">Opens</label>
          <input id="slots-open" type="time" required value={openTime} onChange={(e) => setOpenTime(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="slots-close">Closes</label>
          <input
            id="slots-close"
            type="time"
            required
            value={closeTime}
            onChange={(e) => setCloseTime(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="slots-length">Slot length</label>
          <select id="slots-length" value={slotMinutes} onChange={(e) => setSlotMinutes(Number(e.target.value))}>
            {SLOT_LENGTHS.map((n) => (
              <option key={n} value={n}>
                {n} min
              </option>
            ))}
          </select>
        </div>
      </div>
      <p className="field-hint">
        Times are in the laundromat's time zone ({laundromat.timezone}). Slots that already exist or
        have already started are skipped, so sending the form twice is safe.
      </p>

      {noneReservable && (
        <p className="form-error" role="alert">
          No machine is reservable yet: switch one on above, or pick a machine.
        </p>
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {result && (
        <p className="notice" role="status">
          Created {result.created} slot{result.created === 1 ? '' : 's'}.
          {result.skipped > 0 && ` Skipped ${result.skipped} that already existed or had already started.`}
        </p>
      )}

      <button type="submit" className="button" disabled={busy || noneReservable}>
        {busy ? 'Creating…' : 'Create slots'}
      </button>
    </form>
  )
}
