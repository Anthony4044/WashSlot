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

/** The API verifies the token and permissions. This is only for navigation. */
export function hasOperatorScope(token) {
  try {
    const payload = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    const { scope } = JSON.parse(atob(payload))
    return typeof scope === 'string' && scope.split(' ').includes('operator:manage')
  } catch {
    return false
  }
}

export function subscribe(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}
