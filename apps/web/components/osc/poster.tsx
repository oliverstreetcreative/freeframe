'use client'

/**
 * OSC: choose the grid thumbnail from the player (Sam 10/2 23:57: "scrub to an image and hit a
 * hotkey to change the thumbnail"). Hotkey T = use the frame under the playhead; the menu has the
 * same action for touch, plus Shuffle (a fresh random good frame). Staff only (the API refuses
 * everyone else). Each version keeps its own poster.
 */
import * as React from 'react'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { ImageIcon, Shuffle, Loader2 } from 'lucide-react'
import { api } from '@/lib/api'
import { useReviewStore } from '@/stores/review-store'
import { useToast } from '@/components/shared/toast'

function isTyping(el: Element | null): boolean {
  if (!el) return false
  const tag = el.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (el as HTMLElement).isContentEditable
}

export function PosterMenu({ assetId, versionId }: { assetId: string; versionId?: string }) {
  const { toast } = useToast()
  const [busy, setBusy] = React.useState(false)
  const busyRef = React.useRef(false)

  const run = React.useCallback(async (random: boolean) => {
    if (busyRef.current) return
    busyRef.current = true; setBusy(true)
    try {
      const time = useReviewStore.getState().playheadTime
      const r = await api.post<{ time: number }>(`/assets/${assetId}/poster`,
        random ? { random: true, version_id: versionId } : { time, version_id: versionId })
      const s = r.time
      const tc = `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`
      toast(random ? `Thumbnail shuffled (${tc})` : `Thumbnail updated (${tc})`, 'success', 2500)
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Could not set the thumbnail', 'error')
    } finally {
      busyRef.current = false; setBusy(false)
    }
  }, [assetId, versionId, toast])

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 't' && e.key !== 'T') return
      if (e.metaKey || e.ctrlKey || e.altKey || isTyping(document.activeElement)) return
      e.preventDefault()
      run(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [run])

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button type="button" title="Thumbnail (T = use this frame)" aria-label="Thumbnail options"
          className="inline-flex items-center gap-1.5 rounded-md px-2.5 h-8 text-xs font-medium border border-border text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors outline-none focus-visible:[box-shadow:0_0_0_2px_var(--bg-primary),0_0_0_4px_var(--accent)]">
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ImageIcon className="h-3.5 w-3.5" />}
          Thumbnail
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={6}
          className="z-[100] min-w-[220px] rounded-xl border border-border bg-bg-elevated shadow-2xl py-1.5">
          <DropdownMenu.Item onSelect={() => run(false)}
            className="flex items-center gap-2.5 mx-1 px-2.5 py-2 rounded-lg text-sm text-text-secondary hover:bg-bg-hover hover:text-text-primary cursor-pointer outline-none">
            <ImageIcon className="h-3.5 w-3.5 text-text-tertiary" />
            <span className="flex-1">Use this frame</span>
            <kbd className="text-[10px] text-text-tertiary border border-border rounded px-1">T</kbd>
          </DropdownMenu.Item>
          <DropdownMenu.Item onSelect={() => run(true)}
            className="flex items-center gap-2.5 mx-1 px-2.5 py-2 rounded-lg text-sm text-text-secondary hover:bg-bg-hover hover:text-text-primary cursor-pointer outline-none">
            <Shuffle className="h-3.5 w-3.5 text-text-tertiary" />
            <span className="flex-1">Shuffle (random frame)</span>
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}
