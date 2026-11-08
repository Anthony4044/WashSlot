import { Link, useParams } from 'react-router-dom'
import { PlaceholderPage } from '../components/PlaceholderPage.jsx'

export function HoldPage() {
  const { slotId } = useParams()

  return (
    <PlaceholderPage
      title="Hold this slot"
      path="/slots/:slotId/hold"
      story="US-4.1"
      owner="@Anthony4044"
      note="On 201, go to /holds/:holdId. On 409, show that someone just took the slot."
    >
      <p>
        Slot: <code>{slotId}</code>
      </p>
      <ul className="stub-links">
        <li>
          <Link to="/holds/hold_7251">Continue to hold_7251</Link>
        </li>
      </ul>
    </PlaceholderPage>
  )
}
