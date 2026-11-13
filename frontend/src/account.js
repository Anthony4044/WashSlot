/** Register and log in (US-2.1). The token itself is stored by `src/auth.js`. */
import { api } from './api.js'
import { setEmail, setToken } from './auth.js'

export const MIN_PASSWORD_LENGTH = 8
const DEFAULT_AFTER_LOGIN = '/laundromats'

/** POST /auth/login, then keep the token so later requests send it. */
export async function logIn(email, password) {
  const { accessToken } = await api('/auth/login', {
    method: 'POST',
    body: { email, password },
  })
  setEmail(email.trim()) // remembered to prefill the hold page's confirmation email
  setToken(accessToken)
}

/** POST /auth/register. Always creates a customer; resolves to { userId, email, role }. */
export function register(email, password) {
  return api('/auth/register', { method: 'POST', body: { email, password } })
}

/**
 * Where to go after logging in: the ?next= path the 401 redirect saved, if it is one of our own
 * pages. Anything else (another site, //evil.example, /login itself) goes to the default.
 */
export function nextPath(next) {
  const ownPage =
    typeof next === 'string' &&
    next.startsWith('/') &&
    !next.startsWith('//') &&
    !next.startsWith('/\\')
  if (!ownPage || next.startsWith('/login') || next.startsWith('/register')) {
    return DEFAULT_AFTER_LOGIN
  }
  return next
}
