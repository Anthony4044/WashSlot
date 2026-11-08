import { getToken } from './auth.js'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

const ERROR_MESSAGES = {
  missing_token: 'You need to log in first.',
  invalid_token: 'Your session is no longer valid. Please log in again.',
  insufficient_scope: 'You do not have permission to do that.',
  not_found: 'We could not find that.',
  slot_unavailable: 'Someone just took this slot.',
  invalid_request: 'That request was not valid.',
  email_taken: 'An account with that email already exists.',
  hold_expired: 'This hold has expired.',
  too_late_to_cancel: 'It is too late to cancel this reservation.',
  already_cancelled: 'This reservation is already cancelled.',
  idempotency_key_required: 'This request needs an idempotency key.',
  idempotency_key_reuse:
    'That idempotency key was already used with a different request.',
}

export class ApiError extends Error {
  constructor(code, status) {
    super(messageFor(code))
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

function messageFor(code) {
  if (!code) {
    return 'Something went wrong.'
  }
  return ERROR_MESSAGES[code] ?? `Something went wrong (${code}).`
}

export async function api(path, { method = 'GET', body, headers, idempotencyKey } = {}) {
  const requestHeaders = { ...headers }
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

  const response = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: requestHeaders,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

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
    throw new ApiError(data?.error ?? 'unknown_error', response.status)
  }

  return data
}
