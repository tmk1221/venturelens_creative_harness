import { type OverlayDepth, type OverlayPosition, validOverlayPositions } from './overlayPositions'

/** T30d: `overlay.place`'s in-node body -- a compact depth/position pair (T30a matrix, see
 * `overlayPositions.ts`). Changing either patches params, which gives the node a fresh
 * `input_hash` (`OverlayPlaceParams`'s own docstring) and marks everything downstream stale
 * -- no extra plumbing needed here for that half of the spec line. Switching depth resets
 * position to the first value still legal for the new depth when the old one no longer is
 * (the T30a "swap" rule itself -- lower-band <-> full-frame -- lives in the beat-level dialog
 * T30c owns; this node only needs to never end up holding an invalid combination). */
export function OverlayPlaceNode({
  depth, position, onPatchParams,
}: {
  depth: OverlayDepth
  position: OverlayPosition
  onPatchParams: (params: Record<string, unknown>) => void
}) {
  const positions = validOverlayPositions(depth)

  return (
    <div className="graph-node-overlay-place" data-testid="node-overlay-place" onClick={(e) => e.stopPropagation()}>
      <select
        data-testid="graph-overlay-depth"
        value={depth}
        onChange={(e) => {
          const nextDepth = e.target.value as OverlayDepth
          const nextPositions = validOverlayPositions(nextDepth)
          const nextPosition = nextPositions.includes(position) ? position : nextPositions[0]
          onPatchParams({ depth: nextDepth, position: nextPosition })
        }}
      >
        <option value="in_front">in front</option>
        <option value="behind">behind</option>
      </select>
      <select
        data-testid="graph-overlay-position"
        value={position}
        onChange={(e) => onPatchParams({ depth, position: e.target.value })}
      >
        {positions.map((p) => (
          <option key={p} value={p}>{p}</option>
        ))}
      </select>
    </div>
  )
}
