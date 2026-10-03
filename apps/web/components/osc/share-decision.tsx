'use client'

/**
 * OSC 0010: client approval from a share link. Rendered only when the link's permission is
 * "approve". Approve (green) / Request changes (with a note). Uses the signed-in session or the
 * guest identity the share page already keeps (ff_guest_identity); asks for name + email once if
 * neither exists. Shows who has decided on this version so far.
 */
import * as React from 'react'
import { Check, RotateCcw, Loader2 } from 'lucide-react'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
type Decision = { name: string; decision: 'approved' | 'rejected'; at: string | null }

function guestIdentity(): { name: string; email: string } | null {
  try { const s = localStorage.getItem('ff_guest_identity'); return s ? JSON.parse(s) : null } catch { return null }
}

export function ShareDecision({ token, shareSession, assetId, versionId, permission }: {
  token: string; shareSession?: string | null; assetId: string; versionId?: string; permission: string
}) {
  const [decisions, setDecisions] = React.useState<Decision[]>([])
  const [mode, setMode] = React.useState<null | 'approved' | 'rejected'>(null)
  const [note, setNote] = React.useState('')
  const [name, setName] = React.useState('')
  const [email, setEmail] = React.useState('')
  const [busy, setBusy] = React.useState(false)
  const [msg, setMsg] = React.useState<string | null>(null)
  const qs = `asset_id=${assetId}${versionId ? `&version_id=${versionId}` : ''}${shareSession ? `&share_session=${shareSession}` : ''}`

  const load = React.useCallback(async () => {
    try {
      const r = await fetch(`${API_URL}/share/${token}/decisions?${qs}`)
      if (r.ok) setDecisions(await r.json())
    } catch {}
  }, [token, qs])
  React.useEffect(() => { if (permission === 'approve') load() }, [permission, load])
  if (permission !== 'approve') return null

  const signedIn = typeof window !== 'undefined' && !!localStorage.getItem('ff_access_token')
  const known = signedIn || !!guestIdentity()

  async function send(decision: 'approved' | 'rejected') {
    setBusy(true); setMsg(null)
    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' }
      const t = localStorage.getItem('ff_access_token')
      if (t) headers.Authorization = `Bearer ${t}`
      let gi = guestIdentity()
      if (!t && !gi && name.trim() && email.trim()) {
        gi = { name: name.trim(), email: email.trim() }
        localStorage.setItem('ff_guest_identity', JSON.stringify(gi))
      }
      const body = { decision, note: note.trim() || undefined, asset_id: assetId, version_id: versionId,
                     guest_name: gi?.name, guest_email: gi?.email }
      const r = await fetch(`${API_URL}/share/${token}/decision${shareSession ? `?share_session=${shareSession}` : ''}`,
                            { method: 'POST', headers, body: JSON.stringify(body) })
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'Could not send')
      setMsg(decision === 'approved' ? 'Approved. Thank you!' : 'Sent. Thank you!')
      setMode(null); setNote(''); load()
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Could not send')
    } finally { setBusy(false) }
  }

  const mine = decisions[decisions.length - 1]
  return (
    <div className="relative flex items-center gap-1.5" data-osc-share-decision>
      {mine && (
        <span className="hidden sm:inline text-[11px] text-text-tertiary mr-1">
          {mine.decision === 'approved' ? 'Approved' : 'Changes requested'} by {mine.name}
        </span>
      )}
      <button type="button" disabled={busy} onClick={() => setMode(mode === 'approved' ? null : 'approved')}
        className="inline-flex items-center gap-1 h-7 px-2.5 rounded-md text-xs font-semibold text-white disabled:opacity-60"
        style={{ background: '#15803D' }}>
        <Check className="h-3.5 w-3.5" /> Approve
      </button>
      <button type="button" disabled={busy} onClick={() => setMode(mode === 'rejected' ? null : 'rejected')}
        className="inline-flex items-center gap-1 h-7 px-2.5 rounded-md text-xs font-medium border border-border text-text-secondary hover:text-text-primary hover:bg-bg-hover">
        <RotateCcw className="h-3.5 w-3.5" /> <span className="hidden sm:inline">Request changes</span><span className="sm:hidden">Changes</span>
      </button>
      {mode && (
        <div className="absolute right-0 top-9 z-50 w-72 rounded-xl border border-border bg-bg-elevated shadow-2xl p-3 space-y-2">
          <p className="text-sm text-text-primary font-medium">
            {mode === 'approved' ? 'Approve this version?' : 'What should change?'}
          </p>
          {!known && (
            <div className="flex gap-2">
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name"
                className="flex-1 min-w-0 h-8 rounded-md border border-border bg-bg-hover px-2 text-xs text-text-primary" />
              <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" type="email"
                className="flex-1 min-w-0 h-8 rounded-md border border-border bg-bg-hover px-2 text-xs text-text-primary" />
            </div>
          )}
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={mode === 'rejected' ? 3 : 2}
            placeholder={mode === 'approved' ? 'Optional note' : 'A short note helps (or leave timecoded comments)'}
            className="w-full rounded-md border border-border bg-bg-hover px-2 py-1.5 text-xs text-text-primary" />
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setMode(null)} className="h-7 px-2.5 text-xs text-text-tertiary">Cancel</button>
            <button type="button" disabled={busy || (!known && (!name.trim() || !email.trim()))}
              onClick={() => send(mode)}
              className="inline-flex items-center gap-1 h-7 px-3 rounded-md text-xs font-semibold text-white disabled:opacity-50"
              style={{ background: mode === 'approved' ? '#15803D' : '#DC2626' }}>
              {busy && <Loader2 className="h-3 w-3 animate-spin" />}
              {mode === 'approved' ? 'Approve' : 'Send'}
            </button>
          </div>
        </div>
      )}
      {msg && <span className="text-[11px] text-text-secondary ml-1" role="status">{msg}</span>}
    </div>
  )
}
