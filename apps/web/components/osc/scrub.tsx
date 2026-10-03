'use client'

/**
 * OSC hover-scrub (Sam 10/2/26 23:40: "scrubbing over videos ... makes Frame.io feel really alive").
 *
 * A storyboard = one JPEG sprite sheet per version + meta {count, cols, rows, tile_w, tile_h,
 * interval, duration} (same keys as Stacks' skim strips). Feel rules borrowed from Stacks' skim
 * bench: load + fully decode the sheet ONCE on hover intent (lazy decode = a visible hitch on first
 * touch), then every pointer move is pure arithmetic + a CSS background-position change: no video
 * decoding, no network.
 */
import * as React from 'react'
import { api } from '@/lib/api'

export interface StoryboardMeta {
  count: number; cols: number; rows: number; tile_w: number; tile_h: number; interval: number; duration: number
}
export interface Storyboard { url: string; meta: StoryboardMeta }

const cache = new Map<string, Promise<Storyboard | null>>()

/** Fetch + preload + decode, once per asset (newest version). null = none available. */
export function loadStoryboard(assetId: string): Promise<Storyboard | null> {
  let p = cache.get(assetId)
  // Share-link guests have no session; the storyboard route is staff/member-only. Don't even ask
  // (the player falls back to upstream's decoder preview there).
  let signedIn = false
  try { signedIn = !!localStorage.getItem('ff_access_token') } catch {}
  if (!signedIn) return Promise.resolve(null)
  if (!p) {
    p = api.get<{ url: string; meta: StoryboardMeta }>(`/assets/${assetId}/storyboard`)
      .then(async (r) => {
        const img = new Image()
        img.src = r.url
        try { await img.decode() } catch { /* still usable once loaded */ }
        return { url: r.url, meta: r.meta }
      })
      .catch(() => null)
    cache.set(assetId, p)
  }
  return p
}

export function useStoryboard(assetId: string | undefined, eager = false) {
  const [sb, setSb] = React.useState<Storyboard | null>(null)
  const want = React.useCallback(() => {
    if (!assetId) return
    loadStoryboard(assetId).then((s) => setSb(s))
  }, [assetId])
  React.useEffect(() => { setSb(null); if (eager) want() }, [assetId, eager, want])
  return { sb, want }
}

/** The tile for frame `i`, scaled to fill a box of the tile's aspect. */
export function tileStyle(sb: Storyboard, i: number): React.CSSProperties {
  const { cols, rows, count } = sb.meta
  const idx = Math.max(0, Math.min(count - 1, i))
  const c = idx % cols, r = Math.floor(idx / cols)
  return {
    backgroundImage: `url("${sb.url}")`,
    backgroundSize: `${cols * 100}% ${rows * 100}%`,
    backgroundPosition: `${cols > 1 ? (c / (cols - 1)) * 100 : 0}% ${rows > 1 ? (r / (rows - 1)) * 100 : 0}%`,
    backgroundRepeat: 'no-repeat',
  }
}

export function indexAtTime(sb: Storyboard, t: number): number {
  return Math.floor(t / (sb.meta.interval || 1))
}

/**
 * Grid card overlay: sits over the thumbnail. Mouse: move across to scrub. Touch: drag across.
 * Hover intent (90 ms) before loading, so sweeping the pointer over a grid doesn't fetch every card.
 */
export function ScrubOverlay({ assetId }: { assetId: string }) {
  const { sb, want } = useStoryboard(assetId)
  const [frac, setFrac] = React.useState<number | null>(null)
  const timer = React.useRef<ReturnType<typeof setTimeout> | null>(null)

  const onEnter = () => { timer.current = setTimeout(want, 90) }
  const onLeave = () => { if (timer.current) clearTimeout(timer.current); setFrac(null) }
  const onMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    setFrac(Math.max(0, Math.min(0.9999, (e.clientX - r.left) / r.width)))
  }

  const active = sb && frac !== null
  const idx = sb && frac !== null ? Math.floor(frac * sb.meta.count) : 0
  return (
    <div
      className="absolute inset-0"
      style={{ touchAction: 'pan-y' }}
      onPointerEnter={onEnter}
      onPointerLeave={onLeave}
      onPointerMove={onMove}
      onPointerDown={(e) => { if (e.pointerType === 'touch') want() }}
      data-osc-scrub={active ? idx : undefined}
    >
      {active && (
        <>
          <div className="absolute inset-0 flex items-center justify-center bg-black pointer-events-none">
            <div className="w-full" style={{ aspectRatio: `${sb!.meta.tile_w} / ${sb!.meta.tile_h}`, ...tileStyle(sb!, idx) }} />
          </div>
          <div className="absolute left-0 bottom-0 h-[3px] bg-accent pointer-events-none"
               style={{ width: `${((idx + 1) / sb!.meta.count) * 100}%` }} />
        </>
      )}
    </div>
  )
}
