'use client'
import useSWR from 'swr'
import { api } from '@/lib/api'
import type { ShareLink, FolderShareAssetsResponse } from '@/types'
export interface ShareScopePreview {
  assets: { id: string; name: string; asset_type: string; thumbnail_url?: string | null }[]
  folders: { id: string; name: string; item_count: number }[]
  total: number
}
export async function fetchShareScopePreview(token: string): Promise<ShareScopePreview> {
  const link = await api.get<ShareLink>(`/share/${token}/details`)
  if (link.asset_id) {
    const asset = await api.get<ShareScopePreview['assets'][number]>(`/assets/${link.asset_id}`)
    return { assets: [asset], folders: [], total: 1 }
  }
  const data = await api.get<FolderShareAssetsResponse>(`/share/${token}/assets?page=1&per_page=4`)
  return {assets: data.assets, folders: data.subfolders, total: data.total}
}
export function useShareScopePreview(token: string, enabled: boolean) {
  return useSWR(enabled ? ['share-scope-preview', token] : null, () => fetchShareScopePreview(token), {revalidateOnFocus:false, shouldRetryOnError:false})
}
