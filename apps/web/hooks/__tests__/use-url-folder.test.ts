import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'

// OSC 0021: the breadcrumb changes ?folder= on the same page; the page must follow it.
let params = new URLSearchParams('folder=child')
vi.mock('next/navigation', () => ({ useSearchParams: () => params }))

import { useUrlFolder } from '../use-url-folder'

describe('useUrlFolder', () => {
  beforeEach(() => {
    params = new URLSearchParams('folder=child')
  })

  it('does not fire on mount (the page already starts from the URL)', () => {
    const onChange = vi.fn()
    const { result } = renderHook(() => useUrlFolder(onChange))
    expect(result.current).toBe('child')
    expect(onChange).not.toHaveBeenCalled()
  })

  it('fires with the parent when a breadcrumb points at the parent folder', () => {
    const onChange = vi.fn()
    const { rerender } = renderHook(() => useUrlFolder(onChange))
    params = new URLSearchParams('folder=parent')
    rerender()
    expect(onChange).toHaveBeenCalledWith('parent')
  })

  it('fires with null when the project crumb drops ?folder= (back to the root)', () => {
    const onChange = vi.fn()
    const { rerender } = renderHook(() => useUrlFolder(onChange))
    params = new URLSearchParams('')
    rerender()
    expect(onChange).toHaveBeenCalledWith(null)
  })

  it('does not fire again when the URL is unchanged', () => {
    const onChange = vi.fn()
    const { rerender } = renderHook(() => useUrlFolder(onChange))
    rerender()
    rerender()
    expect(onChange).not.toHaveBeenCalled()
  })
})
