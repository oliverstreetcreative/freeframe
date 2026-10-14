import {render,screen,fireEvent,cleanup,act} from '@testing-library/react'
import {beforeEach,afterEach,expect,it,vi} from 'vitest'
import {ShareLinksTable} from '../share-links-table'
import {setViewportWidth} from '@/test/setup'
const mocks=vi.hoisted(()=>({copy:vi.fn(),select:vi.fn(),activity:vi.fn(),toggle:vi.fn()}))
vi.mock('@/hooks/use-share-meta',()=>({KIND_LABEL:{review:'Review',delivery:'Delivery'},useShareMeta:()=>({shareMeta:{i:{kind:'review',internal_label:'Square review for client'}}})}))
vi.mock('@/hooks/use-share-scope-preview',()=>({useShareScopePreview:()=>({data:{total:9,folders:[],assets:[{id:'a',name:'Mike Harmon — SQUARE 1x1 no captions',asset_type:'video',thumbnail_url:'https://fixture.invalid/thumbnail.png'}]}})}))
vi.mock('@/lib/utils',async(load)=>({...await load<typeof import('@/lib/utils')>(),copyToClipboard:mocks.copy}))
const link={id:'i',token:'SYNTHETIC',title:'Public square review',description:'Longer explanatory text.',target_name:'Mike Harmon — SQUARE 1x1 no captions',is_enabled:true,share_type:'asset',permission:'comment',view_count:4,last_viewed_at:null} as const
beforeEach(()=>{vi.clearAllMocks();mocks.copy.mockResolvedValue(true)})
afterEach(cleanup)
function show(){render(<ShareLinksTable projectId="p" shareLinks={[link as never]} frontendUrl="https://fixture.invalid" onSelectLink={mocks.select} onViewActivity={mocks.activity} onToggleEnabled={mocks.toggle}/>)}
it.each([320,390,430])('renders usable mobile cards with names, counts and controls at %ipx',width=>{
 act(()=>setViewportWidth(width));show();expect(screen.queryByRole('table')).toBeNull();expect(screen.getByRole('article')).toBeVisible();expect(screen.getByText('9 assets')).toBeVisible();expect(screen.getByText('Mike Harmon — SQUARE 1x1 no captions')).toBeVisible();expect(screen.getByText('8 more assets · open details to view')).toBeVisible();expect(screen.getByRole('textbox',{name:/Share URL/})).toHaveValue('https://fixture.invalid/share/SYNTHETIC');fireEvent.click(screen.getByRole('button',{name:/Square review for client/}));expect(mocks.select).toHaveBeenCalledWith('SYNTHETIC');fireEvent.click(screen.getByRole('button',{name:'View activity'}));expect(mocks.activity).toHaveBeenCalledWith('SYNTHETIC')
})
it('copies the real token from a mobile entry',async()=>{act(()=>setViewportWidth(390));show();fireEvent.click(screen.getByTitle('Copy link'));expect(mocks.copy).toHaveBeenCalledWith('https://fixture.invalid/share/SYNTHETIC');expect(await screen.findByText('Copied!')).toBeVisible()})
it('keeps the desktop table at wider widths',()=>{act(()=>setViewportWidth(1024));show();expect(screen.getByRole('table')).toBeVisible();expect(screen.queryByRole('article')).toBeNull()})
it('searches the actual asset name as well as share labels',()=>{act(()=>setViewportWidth(390));show();fireEvent.change(screen.getByPlaceholderText('Search for Shares'),{target:{value:'no captions'}});expect(screen.getByRole('article')).toBeVisible()})

it.each([390,1024])('labels the existing internal name, client title and description at %ipx',width=>{act(()=>setViewportWidth(width));show();expect(screen.queryByText(/Client sees:/)).toBeNull();expect(screen.getByText('Title: Public square review')).toBeVisible();expect(screen.getByText('Description: Longer explanatory text.')).toBeVisible();if(width<768)expect(screen.getByText('Name: Square review for client')).toBeVisible();else expect(screen.getByRole('columnheader',{name:'Name'})).toBeVisible()})
