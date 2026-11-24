import type { AssetStatus } from '@/types'

/** Hub 00-system/osc.css: one palette in both themes, independent of the accent.
 * Needs review = pending action (amber); Client review = with a reviewer (blue);
 * In progress = not yet ready (grey). These are presentation aliases only.
 * Archived remains grey, outside the five active choices. No stored values change.
 */
export const OSC_STATUSES = [
  { value: 'in_review', label: 'Needs review', tone: 'wait', bg: '#fcefd6', fg: '#8a5a0b' },
  { value: 'draft', label: 'In progress', tone: 'off', bg: '#efefec', fg: '#6e6e6a' },
  { value: 'client_review', label: 'Client review', tone: 'review', bg: '#e3eef8', fg: '#245a7d' },
  { value: 'rejected', label: 'Changes requested', tone: 'bad', bg: '#fbe3e0', fg: '#a33b2c' },
  { value: 'approved', label: 'Approved', tone: 'ok', bg: '#e7f3e9', fg: '#2f6b3a' },
] satisfies { value: AssetStatus; label: string; tone: string; bg: string; fg: string }[]
const ARCHIVED = { value: 'archived', label: 'Archived', tone: 'off', bg: '#efefec', fg: '#6e6e6a' }

export function statusMeta(status: AssetStatus) {
  return OSC_STATUSES.find((item) => item.value === status) ?? ARCHIVED
}
