'use client'
import { File } from 'lucide-react'
import { useShareScopePreview } from '@/hooks/use-share-scope-preview'
export function ShareScopePreview({token,enabled,targetName}:{token:string;enabled:boolean;targetName:string}) {
  const {data} = useShareScopePreview(token,enabled)
  if (!data) return <p className="text-sm text-text-secondary break-words [overflow-wrap:anywhere]">{targetName}</p>
  return <div className="min-w-0 space-y-2">
    <p className="text-xs text-text-tertiary">{data.total} {data.total===1?'asset':'assets'}{data.folders.length>0 ? ` · ${data.folders.length} ${data.folders.length===1?'folder':'folders'}`:''}</p>
    {data.assets.map(asset=><div key={asset.id} className="flex min-w-0 items-start gap-2">
      {asset.thumbnail_url ? <img src={asset.thumbnail_url} alt="" className="h-12 w-16 shrink-0 rounded object-cover" loading="lazy"/> : <div className="h-12 w-16 shrink-0 rounded bg-bg-tertiary flex items-center justify-center"><File className="h-5 w-5 text-text-tertiary"/></div>}
      <p className="min-w-0 text-sm text-text-secondary break-words [overflow-wrap:anywhere]">{asset.name}</p>
    </div>)}
    {data.total>data.assets.length && <p className="text-xs text-text-tertiary">{data.total-data.assets.length} more assets · open details to view</p>}
    {data.folders.map(folder=><p key={folder.id} className="text-sm text-text-secondary break-words [overflow-wrap:anywhere]">{folder.name} · {folder.item_count} {folder.item_count===1?'item':'items'}</p>)}
  </div>
}
