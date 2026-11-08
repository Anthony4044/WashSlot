import { Link } from 'react-router-dom'
import { PlaceholderPage } from '../components/PlaceholderPage.jsx'

export function LaundromatsPage() {
  return (
    <PlaceholderPage
      title="Laundromats"
      path="/laundromats"
      story="US-3.1"
      owner="@Lemonada10"
      note="This list will come from GET /laundromats."
    >
      <ul className="stub-links">
        <li>
          <Link to="/laundromats/lm_3">Open a laundromat (lm_3)</Link>
        </li>
      </ul>
    </PlaceholderPage>
  )
}
