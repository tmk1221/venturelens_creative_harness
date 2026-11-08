/** T30 "Additions": behind-subject overlays get a composite preview -- the current app's
 * `story_board.py`/`cutouts.py --preview` shows the A-roll frame with the overlay's cutout
 * composited under it (read-only reference; not ported here). This demo project never has a
 * real A-roll frame to composite against, so a labelled placeholder stands in for it, on the
 * card and (via the same component) in the graph's `overlay.place` node inspector. */
export function CompositePreview({ overlayUrl }: { overlayUrl?: string }) {
  return (
    <div className="rounded border border-dashed border-neutral-300 p-2 text-center text-neutral-500" data-testid="enrich-composite-preview">
      <div className="mx-auto w-full h-20 rounded bg-neutral-100 flex items-center justify-center text-[10px]">
        A-roll frame + cutout overlay (composite placeholder -- no A-roll frame in this demo)
      </div>
      {overlayUrl && <img src={overlayUrl} alt="" className="mt-1 mx-auto h-10 object-contain" />}
    </div>
  )
}
