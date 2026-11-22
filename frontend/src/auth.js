/** JWT storage used by the API client (`src/api.js`) and the nav. */

const TOKEN_KEY = 'washslot.token'
// The email the user logged in with. The token only carries "usr_9", and the hold page wants to
// prefill the confirmation email. Cleared together with the token.
const EMAIL_KEY = 'washslot.email'

const listeners = new Set()

function emit() {
  for (const listener of listeners) {
    listener()
  }
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
  emit()
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(EMAIL_KEY)
  emit()
}

/** The logged-in user's email, or '' if we don't know it. */
export function getEmail() {
  return localStorage.getItem(EMAIL_KEY) ?? ''
}

export function setEmail(email) {
  localStorage.setItem(EMAIL_KEY, email)
}

export function isLoggedIn() {
  return Boolean(getToken())
}

/**
 * The scopes in the stored token, e.g. ["reservations:read", "operator:manage"].
 *
 * Display only (which links and pages to show): anyone can read a JWT's payload without a key,
 * and the server checks the signature and the scope on every request anyway (403 if missing).
 */
export function getScopes() {
  const token = getToken()
  if (!token) {
    return []
  }
  try {
    const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    const claims = JSON.parse(atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, '=')))
    return typeof claims.scope === 'string' ? claims.scope.split(' ').filter(Boolean) : []
  } catch {
    return []
  }
}

/** True when the token carries operator:manage (US-7.1): show the operator pages. */
export function isOperator() {
  return getScopes().includes('operator:manage')
}

export function subscribe(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}
