import{render,screen,fireEvent,cleanup}from'@testing-library/react'
import{afterEach,it,expect,vi}from'vitest'
import{AssetGrid}from'../asset-grid'
import{Button}from'@/components/ui/button'
vi.mock('@/stores/view-store',()=>({useViewStore:()=>({layout:'grid',cardSize:'M',aspectRatio:'landscape',showCardInfo:true,sortKey:'custom',sortDirection:'asc'})}))
vi.mock('../asset-card',()=>({AssetCard:({onSelect}:any)=><button onClick={onSelect}>Select fixture asset</button>}))
afterEach(cleanup)
it('keeps all project actions available and dispatches the original actions',()=>{
 const members=vi.fn(),share=vi.fn(),folder=vi.fn(),upload=vi.fn()
 render(<AssetGrid projectId="p" assets={[]} actions={<><Button onClick={members}>Manage members</Button><Button onClick={share}>Share</Button><Button onClick={folder}>New Folder</Button><Button onClick={upload}>Upload</Button></>}/>)
 for(const name of ['Manage members','Share','New Folder','Upload'])fireEvent.click(screen.getByRole('button',{name}))
 expect(members).toHaveBeenCalledOnce();expect(share).toHaveBeenCalledOnce();expect(folder).toHaveBeenCalledOnce();expect(upload).toHaveBeenCalledOnce()
 expect(screen.getByRole('button',{name:'Appearance'})).toBeVisible();expect(screen.getByRole('button',{name:/Sorted by\s*Custom/})).toBeVisible()
})
it('keeps the share-selection cancel and create actions usable',()=>{
 const cancel=vi.fn();render(<AssetGrid projectId="p" assets={[]} shareMode onShareModeChange={cancel}/>);fireEvent.click(screen.getByRole('button',{name:'Cancel'}));expect(cancel).toHaveBeenCalledWith(false);expect(screen.getByRole('button',{name:'Create Share Link'})).toBeDisabled()
})

it('keeps bulk share and download callbacks intact after selection',()=>{const share=vi.fn(),download=vi.fn();render(<AssetGrid projectId="p" assets={[{id:'a',name:'Fixture',asset_type:'video',status:'in_review'} as never]} onCreateShareLink={share} onBulkDownload={download}/>);fireEvent.click(screen.getByRole('button',{name:'Select fixture asset'}));fireEvent.click(screen.getByRole('button',{name:'Download'}));expect(download).toHaveBeenCalledWith(['a'],[]);fireEvent.click(screen.getByRole('button',{name:'Share'}));expect(share).toHaveBeenCalledWith(['a'],[]);expect(screen.queryByRole('button',{name:'Delete'})).toBeNull()})
