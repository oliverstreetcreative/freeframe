import * as React from 'react'
import { cn } from '@/lib/utils'
import { statusMeta } from '@/lib/osc-status'
import type { AssetStatus } from '@/types'

/** Read-only counterpart of the grid/player pill, with the same labels and tones. */
export function Badge({ status, className }: { status: AssetStatus; className?: string }) {
  const meta = statusMeta(status)
  return (
    <span data-osc-status={status}
      className={cn('inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-2xs font-medium', className)}
      style={{ background: meta.bg, color: meta.fg }}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: meta.fg }} />
      {meta.label}
    </span>
  )
}
