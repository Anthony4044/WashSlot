import { useEffect, useState, useSyncExternalStore } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ApiError } from '../api.js'
import { isLoggedIn, isOperator, subscribe } from '../auth.js'
import { formatSlotHour } from '../browse.js'
import { formatInZone, listNotifications, retryNotification } from '../operator.js'

// The contract's NotificationStatus, in the order the filter offers them ('' = every status).
const FILTERS = [
  { value: 'FAILED', label: 'Failed' },
  { value: 'PENDING', label: 'Waiting to send' },
  { value: 'SENT', label: 'Sent' },
  { value: '', label: 'All' },
]

function messageOf(err) {
  return err instanceof ApiError ? err.message : 'Something went wrong.'
}

/**
 * /operator/notifications (US-7.3): the confirmation emails of my laundromats, failed ones first,
 * with a "Retry" button. Retry only puts the email back in the queue; the worker sends it.
 *
 * Shown only to a token with operator:manage, but that is cosmetic: the server checks the scope
 * (403) and that the email belongs to one of this operator's laundromats (404).
 */
export function OperatorNotificationsPage() {
  const loggedIn = useSyncExternalStore(subscribe, isLoggedIn, () => false)
  const operator = useSyncExternalStore(subscribe, isOperator, () => false)

  if (!loggedIn) {
    return (
      <section className="page form-page">
        <h1>Confirmation emails</h1>
        <div className="notice">
          <p>Log in with an operator account to see your laundromat's emails.</p>
          <Link to={`/login?next=${encodeURIComponent('/operator/notifications')}`}>Log in</Link>
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
  return <NotificationList />
}

/** The status filter (kept in the URL, ?status=) and a Refresh button over the list itself. */
function NotificationList() {
  const [searchParams, setSearchParams] = useSearchParams()
  const requested = searchParams.get('status') ?? 'FAILED'
  const status = FILTERS.some((f) => f.value === requested) ? requested : 'FAILED'
  const [refresh, setRefresh] = useState(0)

  function choose(value) {
    setSearchParams(value === 'FAILED' ? {} : { status: value })
  }

  return (
    <section className="page operator-page">
      <p className="kicker">Operator</p>
      <h1>Confirmation emails</h1>
      <p className="lede">
        If the email service keeps failing, the worker gives up after 6 tries. Retry puts the email back
        in the queue and the worker sends it within a few seconds.
      </p>

      <div className="notifications-toolbar">
        <div className="field">
          <label htmlFor="notification-status">Show</label>
          <select id="notification-status" value={status} onChange={(e) => choose(e.target.value)}>
            {FILTERS.map((f) => (
              <option key={f.value || 'all'} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
        </div>
        <button type="button" className="button-secondary" onClick={() => setRefresh((n) => n + 1)}>
          Refresh
        </button>
      </div>

      {/* key: a new filter or a refresh starts a fresh load, so an old list never lingers */}
      <Notifications key={`${status}:${refresh}`} status={status} />

      <ul className="stub-links">
        <li>
          <Link to="/operator">Machines and slots</Link>
        </li>
        <li>
          <Link to="/operator/today">Today's bookings</Link>
        </li>
      </ul>
    </section>
  )
}

const EMPTY = {
  FAILED: 'No failed emails. Every confirmation went out or is still being tried.',
  PENDING: 'No emails waiting to be sent.',
  SENT: 'No emails sent yet.',
  '': 'No confirmation emails yet.',
}

/** Loads one filter's emails (newest first). A retried row is replaced by what the server answered. */
function Notifications({ status }) {
  const [notifications, setNotifications] = useState(null)
  const [loadError, setLoadError] = useState(null)

  useEffect(() => {
    let cancelled = false
    listNotifications(status)
      .then((data) => !cancelled && setNotifications(data.notifications))
      .catch((err) => !cancelled && setLoadError(messageOf(err)))
    return () => {
      cancelled = true
    }
  }, [status])

  function replace(updated) {
    setNotifications((current) =>
      current.map((n) => (n.notificationId === updated.notificationId ? updated : n)),
    )
  }

  if (loadError) {
    return (
      <p className="form-error" role="alert">
        {loadError}
      </p>
    )
  }
  if (!notifications) {
    return (
      <p className="lede" role="status">
        Loading emails…
      </p>
    )
  }
  if (notifications.length === 0) {
    return <p className="notifications-empty">{EMPTY[status]}</p>
  }
  return (
    <ul className="reservation-list">
      {notifications.map((n) => (
        <NotificationRow key={n.notificationId} notification={n} onRetried={replace} />
      ))}
    </ul>
  )
}

function NotificationRow({ notification: n, onRetried }) {
  const [retrying, setRetrying] = useState(false)
  const [error, setError] = useState(null)

  async function retry() {
    setRetrying(true)
    setError(null)
    try {
      onRetried(await retryNotification(n.notificationId))
    } catch (err) {
      setError(messageOf(err))
    } finally {
      setRetrying(false)
    }
  }

  return (
    <li className="reservation-item notification-item">
      <span className="reservation-where">{n.recipient}</span>
      <span className="reservation-when">
        {n.laundromatName} · {n.machineLabel} · {formatInZone(n.startTime, n.endTime, n.timezone)}
      </span>
      <span className={`reservation-status status-${n.status.toLowerCase()}`}>{statusText(n)}</span>
      {n.lastError && n.status !== 'SENT' && <span className="notification-error">Last error: {n.lastError}</span>}
      {n.status === 'FAILED' && (
        <button type="button" className="button-secondary" onClick={retry} disabled={retrying}>
          {retrying ? 'Retrying…' : 'Retry'}
        </button>
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </li>
  )
}

function statusText(n) {
  if (n.status === 'SENT') {
    return n.sentAt ? `Sent at ${formatSlotHour(n.sentAt, n.timezone)}` : 'Sent'
  }
  if (n.status === 'FAILED') {
    return `Failed after ${n.attempts} ${n.attempts === 1 ? 'try' : 'tries'}`
  }
  if (n.attempts === 0) {
    return 'Queued · sending in a few seconds'
  }
  return `Try ${n.attempts} failed · next try at ${formatSlotHour(n.nextAttemptAt, n.timezone)}`
}
