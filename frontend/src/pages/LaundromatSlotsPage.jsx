import { Link, useParams } from 'react-router-dom'
import { PlaceholderPage } from '../components/PlaceholderPage.jsx'

export function LaundromatSlotsPage() {
  const { id } = useParams()

  return (
    <PlaceholderPage
      title="Availability"
      path="/laundromats/:id"
      story="US-3.1"
      owner="@Lemonada10"
      note="Grid of machines × times for a chosen date. Available slots link to a hold."
    >
      <p>
        Laundromat: <code>{id}</code>
      </p>
      <ul className="stub-links">
        <li>
          <Link to="/slots/slot_1842/hold">Hold slot_1842</Link>
        </li>
      </ul>
    </PlaceholderPage>
  )
}
