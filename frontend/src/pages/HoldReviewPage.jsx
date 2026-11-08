import { Link, useParams } from 'react-router-dom'
import { PlaceholderPage } from '../components/PlaceholderPage.jsx'

export function HoldReviewPage() {
  const { holdId } = useParams()

  return (
    <PlaceholderPage
      title="Review your hold"
      path="/holds/:holdId"
      story="US-4.2"
      owner="@ammarranko"
      note="Show the countdown from expiresAt, then confirm."
    >
      <p>
        Hold: <code>{holdId}</code>
      </p>
      <ul className="stub-links">
        <li>
          <Link to="/reservations">Confirm and go to my reservations</Link>
        </li>
      </ul>
    </PlaceholderPage>
  )
}
