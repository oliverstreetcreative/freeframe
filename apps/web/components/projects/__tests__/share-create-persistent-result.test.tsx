import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { ShareCreateDialog } from '../share-create-dialog'
const mocks = vi.hoisted(() => ({post: vi.fn(), patch: vi.fn(), get: vi.fn(), meta: vi.fn(), copy: vi.fn()}))
vi.mock('@/lib/api', () => ({api: {post:mocks.post, patch:mocks.patch, get:mocks.get}}))
vi.mock('@/hooks/use-share-meta', () => ({KIND_HINT:{review:'Review',delivery:'Delivery'}, KIND_LABEL:{review:'Review',delivery:'Delivery'},putShareMeta:mocks.meta,refreshShareMeta:vi.fn()}))
vi.mock('@/lib/utils', async (load) => ({...await load<typeof import('@/lib/utils')>(), copyToClipboard:mocks.copy}))
beforeEach(() => {
 vi.clearAllMocks()
 mocks.post.mockResolvedValue({id:'fixture-id',token:'SYNTHETIC',title:'Synthetic share',asset_id:'a',folder_id:null,project_id:'p'})
 mocks.patch.mockResolvedValue({})
 mocks.get.mockResolvedValue({permission:'comment',allow_download:false,appearance:null})
 mocks.meta.mockResolvedValue({ok:true})
 mocks.copy.mockResolvedValue(false)
})
afterEach(cleanup)
async function create(count:number) {
 const close=vi.fn()
 const assets = Array.from({length:Math.max(1,count)},(_,i)=>({id:String(i),name:'Fixture '+i,asset_type:'video'}))
 render(<ShareCreateDialog open onOpenChange={close} projectId="p" currentFolderId={null} assets={assets as never} folders={[]} preselectedItems={count ? assets.slice(0,count).map(a=>({type:'asset',id:a.id,name:a.name})) : []} onShareCreated={vi.fn()} />)
 if (screen.queryByRole('button',{name:/^Next$/})) fireEvent.click(screen.getByRole('button',{name:/^Next$/}))
 fireEvent.click(await screen.findByRole('button',{name:/^Create$/}))
 return close
}
it.each([0,1,2])('retains URL and Copy until Done for %i selections',async(count)=>{
 const close=await create(count)
 const url=await screen.findByRole('textbox',{name:'Share URL'})
 expect(url).toHaveValue('http://localhost:3000/share/SYNTHETIC')
 expect(screen.getByRole('button',{name:'Copy Link'})).toBeVisible()
 expect(close).not.toHaveBeenCalled()
 fireEvent.click(screen.getByRole('button',{name:/^Done$/}))
 expect(close).toHaveBeenCalledWith(false)
 expect(mocks.post).toHaveBeenCalledTimes(1)
})
it('keeps the existing result after resolving metadata guard without duplicating creation',async()=>{
 mocks.meta.mockResolvedValueOnce({ok:false,status:409,detail:'Slate',slated:['fixture']}).mockResolvedValueOnce({ok:true})
 const close=await create(1)
 fireEvent.click(await screen.findByRole('button',{name:'Make it a review link'}))
 expect(await screen.findByRole('textbox',{name:'Share URL'})).toBeVisible()
 expect(close).not.toHaveBeenCalled()
 expect(mocks.post).toHaveBeenCalledTimes(1)
})
it('offers a selectable URL when copying fails',async()=>{
 await create(1)
 fireEvent.click(await screen.findByRole('button',{name:'Copy share URL'}))
 expect(await screen.findByText('Copy failed. Select the URL and copy it manually.')).toBeVisible()
 expect(screen.getByRole('textbox',{name:'Share URL'})).toHaveAttribute('readonly')
})
