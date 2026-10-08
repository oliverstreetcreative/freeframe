'use client'

/**
 * OSC 0019: share KINDS. A link is a REVIEW link (comments on, download off) or a DELIVERY link
 * (view only, download on, latest version only = the clean master), and carries an INTERNAL LABEL
 * only OSC staff see. Both live in the OSC API (routers/osc_share_meta.py), not on the link itself.
 */
import useSWR, { mutate as globalMutate } from 'swr'
import { api } from '@/lib/api'
import { getAccessToken, refreshAccessToken } from '@/lib/auth'
import type { ShareLink } from '@/types'

export type ShareKind = 'review' | 'delivery'

export interface ShareMetaEntry {
  kind: ShareKind
  internal_label: string | null
  /** true = no row stored yet; the kind was read off the link's settings */
  inferred: boolean
}

export type ShareMetaMap = Record<string, ShareMetaEntry>

export interface ShareMetaPutBody {
  kind?: ShareKind
  internal_label?: string | null
  force?: boolean
}

export interface ShareMetaPutResult {
  kind: ShareKind
  internal_label: string | null
  permission: string
  allow_download: boolean
  show_versions: boolean
}

export type ShareMetaPutOutcome =
  | { ok: true; result: ShareMetaPutResult }
  /** status 409 = the slate guard: `slated` names the items whose top version still has the slate */
  | { ok: false; status: number; detail: string; slated: string[] }

export const KIND_LABEL: Record<ShareKind, string> = { review: 'Review', delivery: 'Delivery' }

export const KIND_HINT: Record<ShareKind, string> = {
  review: 'Comments on, downloads off.',
  delivery: 'View only, downloads on, only the newest version (the clean master).',
}

export function shareMetaKey(projectId: string | null | undefined): string | null {
  return projectId ? `/osc/projects/${projectId}/share-meta` : null
}

/** Same rule as the API when no row is stored: view-only + download = delivery. */
export function inferKind(link: Pick<ShareLink, 'permission' | 'allow_download'>): ShareKind {
  return link.permission === 'view' && link.allow_download ? 'delivery' : 'review'
}

export function useShareMeta(projectId: string | null | undefined) {
  const { data, mutate } = useSWR<ShareMetaMap>(
    shareMetaKey(projectId),
    (key: string) => api.get<ShareMetaMap>(key),
    { shouldRetryOnError: false },
  )
  return { shareMeta: data ?? {}, mutateShareMeta: mutate }
}

export function refreshShareMeta(projectId: string | null | undefined) {
  const key = shareMetaKey(projectId)
  if (key) globalMutate(key)
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

/**
 * PUT /osc/share-links/{id}/meta. A raw fetch rather than `api.put` because the slate guard's 409
 * carries `slated` beside `detail`, and ApiError keeps only `detail`.
 */
export async function putShareMeta(linkId: string, body: ShareMetaPutBody): Promise<ShareMetaPutOutcome> {
  const send = (token: string | null) =>
    fetch(`${API_URL}/osc/share-links/${linkId}/meta`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    })
  try {
    let resp = await send(getAccessToken())
    if (resp.status === 401) {
      const fresh = await refreshAccessToken()
      if (fresh) resp = await send(fresh)
    }
    const data = await resp.json().catch(() => null)
    if (resp.ok) return { ok: true, result: data as ShareMetaPutResult }
    const detail =
      data && typeof data.detail === 'string' ? data.detail : resp.statusText || 'Could not save the link kind'
    const slated = data && Array.isArray(data.slated) ? data.slated.map(String) : []
    return { ok: false, status: resp.status, detail, slated }
  } catch (e) {
    return { ok: false, status: 0, detail: e instanceof Error ? e.message : 'Network error', slated: [] }
  }
}
