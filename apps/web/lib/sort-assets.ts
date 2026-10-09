import type { AssetStatus } from '@/types'
import type { SortDirection, SortKey } from '@/stores/view-store'
import { compareNames } from './utils'
import { OSC_STATUS_ORDER } from '@/components/osc/status'

// OSC 0001: OSC status labels sort what needs attention first; components/osc/status.tsx owns the order.
const statusOrder: Record<AssetStatus, number> = OSC_STATUS_ORDER

interface SortableAsset {
  name: string
  status: AssetStatus
  asset_type: string
  updated_at: string
  // OSC 0023: the latest version's upload, when the caller has it
  latest_version?: { created_at: string } | null
  latest_version_at?: string | null
}

// OSC 0023: Date sorts by the latest version's upload (updated_at also moves on renames and moves).
const dateOf = (a: SortableAsset) => a.latest_version?.created_at || a.latest_version_at || a.updated_at

/**
 * The order the project view shows assets in. The review page's prev/next
 * walks the same order, so both have to come from here. 'custom' keeps the
 * order they arrived in. Returns a new array.
 */
export function sortAssets<T extends SortableAsset>(
  assets: readonly T[],
  sortKey: SortKey,
  sortDirection: SortDirection,
  // OSC 0001: callers pass effectiveStatus so a status changed on this page sorts by its new value.
  statusOf: (asset: T) => AssetStatus = (asset) => asset.status,
): T[] {
  const result = [...assets]
  if (sortKey === 'custom') return result

  result.sort((a, b) => {
    let cmp = 0
    if (sortKey === 'date') {
      cmp = new Date(dateOf(a)).getTime() - new Date(dateOf(b)).getTime()
    } else if (sortKey === 'name') {
      cmp = compareNames(a.name, b.name)
    } else if (sortKey === 'status') {
      cmp = statusOrder[statusOf(a)] - statusOrder[statusOf(b)]
    } else if (sortKey === 'type') {
      cmp = a.asset_type.localeCompare(b.asset_type)
    }
    return sortDirection === 'asc' ? cmp : -cmp
  })
  return result
}
