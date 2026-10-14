'use client'

import * as React from 'react'
import * as Switch from '@radix-ui/react-switch'
import { ShareScopePreview } from './share-scope-preview'
import { useMediaQuery } from '@/hooks/use-media-query'
import { Search, Folder, File, Copy, Check, Eye } from 'lucide-react'
import { cn, copyToClipboard } from '@/lib/utils'
import { formatRelativeTime } from '@/lib/utils'
import { withBasePath } from '@/lib/base-path'
import type { ShareLinkListItem } from '@/types'
import { useShareMeta } from '@/hooks/use-share-meta'
import { KindBadge } from '@/components/projects/share-kind-controls'

interface ShareLinksTableProps {
  /** OSC 0019: for the kind / internal-label map */
  projectId?: string
  shareLinks: ShareLinkListItem[]
  onSelectLink: (token: string) => void
  onToggleEnabled: (token: string, enabled: boolean) => void
  onViewActivity: (token: string) => void
  frontendUrl: string
}

export function ShareLinksTable({
  projectId,
  shareLinks,
  onSelectLink,
  onToggleEnabled,
  onViewActivity,
  frontendUrl,
}: ShareLinksTableProps) {
  const isDesktop = useMediaQuery('(min-width: 768px)')
  const [search, setSearch] = React.useState('')
  const [copyFailed, setCopyFailed] = React.useState(false)
  const [copiedToken, setCopiedToken] = React.useState<string | null>(null)
  // OSC 0019: staff see the INTERNAL label first; the public title is what the client sees.
  const { shareMeta } = useShareMeta(projectId)

  const filtered = React.useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return shareLinks
    return shareLinks.filter(
      (link) =>
        link.title.toLowerCase().includes(q) ||
        (link.target_name ?? '').toLowerCase().includes(q) ||
        (shareMeta[link.id]?.internal_label ?? '').toLowerCase().includes(q),
    )
  }, [shareLinks, search, shareMeta])

  const handleCopy = React.useCallback(
    async (token: string, e: React.MouseEvent) => {
      e.stopPropagation()
      const url = `${frontendUrl}${withBasePath(`/share/${token}`)}`
      const ok = await copyToClipboard(url)
      setCopyFailed(!ok)
      if (!ok) return
      setCopiedToken(token)
      setTimeout(() => setCopiedToken(null), 2000)
    },
    [frontendUrl],
  )

  return (
    <div className="flex min-w-0 w-full flex-col">
      {/* Search bar */}
      <div className="relative mb-3">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-tertiary pointer-events-none" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search for Shares"
          className="w-full h-9 pl-9 pr-3 rounded-lg border border-border bg-bg-tertiary text-[16px] sm:text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-border-focus transition-colors"
        />
      </div>

      {copyFailed && <p role="status" className="text-xs text-status-error">Copy failed. Select the URL and copy it manually.</p>}
      {/* Table */}
      {filtered.length === 0 ? (
        <div className="flex-1 flex items-center justify-center py-16 text-center">
          <p className="text-sm text-text-tertiary">
            {shareLinks.length === 0
              ? 'No share links yet. Create one by sharing an asset or folder.'
              : 'No share links match your search.'}
          </p>
        </div>
      ) : !isDesktop ? (
        <div className="space-y-3 min-w-0" aria-label="Share links">
          {filtered.map(link => {
            const meta = shareMeta[link.id]
            const label = meta?.internal_label?.trim() || link.title
            const url = `${frontendUrl}${withBasePath(`/share/${link.token}`)}`
            return <article key={link.token} className="min-w-0 rounded-lg border border-border bg-bg-secondary p-3 space-y-3">
              <button onClick={() => onSelectLink(link.token)} className="block w-full min-w-0 text-left">
                <span className="block text-sm font-medium text-text-primary break-words [overflow-wrap:anywhere]">{label}</span>
                {meta && <span className="inline-flex mt-1"><KindBadge kind={meta.kind}/></span>}
                {meta?.internal_label && <span className="block mt-1 text-xs text-text-tertiary break-words [overflow-wrap:anywhere]">Client sees: {link.title}</span>}
              </button>
              <ShareScopePreview token={link.token} enabled={link.is_enabled} targetName={link.target_name || link.title}/>
              <div className="flex min-w-0 items-center gap-2">
                <input aria-label={`Share URL for ${label}`} readOnly value={url} onFocus={e=>e.currentTarget.select()} className="min-w-0 flex-1 rounded border border-border bg-bg-tertiary px-2 py-2 text-[16px] font-mono text-text-secondary"/>
                <button title="Copy link" onClick={e=>handleCopy(link.token,e)} className="shrink-0 rounded border border-border px-3 py-2 text-sm">{copiedToken===link.token?'Copied!':'Copy'}</button>
              </div>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-text-tertiary">
                <label className="flex items-center gap-2">Enabled<Switch.Root aria-label={`Enable ${label}`} checked={link.is_enabled} onCheckedChange={checked=>onToggleEnabled(link.token,checked)} className="relative h-5 w-9 rounded-full bg-border data-[state=checked]:bg-accent"><Switch.Thumb className="block h-4 w-4 rounded-full bg-white translate-x-[2px] data-[state=checked]:translate-x-[18px]"/></Switch.Root></label>
                <span>{link.view_count} {link.view_count===1?'view':'views'}</span>
                <span>Last viewed: {link.last_viewed_at?formatRelativeTime(link.last_viewed_at):'Never'}</span>
                <button onClick={()=>onViewActivity(link.token)} className="py-1 text-text-secondary">View activity</button>
              </div>
            </article>
          })}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-border bg-bg-secondary">
                <th className="px-4 py-2.5 text-left text-xs font-semibold text-text-tertiary uppercase tracking-wider">
                  Title
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold text-text-tertiary uppercase tracking-wider">
                  Link
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold text-text-tertiary uppercase tracking-wider">
                  Visibility
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold text-text-tertiary uppercase tracking-wider">
                  Access Type
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold text-text-tertiary uppercase tracking-wider">
                  Last Viewed
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold text-text-tertiary uppercase tracking-wider">
                  Views
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold text-text-tertiary uppercase tracking-wider">
                  Activity
                </th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((link, i) => {
                const shareUrl = `${frontendUrl}${withBasePath(`/share/${link.token}`)}`
                const isCopied = copiedToken === link.token
                const isLast = i === filtered.length - 1
                const meta = shareMeta[link.id]
                const internalLabel = meta?.internal_label?.trim() || ''

                return (
                  <tr
                    key={link.token}
                    className={cn(
                      'group transition-colors hover:bg-bg-hover/40',
                      !isLast && 'border-b border-border',
                    )}
                  >
                    {/* Title */}
                    <td className="px-4 py-3">
                      <button
                        onClick={() => onSelectLink(link.token)}
                        className="flex items-center gap-2 text-left hover:text-accent transition-colors"
                      >
                        {link.share_type === 'folder' ? (
                          <Folder className="h-4 w-4 text-text-tertiary shrink-0" />
                        ) : (
                          <File className="h-4 w-4 text-text-tertiary shrink-0" />
                        )}
                        <span className="flex flex-col min-w-0">
                          <span className="flex items-center gap-1.5 min-w-0">
                            <span className="text-text-primary font-medium truncate max-w-[180px]">
                              {internalLabel || link.title}
                            </span>
                            {meta && <KindBadge kind={meta.kind} />}
                          </span>
                          {internalLabel && (
                            <span className="text-xs text-text-tertiary truncate max-w-[220px]">
                              Client sees: {link.title}
                            </span>
                          )}
                        </span>
                      </button>
                    </td>

                    {/* Link */}
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="inline-flex items-center rounded-md border border-border bg-bg-tertiary px-2 py-1 text-xs text-text-secondary font-mono select-text whitespace-nowrap max-w-[200px] overflow-hidden text-ellipsis">
                          {shareUrl}
                        </span>
                        <button
                          onClick={(e) => handleCopy(link.token, e)}
                          className="flex items-center justify-center h-6 w-6 rounded border border-border bg-bg-tertiary hover:bg-bg-hover text-text-tertiary hover:text-text-primary transition-colors shrink-0"
                          title="Copy link"
                        >
                          {isCopied ? (
                            <Check className="h-3 w-3 text-green-400" />
                          ) : (
                            <Copy className="h-3 w-3" />
                          )}
                        </button>
                      </div>
                    </td>

                    {/* Visibility (toggle) */}
                    <td className="px-4 py-3">
                      <Switch.Root
                        checked={link.is_enabled}
                        onCheckedChange={(checked) => onToggleEnabled(link.token, checked)}
                        className={cn(
                          'relative h-5 w-9 rounded-full transition-colors outline-none cursor-pointer',
                          link.is_enabled ? 'bg-accent' : 'bg-border',
                        )}
                      >
                        <Switch.Thumb
                          className={cn(
                            'block h-4 w-4 rounded-full bg-white transition-transform',
                            link.is_enabled ? 'translate-x-[18px]' : 'translate-x-[2px]',
                          )}
                        />
                      </Switch.Root>
                    </td>

                    {/* Access Type */}
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center rounded-full border border-border bg-bg-tertiary px-2 py-0.5 text-xs text-text-secondary">
                        Public
                      </span>
                    </td>

                    {/* Last Viewed */}
                    <td className="px-4 py-3">
                      <span className="text-xs text-text-tertiary">
                        {link.last_viewed_at ? formatRelativeTime(link.last_viewed_at) : '—'}
                      </span>
                    </td>

                    {/* Views */}
                    <td className="px-4 py-3">
                      <span className="text-sm text-text-secondary tabular-nums">
                        {link.view_count}
                      </span>
                    </td>

                    {/* Activity */}
                    <td className="px-4 py-3">
                      <button
                        onClick={() => onViewActivity(link.token)}
                        className="flex items-center gap-1.5 text-xs text-text-tertiary hover:text-text-primary transition-colors"
                      >
                        <Eye className="h-3.5 w-3.5" />
                        View Activity
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Footer count */}
      <div className="mt-3 shrink-0">
        <span className="text-xs text-text-tertiary">
          {shareLinks.length} {shareLinks.length === 1 ? 'Share' : 'Shares'}
        </span>
      </div>
    </div>
  )
}
