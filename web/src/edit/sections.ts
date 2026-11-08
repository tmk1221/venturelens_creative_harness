import type { Cut } from '../api/types'

/** Whether a loaded Cut is a T23/T24 "no-media" cut: every passage's angle source is a
 * `kind: "virtual"` Source (no underlying media at all). Returns false for an empty cut.
 * T24 renders these through `RawTranscript` instead of the media-backed `TranscriptView`. */
export function isNoMediaCut(cut: Cut, sourceKindById: Map<string, string>): boolean {
  if (cut.passages.length === 0) return false
  return cut.passages.every((p) => sourceKindById.get(p.angle_source_id) === 'virtual')
}
