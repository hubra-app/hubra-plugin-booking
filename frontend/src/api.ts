import { apiFetch } from '@hubra/plugin-sdk'

export interface Options {
  can: { resources: boolean; bookings: boolean }
  memberId: number
  categories?: { id: number; name: string }[]
  inventory?: boolean
  pending?: number
}

export type Kind = 'room' | 'equipment'
export type Status = 'pending' | 'approved' | 'rejected' | 'cancelled'

export interface Resource {
  id: number
  name: string
  kind: Kind
  description: string | null
  location: string | null
  color: string | null
  inventoryItemId: number | null
  inventoryItemName: string | null
  needsApproval: boolean
  feeFlat: number | null
  feePerHour: number | null
  categoryId: number | null
  maxHours: number | null
  advanceDays: number | null
  active: boolean
  position: number
}

export interface Booking {
  id: number
  resourceId: number
  resourceName: string | null
  memberId: number | null
  memberName: string | null
  title: string | null
  startsAt: string
  endsAt: string
  status: Status
  seriesId: string | null
  mine: boolean
  note?: string | null
  fee?: number | null
  invoiceId?: number | null
  decisionNote?: string | null
}

const BASE = '/app/booking'
const json = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: body === undefined ? undefined : JSON.stringify(body),
})

export const QK = {
  all: ['booking'] as const,
  options: ['booking', 'options'] as const,
  resources: (all: boolean) => ['booking', 'resources', all] as const,
  items: ['booking', 'inventory-items'] as const,
  calendar: (from: string, to: string) => ['booking', 'calendar', from, to] as const,
  mine: ['booking', 'mine'] as const,
  pending: ['booking', 'pending'] as const,
}

export const getOptions = () => apiFetch<Options>(`${BASE}/options`)
export const listResources = (all = false) => apiFetch<Resource[]>(`${BASE}/resources${all ? '?all=1' : ''}`)
export const saveResource = (body: Record<string, unknown>, id?: number) =>
  apiFetch<Resource>(id ? `${BASE}/resources/${id}` : `${BASE}/resources`, json(id ? 'PATCH' : 'POST', body))
export const deleteResource = (id: number) => apiFetch<void>(`${BASE}/resources/${id}`, { method: 'DELETE' })
export const listInventoryItems = () =>
  apiFetch<{ id: number; name: string; location: string | null }[]>(`${BASE}/inventory-items`)

export const listCalendar = (from: string, to: string) =>
  apiFetch<Booking[]>(`${BASE}/bookings?from=${from}&to=${to}`)
export const listMine = () => apiFetch<Booking[]>(`${BASE}/bookings/mine`)
export const listPending = () => apiFetch<Booking[]>(`${BASE}/bookings/pending`)
export const createBooking = (body: Record<string, unknown>) =>
  apiFetch<Booking | Booking[]>(`${BASE}/bookings`, json('POST', body))
export const decideBooking = (id: number, approve: boolean, note?: string) =>
  apiFetch<Booking>(`${BASE}/bookings/${id}/decide`, json('POST', { approve, note }))
export const cancelBooking = (id: number, series = false) =>
  apiFetch<{ cancelled: number[] }>(`${BASE}/bookings/${id}/cancel`, json('POST', { series }))

export function errorText(err: unknown) {
  return err instanceof Error ? err.message : String(err)
}

const pad = (n: number) => String(n).padStart(2, '0')

/** A local date as YYYY-MM-DD. */
export function isoDay(d: Date) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** "2026-11-05T18:00" read as local wall-clock time. */
export function parseLocal(value: string) {
  const [day, time = '00:00'] = value.split('T')
  const [y, m, d] = day.split('-').map(Number)
  const [h, min] = time.split(':').map(Number)
  return new Date(y, m - 1, d, h, min)
}

export function hhmm(value: string) {
  return value.slice(11, 16)
}

export function formatDay(value: string) {
  const [y, m, d] = value.slice(0, 10).split('-')
  return `${d}.${m}.${y}`
}

export function addDays(d: Date, n: number) {
  const out = new Date(d)
  out.setDate(out.getDate() + n)
  return out
}

/** Monday of the week that holds *d*. */
export function weekStart(d: Date) {
  const out = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  out.setDate(out.getDate() - ((out.getDay() + 6) % 7))
  return out
}

export function hoursBetween(start: string, end: string) {
  return (parseLocal(end).getTime() - parseLocal(start).getTime()) / 3_600_000
}

export function feeFor(r: Resource | undefined, start: string, end: string) {
  if (!r) return 0
  const hours = Math.max(0, hoursBetween(start, end))
  return (r.feeFlat ?? 0) + (r.feePerHour ?? 0) * hours
}
