import { useLayoutEffect, useState, type RefObject } from 'react'

interface Rect {
  top: number
  bottom: number
  left: number
  right: number
}
interface Pos {
  top: number
  left: number
}

/** T27 fix, split out of `RawTranscript.tsx` under T30e's line budget: tracks the selection's
 * on-screen bounds (start/end word rects, in viewport coordinates) so the passage toolbar can
 * float next to it, as `.transcript-selection-tools` (position: fixed) was always meant to --
 * T25 pinned it `position: static` at the bottom of the reading pane "for click reliability",
 * which made it invisible without scrolling past the whole transcript. Fixed positioning is
 * already out of document flow, so it never reflows sibling words and needs no reserved
 * spacer slot. Second pass: places the toolbar below the selection (flipping above if there's
 * no room), clamped to the viewport, using the toolbar's own measured size once mounted. */
export function useToolbarPosition(
  textRef: RefObject<HTMLDivElement | null>,
  toolbarRef: RefObject<HTMLDivElement | null>,
  range: { startWordId: string; endWordId: string } | null,
  selectedText: unknown,
): Pos | null {
  const [anchorRect, setAnchorRect] = useState<Rect | null>(null)
  const [toolbarPos, setToolbarPos] = useState<Pos | null>(null)

  useLayoutEffect(() => {
    if (!range || !selectedText) {
      setAnchorRect(null)
      return
    }
    const container = textRef.current
    if (!container) return
    const measure = () => {
      const startEl = container.querySelector(`[data-word-id="${range.startWordId}"]`)
      const endEl = container.querySelector(`[data-word-id="${range.endWordId}"]`)
      if (!startEl || !endEl) return
      const s = startEl.getBoundingClientRect()
      const e = endEl.getBoundingClientRect()
      setAnchorRect({ top: Math.min(s.top, e.top), bottom: Math.max(s.bottom, e.bottom), left: Math.min(s.left, e.left), right: Math.max(s.right, e.right) })
    }
    measure()
    window.addEventListener('resize', measure)
    container.addEventListener('scroll', measure)
    return () => {
      window.removeEventListener('resize', measure)
      container.removeEventListener('scroll', measure)
    }
    // `range`/`selectedText` are plain values recomputed fresh every render (not memoized on a
    // stable identity), so depending on either object directly re-fires this effect on every
    // render -- an infinite measure()/setAnchorRect() loop ("Maximum update depth exceeded").
    // The word-id pair is what the geometry actually depends on; that's already covered above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [range?.startWordId, range?.endWordId])

  useLayoutEffect(() => {
    if (!anchorRect) {
      setToolbarPos(null)
      return
    }
    const margin = 8
    const h = toolbarRef.current?.offsetHeight ?? 56
    const w = toolbarRef.current?.offsetWidth ?? 240
    const spaceBelow = window.innerHeight - anchorRect.bottom
    const top = spaceBelow > h + margin ? anchorRect.bottom + margin : Math.max(margin, anchorRect.top - h - margin)
    const left = Math.min(Math.max(margin, anchorRect.left), window.innerWidth - w - margin)
    setToolbarPos((prev) => (prev && prev.top === top && prev.left === left ? prev : { top, left }))
  }, [anchorRect, toolbarRef])

  return toolbarPos
}
