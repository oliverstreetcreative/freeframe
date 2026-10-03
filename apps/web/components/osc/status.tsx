'use client'

/**
 * OSC status labels (Sam, 10/2/26: "turning things green is helpful").
 *
 * One status per asset, shown as a coloured pill on the grid thumbnail, the list row and the
 * player bar. Staff click it to change it; it saves through the existing PATCH /assets/{id}
 * (editor role). It rides on FreeFrame's own `asset.status` field. The vocabulary is OSC's and
 * shared with the client website:
 *
 *   in_review  → Needs review        (orange, OSC accent)  ← every new upload / new version
 *   draft      → In progress         (blue)
 *   client_review → Client review    (purple)              ← the one value OSC adds
 *   rejected   → Changes requested   (red)                 ← a reviewer requests changes
 *   approved   → Approved            (green)               ← a reviewer approves the latest version
 *
 * Kept in this one file (plus one-line mounts) so upstream merges stay cheap.
 * Colours are inline so Tailwind's purge can't drop them. Every pill passes WCAG AA:
 * orange/#1A1206 6.09, blue/white 5.17, purple/white 5.70, red/white 4.83, green/white 5.02.
 */
import * as React from 'react'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { Check, ChevronDown } from 'lucide-react'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { Asset, AssetStatus } from '@/types'

export type OscStatus = AssetStatus

export const OSC_STATUSES: { value: OscStatus; label: string; bg: string; fg: string }[] = [
  { value: 'in_review', label: 'Needs review', bg: '#E07830', fg: '#1A1206' },
  { value: 'draft', label: 'In progress', bg: '#2563EB', fg: '#FFFFFF' },
  { value: 'client_review', label: 'Client review', bg: '#7C3AED', fg: '#FFFFFF' },
  { value: 'rejected', label: 'Changes requested', bg: '#DC2626', fg: '#FFFFFF' },
  { value: 'approved', label: 'Approved', bg: '#15803D', fg: '#FFFFFF' },
]
const ARCHIVED = { value: 'archived' as OscStatus, label: 'Archived', bg: '#52525B', fg: '#FFFFFF' }

export function statusMeta(s: OscStatus) {
  return OSC_STATUSES.find((x) => x.value === s) ?? ARCHIVED
}

/** Grid sort order: what needs attention first, done last. */
export const OSC_STATUS_ORDER: Record<OscStatus, number> = {
  in_review: 0, rejected: 1, client_review: 2, draft: 3, approved: 4, archived: 5,
}

// ---- tiny shared store: local overrides after a change + the grid's status filter ----------
type State = { overrides: Record<string, OscStatus>; filter: Set<OscStatus> }
let state: State = { overrides: {}, filter: new Set() }
const listeners = new Set<() => void>()
const emit = () => listeners.forEach((l) => l())
function subscribe(l: () => void) { listeners.add(l); return () => { listeners.delete(l) } }
function useOscState<T>(pick: (s: State) => T): T {
  return React.useSyncExternalStore(subscribe, () => pick(state), () => pick(state))
}

/** The status to show/sort/filter by: a just-made change wins over the fetched asset. */
export function effectiveStatus(asset: Pick<Asset, 'id' | 'status'>): OscStatus {
  return state.overrides[asset.id] ?? asset.status
}
export function useEffectiveStatus(asset: Pick<Asset, 'id' | 'status'>): OscStatus {
  return useOscState((s) => s.overrides[asset.id] ?? asset.status)
}
export function useOscStatusVersion(): unknown {
  // Changes identity whenever any override or the filter changes — a memo dependency for the grid.
  return useOscState((s) => s)
}

export function useStatusFilter() {
  const filter = useOscState((s) => s.filter)
  const toggle = React.useCallback((v: OscStatus) => {
    const next = new Set(state.filter)
    if (next.has(v)) next.delete(v)
    else next.add(v)
    state = { ...state, filter: next }
    emit()
  }, [])
  const clear = React.useCallback(() => { state = { ...state, filter: new Set() }; emit() }, [])
  return { filter, toggle, clear }
}
export function passesStatusFilter(asset: Pick<Asset, 'id' | 'status'>): boolean {
  return state.filter.size === 0 || state.filter.has(effectiveStatus(asset))
}

async function setStatus(assetId: string, prev: OscStatus, next: OscStatus) {
  state = { ...state, overrides: { ...state.overrides, [assetId]: next } }
  emit()
  try {
    await api.patch(`/assets/${assetId}`, { status: next })
  } catch {
    state = { ...state, overrides: { ...state.overrides, [assetId]: prev } }
    emit()
  }
}

// ---- the pill ---------------------------------------------------------------------------------
export function StatusPill({
  asset, editable = true, size = 'sm', className,
}: { asset: Pick<Asset, 'id' | 'status'>; editable?: boolean; size?: 'xs' | 'sm'; className?: string }) {
  const current = useEffectiveStatus(asset)
  const meta = statusMeta(current)
  // ONE element is the pill: the ring must hug it (Sam 10/2 23:55 "the orange outline doesn't
  // align"). Before, a wrapper <button> carried the ring around an inner <span>, so the ring had the
  // button's box (plus inline baseline space), not the pill's. Now the button IS the pill, the ring
  // is a box-shadow on that same rounded element (gap in the page colour, then the accent), and it
  // shows on keyboard focus only (:focus-visible), never as a leftover after a click.
  const pillClass = cn(
    'inline-flex items-center gap-1 rounded-full font-semibold leading-none whitespace-nowrap select-none align-middle',
    size === 'xs' ? 'px-2 py-[3px] text-[10px]' : 'px-2.5 py-1 text-xs',
    className,
  )
  const inner = (
    <>
      {meta.label}
      {editable && <ChevronDown className={size === 'xs' ? 'h-2.5 w-2.5' : 'h-3 w-3'} style={{ color: meta.fg }} />}
    </>
  )
  if (!editable) {
    return (
      <span data-osc-status={current} className={pillClass} style={{ background: meta.bg, color: meta.fg }}>
        {inner}
      </span>
    )
  }
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button type="button" data-osc-status={current} aria-label={`Status: ${meta.label}. Change status`}
          onClick={(e) => e.stopPropagation()}
          className={cn(pillClass, 'cursor-pointer border-0 outline-none focus:outline-none',
            'focus-visible:[box-shadow:0_0_0_2px_var(--bg-primary),0_0_0_4px_var(--accent)]')}
          style={{ background: meta.bg, color: meta.fg }}>
          {inner}
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="start" sideOffset={6} onClick={(e) => e.stopPropagation()}
          className="z-[100] min-w-[190px] rounded-xl border border-border bg-bg-elevated shadow-2xl py-1.5">
          {OSC_STATUSES.map((s) => (
            <DropdownMenu.Item key={s.value}
              onSelect={() => { if (s.value !== current) setStatus(asset.id, current, s.value) }}
              className="flex items-center gap-2.5 mx-1 px-2.5 py-2 rounded-lg text-sm text-text-secondary hover:bg-bg-hover hover:text-text-primary cursor-pointer outline-none">
              <span className="h-2.5 w-2.5 rounded-full shrink-0" style={{ background: s.bg }} />
              <span className="flex-1">{s.label}</span>
              {s.value === current && <Check className="h-3.5 w-3.5 text-text-tertiary" />}
            </DropdownMenu.Item>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}

// ---- filter bar above the grid -----------------------------------------------------------------
export function StatusFilterBar({ assets }: { assets: Pick<Asset, 'id' | 'status'>[] }) {
  const { filter, toggle, clear } = useStatusFilter()
  useOscStatusVersion()
  const counts = new Map<OscStatus, number>()
  assets.forEach((a) => { const s = effectiveStatus(a); counts.set(s, (counts.get(s) ?? 0) + 1) })
  if (assets.length === 0) return null
  return (
    <div className="flex flex-wrap items-center gap-1.5 mb-3" role="group" aria-label="Filter by status">
      <span className="text-xs text-text-tertiary mr-1">Status</span>
      {OSC_STATUSES.map((s) => {
        const on = filter.has(s.value)
        const n = counts.get(s.value) ?? 0
        return (
          <button key={s.value} type="button" onClick={() => toggle(s.value)} aria-pressed={on}
            className={cn('inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors outline-none focus-visible:[box-shadow:0_0_0_2px_var(--bg-primary),0_0_0_4px_var(--accent)]',
              on ? 'border-transparent' : 'border-border text-text-secondary hover:text-text-primary hover:bg-bg-hover',
              n === 0 && !on && 'opacity-50')}
            style={on ? { background: s.bg, color: s.fg } : undefined}>
            {!on && <span className="h-2 w-2 rounded-full" style={{ background: s.bg }} />}
            {s.label}
            <span className="tabular-nums opacity-80">{n}</span>
          </button>
        )
      })}
      {filter.size > 0 && (
        <button type="button" onClick={clear} className="text-xs text-text-tertiary hover:text-text-primary ml-1 underline">
          Clear
        </button>
      )}
    </div>
  )
}
