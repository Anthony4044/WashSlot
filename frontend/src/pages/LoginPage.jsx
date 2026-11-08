import { Link } from 'react-router-dom'
import { PlaceholderPage } from '../components/PlaceholderPage.jsx'

export function LoginPage() {
  return (
    <PlaceholderPage
      title="Log in"
      path="/login"
      story="US-2.1"
      owner="@Anthony4044"
      note="Save the JWT here, then send it on later requests."
    >
      <p>
        Need an account? <Link to="/register">Register</Link>
      </p>
    </PlaceholderPage>
  )
}
