'use client'

/**
 * OSC 0020 (Sam 10/8 19:05: "I want review links and delivery links. It should be clear which type is
 * which."): the recipient sees the link's kind next to its title. Review = watch and leave notes;
 * Delivery = the final file to download. Fails soft: renders nothing if the kind can't be read.
 */
import * as React from 'react'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export function ShareKindBadge({ token, shareSession }: { token: string; shareSession?: string | null }) {
  const [kind, setKind] = React.useState<'review' | 'delivery' | null>(null)
  React.useEffect(() => {
    let alive = true
    const qs = shareSession ? `?share_session=${encodeURIComponent(shareSession)}` : ''
    fetch(`${API_URL}/share/${token}/osc-kind${qs}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (alive && d && (d.kind === 'review' || d.kind === 'delivery')) setKind(d.kind)
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [token, shareSession])
  if (!kind) return null
  const delivery = kind === 'delivery'
  return (
    <span
      data-osc-share-kind={kind}
      title={delivery ? 'The final version, ready to download' : 'A cut for review: watch it and leave notes'}
      className={
        'inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ' +
        (delivery ? 'bg-emerald-500/15 text-emerald-400' : 'bg-accent/15 text-accent')
      }
    >
      {delivery ? 'Delivery' : 'Review'}
    </span>
  )
}
