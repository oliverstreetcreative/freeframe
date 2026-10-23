import{beforeEach,expect,it,vi}from'vitest'
import{fetchShareScopePreview}from'../use-share-scope-preview'
const get=vi.hoisted(()=>vi.fn())
vi.mock('@/lib/api',()=>({api:{get}}))
beforeEach(()=>get.mockReset())
it('identifies a single asset from authenticated details without guessing its ID',async()=>{
 get.mockResolvedValueOnce({asset_id:'actual-id'}).mockResolvedValueOnce({id:'actual-id',name:'Square captions',asset_type:'video',thumbnail_url:'thumb'})
 expect(await fetchShareScopePreview('known')).toEqual({assets:[{id:'actual-id',name:'Square captions',asset_type:'video',thumbnail_url:'thumb'}],folders:[],total:1})
 expect(get.mock.calls.map(c=>c[0])).toEqual(['/share/known/details','/assets/actual-id'])
})
it('uses the existing scoped listing and preserves the real group total',async()=>{
 get.mockResolvedValueOnce({asset_id:null,project_id:'p'}).mockResolvedValueOnce({assets:[{id:'a',name:'Square'}],subfolders:[{id:'f',name:'Deliverables',item_count:3}],total:9})
 const result=await fetchShareScopePreview('known');expect(result.total).toBe(9);expect(result.assets[0].name).toBe('Square');expect(get).toHaveBeenLastCalledWith('/share/known/assets?page=1&per_page=4')
})
