'use client'

/**
 * OSC 0019: the Review | Delivery switch and the slate-guard notice, shared by the share-link
 * settings page and the create dialog.
 */
import * as React from 'react'
import { AlertTriangle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { KIND_LABEL, type ShareKind } from '@/hooks/use-share-meta'

export function KindToggle({
  value,
  onChange,
  disabled,
}: {
  value: ShareKind
  onChange: (kind: ShareKind) => void
  disabled?: boolean
}) {
  return (
    <div className="flex rounded-lg border border-border overflow-hidden shrink-0" role="radiogroup" aria-label="Link kind">
      {(['review', 'delivery'] as const).map((k) => (
        <button
          key={k}
          type="button"
          role="radio"
          aria-checked={value === k}
          disabled={disabled}
          onClick={() => value !== k && onChange(k)}
          className={cn(
            'px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-60',
            value === k ? 'bg-accent text-text-inverse' : 'text-text-secondary hover:text-text-primary',
          )}
        >
          {KIND_LABEL[k]}
        </button>
      ))}
    </div>
  )
}

export function KindBadge({ kind }: { kind: ShareKind }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-1.5 py-0.5 text-2xs font-medium shrink-0',
        kind === 'delivery'
          ? 'border-green-500/30 bg-green-500/10 text-green-400'
          : 'border-border bg-bg-tertiary text-text-secondary',
      )}
    >
      {KIND_LABEL[kind]}
    </span>
  )
}

/** The 409 from the slate guard: which items still have the review slate on their top version. */
export function SlateGuardNotice({
  detail,
  slated,
  busy,
  onForce,
  onCancel,
  cancelLabel = 'Cancel',
}: {
  detail: string
  slated: string[]
  busy?: boolean
  onForce: () => void
  onCancel: () => void
  cancelLabel?: string
}) {
  return (
    <div className="rounded-md border border-status-warning/30 bg-status-warning/10 px-3 py-2.5 space-y-2">
      <div className="flex items-start gap-2">
        <AlertTriangle className="h-4 w-4 text-status-warning shrink-0 mt-0.5" />
        <p className="text-xs text-text-primary">{detail}</p>
      </div>
      {slated.length > 0 && (
        <ul className="pl-6 list-disc text-xs text-text-secondary space-y-0.5">
          {slated.map((name, i) => (
            <li key={`${name}-${i}`} className="break-words">{name}</li>
          ))}
        </ul>
      )}
      <div className="flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          disabled={busy}
          className="px-3 py-1 text-xs text-text-secondary hover:text-text-primary transition-colors disabled:opacity-60"
        >
          {cancelLabel}
        </button>
        <button
          type="button"
          onClick={onForce}
          disabled={busy}
          className="px-3 py-1 rounded-md bg-accent text-xs font-medium text-text-inverse hover:bg-accent/90 transition-colors disabled:opacity-60"
        >
          Use anyway
        </button>
      </div>
    </div>
  )
}
