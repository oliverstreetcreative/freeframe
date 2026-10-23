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
/** A sharp tier (Sam 10/3 00:40, iPhone "really fuzzy"): tiles >= CSS size x DPR, split into sheets. */
export interface StoryboardTier { w: number; h: number; cols: number; rows: number; per_sheet: number; sheets: number; urls: string[] }
export interface Storyboard { url: string; meta: StoryboardMeta; tiers: StoryboardTier[] }

const cache = new Map<string, Promise<Storyboard | null>>()

/** Fetch + preload + decode the small sheet, once per asset (newest version). null = none available. */
export function loadStoryboard(assetId: string): Promise<Storyboard | null> {
  let p = cache.get(assetId)
  // Share-link guests have no session; the storyboard route is staff/member-only. Don't even ask
  // (the player falls back to upstream's decoder preview there).
  let signedIn = false
  try { signedIn = !!localStorage.getItem('ff_access_token') } catch {}
  if (!signedIn) return Promise.resolve(null)
  if (!p) {
    p = api.get<{ url: string; meta: StoryboardMeta; tiers?: StoryboardTier[] }>(`/assets/${assetId}/storyboard`)
      .then(async (r) => {
        const img = new Image()
        img.src = r.url
        try { await img.decode() } catch { /* still usable once loaded */ }
        return { url: r.url, meta: r.meta, tiers: r.tiers ?? [] }
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

// ---- sharp sheets: decoded in the background, swapped in per frame as each sheet lands ----------
const decoded = new Set<string>()
const pending = new Set<string>()
const sheetListeners = new Set<() => void>()
let sheetVersion = 0

function decodeSheet(url: string) {
  if (decoded.has(url) || pending.has(url)) return
  pending.add(url)
  const img = new Image()
  img.src = url
  img.decode().catch(() => undefined).then(() => {
    pending.delete(url)
    decoded.add(url)
    sheetVersion++
    sheetListeners.forEach((l) => l())
  })
}

/** Smallest tier whose tiles cover `needPx` device pixels; else the biggest there is. */
export function pickTier(sb: Storyboard, needPx: number): StoryboardTier | null {
  if (!sb.tiers?.length || needPx <= sb.meta.tile_w) return null
  const sorted = [...sb.tiers].sort((a, b) => a.w - b.w)
  return sorted.find((t) => t.w >= needPx) ?? sorted[sorted.length - 1]
}

/**
 * Start decoding the tier that `needPx` (CSS width x devicePixelRatio) calls for, and re-render as
 * its sheets land. The sheet holding `nearIdx` goes first, so the frame under the finger sharpens first.
 */
export function useSharpTier(sb: Storyboard | null, needPx: number, nearIdx = 0): StoryboardTier | null {
  const tier = sb ? pickTier(sb, needPx) : null
  React.useSyncExternalStore(
    (l) => { sheetListeners.add(l); return () => { sheetListeners.delete(l) } },
    () => sheetVersion,
    () => sheetVersion,
  )
  const firstSheet = tier ? Math.min(tier.sheets - 1, Math.floor(Math.max(0, nearIdx) / tier.per_sheet)) : 0
  React.useEffect(() => {
    if (!tier) return
    decodeSheet(tier.urls[firstSheet])
    tier.urls.forEach((u) => decodeSheet(u))
  }, [tier, firstSheet])
  return tier
}

/** The tile for frame `i`, scaled to fill a box of the tile's aspect. Uses the sharp tier's sheet
 *  for that frame once it's decoded, else the small 160 px sheet (instant). */
export function tileStyle(sb: Storyboard, i: number, tier?: StoryboardTier | null): React.CSSProperties {
  const idx = Math.max(0, Math.min(sb.meta.count - 1, i))
  if (tier) {
    const s = Math.floor(idx / tier.per_sheet)
    const url = tier.urls[s]
    if (url && decoded.has(url)) {
      const j = idx % tier.per_sheet
      const c = j % tier.cols
      const r = Math.floor(j / tier.cols)
      return {
        backgroundImage: `url("${url}")`,
        backgroundSize: `${tier.cols * 100}% ${tier.rows * 100}%`,
        backgroundPosition: `${tier.cols > 1 ? (c / (tier.cols - 1)) * 100 : 0}% ${tier.rows > 1 ? (r / (tier.rows - 1)) * 100 : 0}%`,
        backgroundRepeat: 'no-repeat',
      }
    }
  }
  const { cols, rows } = sb.meta
  const c = idx % cols
  const r = Math.floor(idx / cols)
  return {
    backgroundImage: `url("${sb.url}")`,
    backgroundSize: `${cols * 100}% ${rows * 100}%`,
    backgroundPosition: `${cols > 1 ? (c / (cols - 1)) * 100 : 0}% ${rows > 1 ? (r / (rows - 1)) * 100 : 0}%`,
    backgroundRepeat: 'no-repeat',
  }
}

export function dpr(): number {
  return typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1
}

export function indexAtTime(sb: Storyboard, t: number): number {
  return Math.floor(t / (sb.meta.interval || 1))
}

/**
 * Grid card overlay: sits over the thumbnail.
 *  - Mouse: hover intent (90 ms) loads the sheet, then moving across scrubs.
 *  - Touch (Sam 10/3 00:20, iPhone: "a flash of a frame change, but that's it"): pointer events
 *    got cancelled the moment Safari claimed the gesture for scrolling, and the sheet only started
 *    loading on that first touch. Now: the sheet PRELOADS when the card scrolls into view on a
 *    touch device; touch is handled with native touchstart/touchmove (passive: false) and a
 *    direction lock: a horizontal drag scrubs (preventDefault, so the page doesn't scroll) and
 *    the frames follow the finger continuously; a vertical drag is left alone, so the page scrolls.
 *    A tap (no drag) still opens the asset.
 */
const isCoarse = () => typeof window !== 'undefined' && !!window.matchMedia?.('(pointer: coarse)').matches

export function ScrubOverlay({ assetId }: { assetId: string }) {
  const { sb, want } = useStoryboard(assetId)
  const [frac, setFrac] = React.useState<number | null>(null)
  const timer = React.useRef<ReturnType<typeof setTimeout> | null>(null)
  const ref = React.useRef<HTMLDivElement>(null)

  // Touch devices: load before the first touch, as the card comes into view.
  React.useEffect(() => {
    const el = ref.current
    if (!el || !isCoarse() || typeof IntersectionObserver === 'undefined') return
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) { want(); io.disconnect() }
    }, { rootMargin: '200px' })
    io.observe(el)
    return () => io.disconnect()
  }, [want])

  // Native touch listeners (React's touch handlers are passive, so they can't preventDefault).
  React.useEffect(() => {
    const el = ref.current
    if (!el) return
    let x0 = 0, y0 = 0, mode: 'none' | 'scrub' | 'scroll' = 'none'
    const fracAt = (clientX: number) => {
      const r = el.getBoundingClientRect()
      return Math.max(0, Math.min(0.9999, (clientX - r.left) / r.width))
    }
    const start = (e: TouchEvent) => {
      if (e.touches.length !== 1) { mode = 'scroll'; return }
      x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; mode = 'none'
      want()
    }
    const move = (e: TouchEvent) => {
      if (mode === 'scroll' || e.touches.length !== 1) return
      const t = e.touches[0]
      if (mode === 'none') {
        const dx = Math.abs(t.clientX - x0), dy = Math.abs(t.clientY - y0)
        if (dx < 6 && dy < 6) return
        mode = dx > dy ? 'scrub' : 'scroll'
        if (mode === 'scroll') return
      }
      e.preventDefault()          // we own this gesture: no page scroll, no click afterwards
      setFrac(fracAt(t.clientX))
    }
    const end = () => { if (mode === 'scrub') setTimeout(() => setFrac(null), 600); mode = 'none' }
    el.addEventListener('touchstart', start, { passive: true })
    el.addEventListener('touchmove', move, { passive: false })
    el.addEventListener('touchend', end)
    el.addEventListener('touchcancel', end)
    return () => {
      el.removeEventListener('touchstart', start)
      el.removeEventListener('touchmove', move)
      el.removeEventListener('touchend', end)
      el.removeEventListener('touchcancel', end)
    }
  }, [want])

  // Mouse/pen only; touch is handled natively above.
  const onEnter = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.pointerType === 'touch') return
    timer.current = setTimeout(want, 90)
  }
  const onLeave = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.pointerType === 'touch') return
    if (timer.current) clearTimeout(timer.current)
    setFrac(null)
  }
  const onMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.pointerType === 'touch') return
    const r = e.currentTarget.getBoundingClientRect()
    setFrac(Math.max(0, Math.min(0.9999, (e.clientX - r.left) / r.width)))
  }

  const active = sb && frac !== null
  const idx = sb && frac !== null ? Math.floor(frac * sb.meta.count) : 0
  // tiles must be >= this card's CSS width x devicePixelRatio to look sharp (3x on iPhone)
  const [needPx, setNeedPx] = React.useState(0)
  React.useEffect(() => {
    const el = ref.current
    if (!el || !sb) return
    setNeedPx(Math.ceil(el.getBoundingClientRect().width * dpr()))
  }, [sb])
  const tier = useSharpTier(sb, needPx, idx)
  return (
    <div
      ref={ref}
      className="absolute inset-0"
      style={{ touchAction: 'pan-y' }}
      onPointerEnter={onEnter}
      onPointerLeave={onLeave}
      onPointerMove={onMove}
      data-osc-scrub={active ? idx : undefined}
      data-osc-scrub-ready={sb ? 'yes' : 'no'}
      data-osc-scrub-tier={tier ? tier.w : sb ? sb.meta.tile_w : undefined}
    >
      {active && (
        <>
          <div className="absolute inset-0 flex items-center justify-center bg-black pointer-events-none">
            <div className="w-full" style={{ aspectRatio: `${sb!.meta.tile_w} / ${sb!.meta.tile_h}`, ...tileStyle(sb!, idx, tier) }} />
          </div>
          <div className="absolute left-0 bottom-0 h-[3px] bg-accent pointer-events-none"
               style={{ width: `${((idx + 1) / sb!.meta.count) * 100}%` }} />
        </>
      )}
    </div>
  )
}
