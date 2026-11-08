const TOKEN_KEY = 'washslot.token'

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
  emit()
}

export function isLoggedIn() {
  return Boolean(getToken())
}

export function subscribe(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}
