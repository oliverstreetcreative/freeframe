import * as React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SWRConfig } from 'swr'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { BotAccessTab } from '../settings/bot-access-tab'

const { get, post } = vi.hoisted(()=>({get:vi.fn(),post:vi.fn()}))
vi.mock('@/lib/api',()=>({api:{get,post}}))
function show() { return render(<SWRConfig value={{provider:()=>new Map(),dedupingInterval:0}}><BotAccessTab /></SWRConfig>) }
beforeEach(()=>{
  vi.clearAllMocks()
  get.mockImplementation(async(path:string)=>{
    if(path==='/osc/admin/bot-tokens')return [{id:'key1',name:'Fixture bot',scopes:['read'],project_ids:['project1'],revoked_at:null,last_used_at:null,expires_at:null}]
    if(path==='/osc/admin/removals')return [{id:'removal1',target_type:'asset',target_id:'item1',reason:'Fixture removal'}]
    if(path==='/osc/actions/catalog')return [{name:'list_projects',scope:'read',gui:'Projects',inputSchema:{properties:{},required:[]}}]
    return []
  })
  post.mockImplementation(async(path:string)=>{
    if(path==='/osc/actions/list_projects')return [{id:'project1',name:'Fixture project'}]
    if(path==='/osc/admin/bot-tokens')return {token:'ffb_fixture_only_shown_once'}
    if(path.endsWith('/code'))return {code:'fixture-confirmation'}
    if(path==='/osc/actions/list_archives')return [{receipt_id:'receipt1',target_type:'asset',target_id:'item1'}]
    return []
  })
})

describe('Bot access admin',()=>{
  it('issues a scoped project key once and hides it on revoke',async()=>{
    const user=userEvent.setup();show()
    await user.type(screen.getByLabelText('Bot name'),'Uploader')
    await user.click(await screen.findByLabelText('Fixture project'))
    await user.click(screen.getByRole('button',{name:'Create key'}))
    expect(await screen.findByText('ffb_fixture_only_shown_once')).toBeVisible()
    expect(post).toHaveBeenCalledWith('/osc/admin/bot-tokens',{name:'Uploader',scopes:['read','upload'],project_ids:['project1'],expires_at:null})
    await user.click(screen.getByRole('button',{name:'Revoke'}))
    await waitFor(()=>expect(screen.queryByText('ffb_fixture_only_shown_once')).not.toBeInTheDocument())
    expect(post).toHaveBeenCalledWith('/osc/admin/bot-tokens/key1/revoke',{})
    expect(screen.queryByLabelText('share')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('notes:write')).not.toBeInTheDocument()
  })
  it('requires two deliberate human actions before confirming removal',async()=>{
    const user=userEvent.setup();show()
    await user.click(await screen.findByRole('button',{name:'Review removal'}))
    expect(post).toHaveBeenCalledWith('/osc/admin/removals/removal1/code',{})
    expect(post.mock.calls.some(([p])=>p.endsWith('/confirm'))).toBe(false)
    await user.click(await screen.findByRole('button',{name:'Confirm move to Trash'}))
    expect(post).toHaveBeenCalledWith('/osc/admin/removals/removal1/confirm',{code:'fixture-confirmation'})
    expect(screen.queryByText('fixture-confirmation')).not.toBeInTheDocument()
  })
  it('offers archive undo through the same action endpoint',async()=>{
    const user=userEvent.setup();show()
    await screen.findByRole('option',{name:'Fixture project'})
    await user.selectOptions(screen.getByLabelText('Project'),'project1')
    await user.click(await screen.findByRole('button',{name:'Restore'}))
    expect(post).toHaveBeenCalledWith('/osc/actions/restore_archive',{receipt_id:'receipt1'})
  })
})
