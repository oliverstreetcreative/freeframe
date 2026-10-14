import { render,screen,fireEvent,cleanup } from '@testing-library/react'
import { beforeEach,afterEach,expect,it,vi } from 'vitest'
import { ShareLinksTable } from '../share-links-table'
const copy=vi.hoisted(()=>vi.fn())
vi.mock('@/hooks/use-share-meta',()=>({useShareMeta:()=>({shareMeta:{}})}))
vi.mock('@/lib/utils',async(load)=>({...await load<typeof import('@/lib/utils')>(),copyToClipboard:copy}))
beforeEach(()=>copy.mockReset())
afterEach(cleanup)
function show(){render(<ShareLinksTable projectId="p" shareLinks={[{id:'i',token:'SYNTHETIC',title:'Fixture',is_enabled:true,permission:'view',view_count:0} as never]} onSelectLink={vi.fn()} onToggleEnabled={vi.fn()} onViewActivity={vi.fn()} frontendUrl="https://fixture.invalid" />)}
it('uses fallback helper and confirms only successful copies',async()=>{copy.mockResolvedValue(true);show();fireEvent.click(screen.getByTitle('Copy link'));expect(copy).toHaveBeenCalledWith('https://fixture.invalid/share/SYNTHETIC');expect(await screen.findByTitle('Copy link')).toBeVisible()})
it('keeps the URL and manual-copy instruction visible on copy failure',async()=>{copy.mockResolvedValue(false);show();fireEvent.click(screen.getByTitle('Copy link'));expect(await screen.findByRole('status')).toHaveTextContent('Copy failed');expect(screen.getByText('https://fixture.invalid/share/SYNTHETIC')).toHaveClass('select-text')})
