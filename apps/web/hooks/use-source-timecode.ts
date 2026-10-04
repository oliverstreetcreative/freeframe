'use client'

import { useCallback } from 'react'
import { useReviewStore } from '@/stores/review-store'
import { formatSourceTimecode } from '@/lib/utils'

/**
 * OSC 0013: a formatter (seconds-from-0 -> "HH:MM:SS:FF") that labels frames the way the source
 * file does — frame 0 = the file's embedded start TC (e.g. 00:59:55:00). Only uses the fetched
 * start TC when it belongs to the version on screen; otherwise (unknown, loading, or another
 * version's) it counts from 0 exactly as before. Display only: stored times stay seconds-from-0.
 */
export function useSourceTimecode(): (seconds: number) => string {
  const tc = useReviewStore((s) => s.sourceTc)
  const versionId = useReviewStore((s) => s.currentVersion?.id ?? null)
  const live = tc && tc.versionId != null && tc.versionId === versionId ? tc : null
  const startFrames = live ? live.startFrames : null
  const fps = live ? live.fps : null
  return useCallback(
    (seconds: number) => formatSourceTimecode(seconds, startFrames, fps),
    [startFrames, fps],
  )
}
