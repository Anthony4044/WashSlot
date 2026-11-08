import { Link } from 'react-router-dom'
import { PlaceholderPage } from '../components/PlaceholderPage.jsx'

export function OperatorPage() {
  return (
    <PlaceholderPage
      title="Machines and slots"
      path="/operator"
      story="US-7.1"
      owner="@Anthony4044"
      note="Toggle reservable machines and create slots for a date range."
    >
      <ul className="stub-links">
        <li>
          <Link to="/operator/today">Today's bookings</Link>
        </li>
        <li>
          <Link to="/operator/notifications">Failed emails</Link>
        </li>
      </ul>
    </PlaceholderPage>
  )
}
