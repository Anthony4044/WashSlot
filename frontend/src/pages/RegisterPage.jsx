import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { logIn, MIN_PASSWORD_LENGTH, nextPath, register } from '../account.js'
import { ApiError } from '../api.js'

export function RegisterPage() {
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
      await register(email, password)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong.')
      setBusy(false)
      return
    }
    try {
      await logIn(email, password) // the account exists now: sign straight in
      navigate(next, { replace: true })
    } catch {
      navigate('/login', { replace: true })
    }
  }

  return (
    <section className="page form-page">
      <h1>Create an account</h1>
      <p className="lede">Reserve a washer or dryer ahead of time.</p>

      <form className="form" onSubmit={onSubmit}>
        <div className="field">
          <label htmlFor="register-email">Email</label>
          <input
            id="register-email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="register-password">Password</label>
          <input
            id="register-password"
            type="password"
            autoComplete="new-password"
            required
            minLength={MIN_PASSWORD_LENGTH}
            aria-describedby="register-password-hint"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <p id="register-password-hint" className="field-hint">
            At least {MIN_PASSWORD_LENGTH} characters.
          </p>
        </div>

        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}

        <button type="submit" className="button" disabled={busy}>
          {busy ? 'Creating account…' : 'Create account'}
        </button>
      </form>

      <p className="form-footer">
        Already have an account?{' '}
        <Link to={params.has('next') ? `/login?${params}` : '/login'}>Log in</Link>
      </p>
    </section>
  )
}
