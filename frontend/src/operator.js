import { api } from './api.js'

export function listOperatorLaundromats() {
  return api('/operator/laundromats')
}

export function listTodaysBookings(laundromatId) {
  return api(`/operator/laundromats/${encodeURIComponent(laundromatId)}/today`)
}
