import { Link } from 'react-router-dom'
import { PlaceholderPage } from '../components/PlaceholderPage.jsx'

export function NotFoundPage() {
  return (
    <PlaceholderPage
      title="Page not found"
      path="*"
      story="US-1.2"
      owner="@Lemonada10"
      note="This route is not in the app."
    >
      <p>
        <Link to="/laundromats">Back to laundromats</Link>
      </p>
    </PlaceholderPage>
  )
}
