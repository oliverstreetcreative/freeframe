'use client'

/**
 * OSC 0021: follow `?folder=` in the project URL.
 *
 * The project page read `?folder=` once, as the initial value of its folder state. The header breadcrumb
 * links to `/projects/{id}?folder={parent}` (and the project crumb to `/projects/{id}`), which is the same
 * page, so Next keeps it mounted and the folder state never changed: clicking a parent folder in the
 * breadcrumb did nothing (Sam 10/8: "When you try to click back the tree in the top left to a parent
 * folder, it doesn't work"). Browser Back had the same problem.
 *
 * Calls `onChange(folderId | null)` whenever the URL's folder changes after the first render. The page's
 * own in-page navigation writes the URL with history.replaceState, which Next (14.1+) mirrors into
 * useSearchParams; that echo arrives here too, so `onChange` must be idempotent (setting the same id
 * again is a no-op).
 */
import * as React from 'react'
import { useSearchParams } from 'next/navigation'

export function useUrlFolder(onChange: (folderId: string | null) => void): string | null {
  const searchParams = useSearchParams()
  const folder = searchParams?.get('folder') || null
  const first = React.useRef(true)
  const cb = React.useRef(onChange)
  cb.current = onChange
  React.useEffect(() => {
    if (first.current) {
      first.current = false
      return
    }
    cb.current(folder)
  }, [folder])
  return folder
}
