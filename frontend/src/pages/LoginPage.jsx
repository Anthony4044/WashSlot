import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { logIn, nextPath } from '../account.js'
import { ApiError } from '../api.js'

export function LoginPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const next = nextPath(params.get('next'))
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(event) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await logIn(email, password)
      navigate(next, { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong.')
      setBusy(false)
    }
  }

  return (
    <section className="page form-page">
      <h1>Log in</h1>
      <p className="lede">Log in to hold and confirm a machine.</p>

      <form className="form" onSubmit={onSubmit}>
        <div className="field">
          <label htmlFor="login-email">Email</label>
          <input
            id="login-email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="login-password">Password</label>
          <input
            id="login-password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}

        <button type="submit" className="button" disabled={busy}>
          {busy ? 'Logging in…' : 'Log in'}
        </button>
      </form>

      <p className="form-footer">
        Need an account?{' '}
        <Link to={params.has('next') ? `/register?${params}` : '/register'}>Register</Link>
      </p>
    </section>
  )
}
