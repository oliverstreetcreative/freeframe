import { describe, it, expect } from 'vitest'
import { formatSourceTimecode, formatTimecode } from '../utils'

// OSC 0013: the player shows the clip's real source timecode (frame 0 = the file's embedded
// start TC), not 00:00:00:00.
describe('formatSourceTimecode', () => {
  it('falls back to count-from-zero when the start TC is unknown', () => {
    expect(formatSourceTimecode(1.5, null, null)).toBe(formatTimecode(1.5, 24))
    expect(formatSourceTimecode(1.5, undefined, 25)).toBe('00:00:01:12')
  })

  it('starts a slated 24 fps render at 00:59:55:00 and hits program at 01:00:00:00', () => {
    expect(formatSourceTimecode(0, 86280, 24)).toBe('00:59:55:00')
    expect(formatSourceTimecode(5, 86280, 24)).toBe('01:00:00:00')
    expect(formatSourceTimecode(6.5, 86280, 24)).toBe('01:00:01:12')
  })

  it('counts real frames at 23.976 against a 24 fps label base', () => {
    expect(formatSourceTimecode(120 / 23.976, 86280, 23.976)).toBe('01:00:00:00')
    expect(formatSourceTimecode(121 / 23.976, 86280, 23.976)).toBe('01:00:00:01')
  })

  it('matches the export math at 25 fps (2.52 s = frame 63)', () => {
    expect(formatSourceTimecode(2.52, 90000, 25)).toBe('01:00:02:13')
  })

  it('a slateless master starts at its own TC', () => {
    expect(formatSourceTimecode(0, 108000, 30)).toBe('01:00:00:00')
  })
})
