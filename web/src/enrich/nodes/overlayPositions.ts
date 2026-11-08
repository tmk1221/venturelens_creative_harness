/** Mirrors `post_core.model.cut.valid_overlay_positions`/`OverlayDepth`/`OverlayPosition`
 * (T30a matrix) for the `overlay.place` in-node picker (`OverlayPlaceNode.tsx`) -- pure
 * lookup, no React. The node itself only carries `depth`/`position` (`OverlayPlaceParams`),
 * not the picture layer's own kind, so this defaults to the `aroll` matrix (the only kind
 * `depth: "behind"` is ever legal for) when the picture kind isn't known; callers that do
 * know it (none yet -- T30c's dialog enforces the matrix before this node ever exists) can
 * pass it explicitly. */
export type OverlayDepth = 'in_front' | 'behind'
export type OverlayPosition = 'right' | 'left' | 'lower-band' | 'full-frame' | 'center' | 'full-width'

const AROLL_POSITIONS: Record<OverlayDepth, OverlayPosition[]> = {
  in_front: ['right', 'left', 'lower-band'],
  behind: ['right', 'left', 'full-frame'],
}
const BROLL_POSITIONS: Record<OverlayDepth, OverlayPosition[]> = {
  in_front: ['right', 'left', 'lower-band', 'center', 'full-width'],
  behind: [],
}

export function validOverlayPositions(depth: OverlayDepth, pictureKind: string = 'aroll'): OverlayPosition[] {
  return pictureKind === 'aroll' ? AROLL_POSITIONS[depth] : BROLL_POSITIONS[depth]
}
