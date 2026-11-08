import type { TimelineSegment } from '../../api/types'
import type { WordIndex } from '../blocks'

/** Mirrors `post_core.edit.ranges.word_at` client-side for playback-follow display only
 * (highlighting the current word / auto-scroll) -- never used to decide an edit. */
export function frameToWordId(
  segments: TimelineSegment[],
  frame: number,
  wordIndexBySyncGroup: Map<string, WordIndex>,
): string | null {
  const seg = segments.find((s) => frame >= s.start_frame && frame < s.start_frame + Math.max(1, s.duration_frames))
  if (!seg) return null
  const frac = seg.duration_frames <= 0 ? 0 : (frame - seg.start_frame) / seg.duration_frames
  const sourceTime = seg.source_start + frac * (seg.source_end - seg.source_start)
  const wordIndex = wordIndexBySyncGroup.get(seg.sync_group_id)
  if (!wordIndex) return null
  let best: { id: string; d: number } | null = null
  for (const w of wordIndex.words) {
    if (w.start <= sourceTime && sourceTime <= w.end) return w.id
    const d = Math.min(Math.abs(w.start - sourceTime), Math.abs(w.end - sourceTime))
    if (!best || d < best.d) best = { id: w.id, d }
  }
  return best?.id ?? null
}

/** Inverse: the frame at which `wordId` (in `syncGroupId`) plays, or null if it's not
 * covered by the current timeline. */
export function wordIdToFrame(
  segments: TimelineSegment[],
  wordIndexBySyncGroup: Map<string, WordIndex>,
  syncGroupId: string,
  wordId: string,
): number | null {
  const wordIndex = wordIndexBySyncGroup.get(syncGroupId)
  if (!wordIndex) return null
  const idx = wordIndex.indexOf.get(wordId)
  if (idx === undefined) return null
  const word = wordIndex.words[idx]
  if (!word) return null
  for (const seg of segments) {
    if (seg.sync_group_id !== syncGroupId) continue
    if (word.start < seg.source_start || word.start > seg.source_end) continue
    const span = seg.source_end - seg.source_start
    const frac = span <= 0 ? 0 : (word.start - seg.source_start) / span
    return Math.round(seg.start_frame + frac * seg.duration_frames)
  }
  return null
}
