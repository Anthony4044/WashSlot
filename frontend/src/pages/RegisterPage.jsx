import { Link } from 'react-router-dom'
import { PlaceholderPage } from '../components/PlaceholderPage.jsx'

export function RegisterPage() {
  return (
    <PlaceholderPage
      title="Create an account"
      path="/register"
      story="US-2.1"
      owner="@Anthony4044"
      note="Registration always creates a customer."
    >
      <p>
        Already have an account? <Link to="/login">Log in</Link>
      </p>
    </PlaceholderPage>
  )
}
