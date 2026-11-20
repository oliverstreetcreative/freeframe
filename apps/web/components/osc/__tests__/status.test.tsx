import { render, screen, waitFor, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { OSC_STATUSES, StatusPill, StatusFilterBar, effectiveStatus, passesStatusFilter } from '../status'
import { Badge } from '@/components/shared/badge'
import { api } from '@/lib/api'

vi.mock('@/lib/api', () => ({ api: { patch: vi.fn() } }))
afterEach(() => { cleanup(); vi.clearAllMocks() })

const expected = [
  ['in_review', 'Needs review', '#fcefd6', '#8a5a0b'],
  ['draft', 'In progress', '#efefec', '#6e6e6a'],
  ['client_review', 'Client review', '#e3eef8', '#245a7d'],
  ['rejected', 'Changes requested', '#fbe3e0', '#a33b2c'],
  ['approved', 'Approved', '#e7f3e9', '#2f6b3a'],
] as const

describe('OSC five-state asset presentation', () => {
  it('matches the Hub palette and preserves the five existing stored choices', () => {
    expect(OSC_STATUSES.map(s => [s.value, s.label, s.bg, s.fg])).toEqual(expected)
  })
  it.each(expected)('paints %s identically in both pill components', (status, label, bg, fg) => {
    render(<><StatusPill asset={{ id: status, status }} editable={false} /><Badge status={status} /></>)
    for (const pill of screen.getAllByText(label)) {
      expect(pill).toHaveStyle({ background: bg, color: fg })
      expect(pill).toHaveAttribute('data-osc-status', status)
    }
  })
  it('keeps archived grey and outside the active choices', () => {
    render(<StatusPill asset={{ id: 'old', status: 'archived' }} editable={false} />)
    expect(screen.getByText('Archived')).toHaveStyle({ background: '#efefec', color: '#6e6e6a' })
    expect(OSC_STATUSES.map(s => s.value)).not.toContain('archived')
  })
  it('saves the original enum through the existing endpoint, then restores on refusal', async () => {
    const asset = { id: 'edit-test', status: 'draft' as const }
    vi.mocked(api.patch).mockRejectedValueOnce(new Error('not allowed'))
    render(<StatusPill asset={asset} />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /Status: In progress/ }))
    await user.click(screen.getByRole('menuitem', { name: 'Approved' }))
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/assets/edit-test', { status: 'approved' }))
    await waitFor(() => expect(effectiveStatus(asset)).toBe('draft'))
    expect(screen.getByRole('button', { name: /Status: In progress/ })).toBeInTheDocument()
  })
  it('keeps status filtering and counts on saved values', async () => {
    const assets = [{ id: 'f1', status: 'in_review' as const }, { id: 'f2', status: 'approved' as const }]
    render(<StatusFilterBar assets={assets} />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /Needs review\s*1/ }))
    expect(passesStatusFilter(assets[0])).toBe(true)
    expect(passesStatusFilter(assets[1])).toBe(false)
    await user.click(screen.getByRole('button', { name: 'Clear' }))
    expect(passesStatusFilter(assets[1])).toBe(true)
  })
})
