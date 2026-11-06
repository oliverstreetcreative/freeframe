'use client'

import * as React from 'react'
import useSWR from 'swr'
import { api, ApiError } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { sha256 } from '@noble/hashes/sha2.js'

type Token = { id: string; name: string; scopes: string[]; project_ids: string[] | null; revoked_at: string | null; last_used_at: string | null; expires_at: string | null }
type Project = { id: string; name: string }
type Property = { type?: string; title?: string; default?: unknown; enum?: string[]; anyOf?: Property[]; format?: string }
type Action = { name: string; gui: string; scope: string; inputSchema: { properties: Record<string, Property>; required?: string[] } }
type Removal = { id: string; target_type: string; target_id: string; reason: string }
type Archive = { receipt_id: string; target_type: string; target_id: string }
const scopes = ['read', 'upload', 'organize', 'notes:read', 'archive', 'remove:request']
const actionLabels: Record<string, string> = {
  list_projects: 'List projects', list_folders: 'List folders', list_assets: 'List items and versions', get_asset: 'Open item details',
  get_version: 'Check a version', find_upload: 'Find an upload', upload_version: 'Upload a version', create_project: 'Create a project',
  create_folder: 'Create a folder', rename_asset: 'Rename an item', move_asset: 'Move an item', bulk_move: 'Move selected items',
  set_version_label: 'Label a version', merge_into_stack: 'Merge version stacks', list_notes: 'Read notes', export_notes: 'Export notes',
  mark_note_addressed: 'Mark a note addressed', archive_asset: 'Archive an item', archive_folder: 'Archive a folder',
  list_archives: 'List archived items', restore_archive: 'Restore an archived item', request_removal: 'Request removal',
}
const label = (value: string) => value.replace(/_/g, ' ').replace(/\bid\b/g, 'ID')
const fetchProjects = () => api.post<Project[]>('/osc/actions/list_projects', {})

export function BotAccessTab() {
  const { data: tokens, mutate: refreshTokens } = useSWR<Token[]>('/osc/admin/bot-tokens', () => api.get<Token[]>('/osc/admin/bot-tokens'))
  const { data: projects } = useSWR<Project[]>('review-action-projects', fetchProjects)
  const { data: catalog } = useSWR<Action[]>('/osc/actions/catalog', () => api.get<Action[]>('/osc/actions/catalog'))
  const { data: removals, mutate: refreshRemovals } = useSWR<Removal[]>('/osc/admin/removals', () => api.get<Removal[]>('/osc/admin/removals'))
  const [name, setName] = React.useState('')
  const [selectedScopes, setSelectedScopes] = React.useState(['read', 'upload'])
  const [allowedProjects, setAllowedProjects] = React.useState<string[]>([])
  const [allProjects, setAllProjects] = React.useState(false)
  const [expiry, setExpiry] = React.useState('')
  const [issued, setIssued] = React.useState('')
  const [error, setError] = React.useState('')
  const [busy, setBusy] = React.useState(false)
  const [tool, setTool] = React.useState('list_projects')
  const [args, setArgs] = React.useState<Record<string, unknown>>({})
  const [file, setFile] = React.useState<File | null>(null)
  const [result, setResult] = React.useState<unknown>(null)
  const [progress, setProgress] = React.useState('')
  const [project, setProject] = React.useState('')
  const [codes, setCodes] = React.useState<Record<string, string>>({})
  const action = catalog?.find(x => x.name === tool)
  const { data: stacks } = useSWR<{asset: {id: string; name: string}; versions: {id: string; version_number: number}[]}[]>(project ? ['review-action-assets', project] : null,
    () => api.post('/osc/actions/list_assets', {project_id: project}))
  const { data: folders } = useSWR<{id: string; name: string}[]>(project ? ['review-action-folders', project] : null,
    () => api.post('/osc/actions/list_folders', {project_id: project}))
  const { data: archives, mutate: refreshArchives } = useSWR<Archive[]>(project ? ['review-action-archives', project] : null,
    () => api.post('/osc/actions/list_archives', {project_id: project}))

  async function perform(work: () => Promise<void>) {
    setBusy(true); setError('')
    try { await work() } catch (e) { setError(e instanceof Error ? e.message : 'The action failed') }
    finally { setBusy(false) }
  }
  async function call<T>(name: string, arguments_: unknown): Promise<T> {
    for (let attempt=0; ; attempt++) {
      try { return await api.post<T>('/osc/actions/' + name, arguments_) }
      catch (error) {
        if (!(error instanceof ApiError) || error.status !== 429 || attempt >= 3) throw error
        setProgress('Waiting for the request limit to reset…')
        await new Promise(resolve=>setTimeout(resolve,60000))
      }
    }
  }
  function values() {
    const out: Record<string, unknown> = {}
    for (const [key, property] of Object.entries(action?.inputSchema.properties || {})) {
      if (args[key] !== undefined && args[key] !== '') out[key] = args[key]
      else if (property.default !== undefined) out[key] = property.default
      else if (key === 'project_id') out[key] = project
    }
    return out
  }
  async function upload(arguments_: Record<string, unknown>) {
    if (!file) throw new Error('Choose the media file to upload')
    setProgress('Checking the file…')
    const checksum = sha256.create()
    for (let offset=0; offset<file.size; offset+=1024*1024) checksum.update(new Uint8Array(await file.slice(offset,offset+1024*1024).arrayBuffer()))
    const hash = Array.from(checksum.digest()).map(x => x.toString(16).padStart(2, '0')).join('')
    type Plan = { s3_key: string; upload_id: string; asset_id: string; version_id: string; chunk_size_bytes: number; part_count: number }
    const plan = await call<Plan>('upload_version', {...arguments_, filename: file.name, sha256: hash, file_size_bytes: file.size, mime_type: file.type || (file.name.toLowerCase().endsWith('.mov') ? 'video/quicktime' : 'video/mp4')})
    // Keep the version reference visible even if the connection is interrupted.
    setResult({asset_id: plan.asset_id, version_id: plan.version_id, status: 'uploading'})
    const parts = []
    for (let part = 1; part <= plan.part_count; part++) {
      setProgress(`Uploading part ${part} of ${plan.part_count}…`)
      const signed = await call<{presigned_url: string}>('presign_part', {s3_key: plan.s3_key, upload_id: plan.upload_id, part_number: part})
      const response = await fetch(signed.presigned_url, {method: 'PUT', body: file.slice((part-1)*plan.chunk_size_bytes, part*plan.chunk_size_bytes)})
      const etag = response.headers.get('etag')
      if (!response.ok || !etag) throw new Error('The storage transfer failed. Keep the version reference before retrying.')
      parts.push({PartNumber: part, ETag: etag})
    }
    setProgress('Verifying the upload…')
    await call('complete_upload', {s3_key:plan.s3_key,upload_id:plan.upload_id,asset_id:plan.asset_id,version_id:plan.version_id,parts})
    setProgress('Processing…')
    for (let attempt=0; attempt<900; attempt++) {
      const version = await call<{ready: boolean; item_url: string; version: {processing_status: string}}>('get_version', {version_id: plan.version_id})
      if (version.ready) { setResult({item_url: version.item_url, version_id: plan.version_id, status: 'ready'}); setProgress('Ready'); return }
      if (version.version.processing_status === 'failed') throw new Error('Review could not process this version')
      await new Promise(resolve => setTimeout(resolve, 2000))
    }
    setProgress('Still processing. Use Check a version with the saved version reference.')
  }
  function field(key: string, property: Property) {
    const definition = property.anyOf?.find(x => x.type !== 'null') || property
    const current = args[key] ?? property.default ?? ''
    const options = property.enum || definition.enum
    const set = (value: unknown) => setArgs(a => ({...a, [key]: value}))
    const required = action?.inputSchema.required?.includes(key)
    const select = (items: {id: string; name: string}[], empty = 'Choose…') => <select id={'action-'+key} className="w-full rounded border border-border bg-bg-primary p-2" value={String(current)} onChange={e => set(e.target.value || null)} required={required}><option value="">{empty}</option>{items.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select>
    if (key === 'project_id') return <select id="action-project_id" value={project} onChange={e=>setProject(e.target.value)} required className="w-full rounded border border-border bg-bg-primary p-2"><option value="">Choose a project…</option>{projects?.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select>
    if (key === 'asset_id' || key === 'target_asset_id') return select(stacks?.map(x=>({id:x.asset.id,name:x.asset.name})) || [])
    if (key === 'version_id') return select(stacks?.flatMap(x=>x.versions.map(v=>({id:v.id,name:`${x.asset.name} · version ${v.version_number}`}))) || [])
    if (['folder_id','parent_id','target_folder_id'].includes(key)) return select(folders || [], 'Project root')
    if (definition.type === 'boolean') return <input id={'action-'+key} type="checkbox" checked={Boolean(current)} onChange={e=>set(e.target.checked)} />
    if (options) return <select id={'action-'+key} value={String(current)} onChange={e=>set(e.target.value)} className="w-full rounded border border-border bg-bg-primary p-2"><option value="">Choose…</option>{options.map(x=><option key={x}>{x}</option>)}</select>
    if (definition.type === 'array') return <textarea id={'action-'+key} className="w-full rounded border border-border bg-bg-primary p-2" aria-label={label(key)} placeholder="One ID per line" value={Array.isArray(current) ? current.join('\n') : ''} onChange={e=>set(e.target.value.split(/[\n,]/).map(x=>x.trim()).filter(Boolean))} />
    return <Input id={'action-'+key} value={String(current)} required={required} type={definition.type==='integer'?'number':'text'} onChange={e=>set(definition.type==='integer'?Number(e.target.value):e.target.value)} />
  }

  return <div className="space-y-8 text-text-primary">
    {error && <p role="alert" className="text-red-500">{error}</p>}
    <section className="space-y-3"><h2 className="text-lg font-semibold">Bot access</h2><p className="text-sm text-text-secondary">Each bot uses its own key. Choose its actions and projects. Keys cannot create client links or reply to notes.</p>
      <form className="space-y-3 max-w-xl" onSubmit={e=>{e.preventDefault();void perform(async()=>{setIssued('');const value=await api.post<{token:string}>('/osc/admin/bot-tokens',{name,scopes:selectedScopes,project_ids:allProjects?null:allowedProjects,expires_at:expiry?new Date(expiry).toISOString():null});setIssued(value.token);await refreshTokens()})}}>
        <label className="block">Bot name<Input value={name} onChange={e=>setName(e.target.value)} required maxLength={120} /></label>
        <fieldset><legend>Allowed actions</legend><div className="flex flex-wrap gap-3">{scopes.map(scope=><label key={scope}><input type="checkbox" checked={selectedScopes.includes(scope)} onChange={e=>setSelectedScopes(s=>e.target.checked?[...s,scope]:s.filter(x=>x!==scope))} /> {scope}</label>)}</div></fieldset>
        <fieldset><legend>Allowed projects</legend><label className="block"><input type="checkbox" checked={allProjects} onChange={e=>setAllProjects(e.target.checked)} /> All projects, including future ones</label>{!allProjects&&projects?.map(p=><label className="block" key={p.id}><input type="checkbox" checked={allowedProjects.includes(p.id)} onChange={e=>setAllowedProjects(s=>e.target.checked?[...s,p.id]:s.filter(x=>x!==p.id))} /> {p.name}</label>)}</fieldset>
        <label className="block">Expires (optional)<Input type="datetime-local" value={expiry} onChange={e=>setExpiry(e.target.value)} /></label>
        <Button disabled={busy || !selectedScopes.length || (!allProjects&&!allowedProjects.length)}>Create key</Button>
      </form>
      {issued&&<div role="status" className="rounded border border-border p-3"><p>Copy this key now. It is shown only once.</p><code className="break-all select-all">{issued}</code><Button variant="ghost" onClick={()=>setIssued('')}>Hide key</Button></div>}
      <ul className="space-y-2">{tokens?.map(t=><li className="rounded border border-border p-3" key={t.id}><strong>{t.name}</strong> · {t.scopes.join(', ')} · {t.revoked_at?'Revoked':t.last_used_at?'Last used '+new Date(t.last_used_at).toLocaleString():'Unused'}{!t.revoked_at&&<Button variant="ghost" disabled={busy} onClick={()=>void perform(async()=>{await api.post(`/osc/admin/bot-tokens/${t.id}/revoke`,{});setIssued('');await refreshTokens()})}>Revoke</Button>}</li>)}</ul>
    </section>
    <section className="space-y-3 max-w-2xl"><h2 className="text-lg font-semibold">Review actions</h2><p className="text-sm text-text-secondary">These actions use the same checks as bot access. Enabled client links prevent changes to their items.</p>
      <label className="block">Project<select className="block w-full rounded border border-border bg-bg-primary p-2" value={project} onChange={e=>{setProject(e.target.value);setArgs({})}}><option value="">Choose a project…</option>{projects?.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      <label className="block">Action<select className="block w-full rounded border border-border bg-bg-primary p-2" value={tool} onChange={e=>{setTool(e.target.value);setArgs({});setResult(null)}}>{catalog?.filter(x=>!['presign_part','complete_upload'].includes(x.name)).map(x=><option key={x.name} value={x.name}>{actionLabels[x.name] || x.gui}</option>)}</select></label>
      <form className="space-y-3" onSubmit={e=>{e.preventDefault();void perform(async()=>{if(tool==='upload_version')await upload(values());else setResult(await call(tool,values()));await refreshRemovals();await refreshArchives()})}}>
        {Object.entries(action?.inputSchema.properties||{}).filter(([key])=>!(tool==='upload_version'&&['filename','sha256','file_size_bytes','mime_type'].includes(key))).map(([key,p])=><label className="block" htmlFor={'action-'+key} key={key}>{label(key)}{field(key,p)}</label>)}
        {tool==='upload_version'&&<label className="block">Media file<input className="block" type="file" required onChange={e=>setFile(e.target.files?.[0] || null)} /></label>}
        <Button disabled={busy}>Run action</Button>
      </form>
      {progress&&<p role="status">{progress}</p>}{result!==null&&<pre className="overflow-auto whitespace-pre-wrap rounded border border-border p-3 text-sm">{JSON.stringify(result,null,2)}</pre>}
      {!!archives?.length&&<div><h3 className="font-semibold">Archived items</h3>{archives.map(x=><p key={x.receipt_id}>{x.target_type} {x.target_id} <Button variant="ghost" disabled={busy} onClick={()=>void perform(async()=>{await call('restore_archive',{receipt_id:x.receipt_id});await refreshArchives()})}>Restore</Button></p>)}</div>}
    </section>
    <section className="space-y-3"><h2 className="text-lg font-semibold">Pending removals</h2><p className="text-sm text-text-secondary">A bot can request removal. Only your signed-in administrator session can confirm. Items go to Trash for the normal retention period.</p>
      {!removals?.length&&<p>No pending requests.</p>}{removals?.map(x=><div key={x.id} className="rounded border border-border p-3"><p>{x.target_type} {x.target_id}</p><p>{x.reason}</p>{!codes[x.id]?<Button variant="ghost" disabled={busy} onClick={()=>void perform(async()=>{const code=await api.post<{code:string}>(`/osc/admin/removals/${x.id}/code`,{});setCodes(s=>({...s,[x.id]:code.code}))})}>Review removal</Button>:<div><p>This confirmation expires in 15 minutes. Move this item to Trash?</p><Button disabled={busy} onClick={()=>void perform(async()=>{await api.post(`/osc/admin/removals/${x.id}/confirm`,{code:codes[x.id]});setCodes(s=>{const next={...s};delete next[x.id];return next});await refreshRemovals()})}>Confirm move to Trash</Button><Button variant="ghost" onClick={()=>setCodes(s=>{const next={...s};delete next[x.id];return next})}>Cancel</Button></div>}</div>)}
    </section>
  </div>
}
