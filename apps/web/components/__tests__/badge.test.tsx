import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Badge } from '../shared/badge'
import type { AssetStatus } from '@/types'

describe('Badge component', () => {
  const statuses: AssetStatus[] = ['draft', 'in_review', 'approved', 'rejected', 'archived']

  it.each(statuses)('renders %s status badge', (status) => {
    render(<Badge status={status} />)
    const badge = screen.getByText(/In progress|Needs review|Approved|Changes requested|Archived/)
    expect(badge).toBeInTheDocument()
  })

  it('renders "In progress" label for draft status', () => {
    render(<Badge status="draft" />)
    expect(screen.getByText('In progress')).toBeInTheDocument()
  })

  it('renders "Needs review" label for in_review status', () => {
    render(<Badge status="in_review" />)
    expect(screen.getByText('Needs review')).toBeInTheDocument()
  })

  it('renders "Approved" label for approved status', () => {
    render(<Badge status="approved" />)
    expect(screen.getByText('Approved')).toBeInTheDocument()
  })

  it('renders "Changes requested" label for rejected status', () => {
    render(<Badge status="rejected" />)
    expect(screen.getByText('Changes requested')).toBeInTheDocument()
  })

  it('renders "Archived" label for archived status', () => {
    render(<Badge status="archived" />)
    expect(screen.getByText('Archived')).toBeInTheDocument()
  })

  it('applies custom className', () => {
    render(<Badge status="draft" className="my-custom-class" />)
    const badge = screen.getByText('In progress')
    expect(badge.className).toContain('my-custom-class')
  })
})
