/**
 * Thin HTTP client for the WashSlot API.
 *
 * - Base URL from VITE_API_BASE_URL (see .env.example)
 * - Sends Authorization: Bearer <token> when one is in storage
 * - Turns {"error": "<code>"} bodies into readable ApiError messages
 */
import { clearToken, getToken } from './auth.js'

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/$/, '')

// Readable copy for every code in backend/app/api/errors.py CATALOG.
// Unknown codes stay non-retryable (CODING_GUIDE §3).
const ERROR_MESSAGES = {
  invalid_request: 'That request was not valid.',
  idempotency_key_required: 'This request needs an idempotency key.',
  idempotency_key_reuse:
    'That idempotency key was already used with a different request.',
  not_found: 'We could not find that.',
  method_not_allowed: 'That method is not allowed.',
  missing_token: 'You need to log in first.',
  invalid_token: 'Your session is no longer valid. Please log in again.',
  insufficient_scope: 'You do not have permission to do that.',
  invalid_credentials: 'Wrong email or password.',
  slot_unavailable: 'Someone just took this slot.',
  hold_expired: 'This hold has expired.',
  too_late_to_cancel: 'It is too late to cancel this reservation.',
  already_cancelled: 'This reservation is already cancelled.',
  reservation_not_confirmed: 'Only confirmed reservations can be checked in.',
  too_late_to_check_in: 'The check-in window has closed.',
  email_taken: 'An account with that email already exists.',
  internal_error: 'Something went wrong on the server. Try again.',
  service_unavailable: 'The service is temporarily unavailable. Try again.',
}

const RETRYABLE_CODES = new Set(['internal_error', 'service_unavailable'])

export class ApiError extends Error {
  /**
   * @param {string} code machine-readable error from {"error": "<code>"}
   * @param {number} status HTTP status
   */
  constructor(code, status) {
    super(messageFor(code))
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.retryable = RETRYABLE_CODES.has(code)
  }
}

function messageFor(code) {
  if (!code) {
    return 'Something went wrong.'
  }
  return ERROR_MESSAGES[code] ?? `Something went wrong (${code}).`
}

function redirectToLogin() {
  clearToken()
  if (typeof window === 'undefined') {
    return
  }
  const path = window.location.pathname
  if (path === '/login' || path === '/register') {
    return
  }
  // Come back to this page after logging in (the login page checks it is one of ours).
  const next = encodeURIComponent(path + window.location.search)
  window.location.assign(`/login?next=${next}`)
}

/**
 * Call the WashSlot API.
 *
 * @param {string} path path starting with /, e.g. "/laundromats"
 * @param {{
 *   method?: string,
 *   body?: unknown,
 *   headers?: Record<string, string>,
 *   idempotencyKey?: string,
 * }} [options]
 * @returns {Promise<unknown>} parsed JSON, or null for 204
 * @throws {ApiError} when the response is not ok
 */
export async function api(path, { method = 'GET', body, headers, idempotencyKey } = {}) {
  const requestHeaders = { Accept: 'application/json', ...headers }
  const token = getToken()
  if (token) {
    requestHeaders.Authorization = `Bearer ${token}`
  }
  if (body !== undefined) {
    requestHeaders['Content-Type'] = 'application/json'
  }
  if (idempotencyKey) {
    requestHeaders['Idempotency-Key'] = idempotencyKey
  }

  let response
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers: requestHeaders,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError('service_unavailable', 0)
  }

  if (response.status === 204) {
    return null
  }

  const text = await response.text()
  let data = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      throw new ApiError('invalid_response', response.status)
    }
  }

  if (!response.ok) {
    const code = typeof data?.error === 'string' ? data.error : 'unknown_error'
    if (response.status === 401) {
      redirectToLogin()
    }
    throw new ApiError(code, response.status)
  }

  return data
}
