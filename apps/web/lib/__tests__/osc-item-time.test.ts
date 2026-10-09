import { describe, it, expect } from 'vitest'
import { itemTime } from '../utils'

// OSC 0023 (Sam 10/8 22:50): an item shows and sorts by its LATEST version's upload, not its first.
describe('itemTime', () => {
  it("uses the latest version's upload time on the dashboard", () => {
    expect(itemTime({ created_at: '2026-10-04T19:10:00Z', latest_version: { created_at: '2026-10-08T22:56:00Z' } }))
      .toBe('2026-10-08T22:56:00Z')
  })
  it('uses latest_version_at on share-link folder pages', () => {
    expect(itemTime({ created_at: '2026-10-04T19:10:00Z', latest_version_at: '2026-10-09T02:07:00Z' }))
      .toBe('2026-10-09T02:07:00Z')
  })
  it('falls back to the item time when no version time is known', () => {
    expect(itemTime({ created_at: '2026-10-04T19:10:00Z', latest_version: null })).toBe('2026-10-04T19:10:00Z')
  })
  it('sorts a stack updated tonight above one made later but not updated since', () => {
    const old = { created_at: '2026-10-04T00:00:00Z', latest_version: { created_at: '2026-10-08T23:00:00Z' } }
    const newer = { created_at: '2026-10-06T00:00:00Z', latest_version: { created_at: '2026-10-06T00:00:00Z' } }
    const sorted = [newer, old].sort((a, b) => new Date(itemTime(b)).getTime() - new Date(itemTime(a)).getTime())
    expect(sorted[0]).toBe(old)
  })
})
