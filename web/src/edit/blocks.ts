import type { Cut, Passage, Word } from '../api/types'

/** One renderable run in the transcript surface: either a surviving passage (`kind:
 * "passage"`) or a stretch of words between two passages of the same sync group that the
 * cut no longer covers (`kind: "gap"` -- only shown when "show cuts" is on). Both carry a
 * contiguous `[startIndex, endIndex]` into that sync group's word array. */
export type Block =
  | { kind: 'passage'; passage: Passage; syncGroupId: string; startIndex: number; endIndex: number }
  | { kind: 'gap'; syncGroupId: string; startIndex: number; endIndex: number; afterPassageId: string }

export interface WordIndex {
  /** word id -> index within that sync group's full word list */
  indexOf: Map<string, number>
  words: Word[]
}

/** Build the transcript surface's block list from a Cut's passages, reconstructing deleted
 * gaps between consecutive same-sync-group passages so "show cuts" can render them. Passages
 * whose sync group has no loaded word index yet are skipped (caller loads on demand). */
export function buildBlocks(cut: Cut, wordIndexBySyncGroup: Map<string, WordIndex>): Block[] {
  const blocks: Block[] = []
  let prevPassage: Passage | null = null
  let prevEndIndex = -1

  for (const passage of cut.passages) {
    const wordIndex = wordIndexBySyncGroup.get(passage.sync_group_id)
    if (!wordIndex) {
      prevPassage = passage
      prevEndIndex = -1
      continue
    }
    const startIndex = wordIndex.indexOf.get(passage.start_word_id)
    const endIndex = wordIndex.indexOf.get(passage.end_word_id)
    if (startIndex === undefined || endIndex === undefined) {
      prevPassage = passage
      prevEndIndex = -1
      continue
    }

    if (
      prevPassage &&
      prevPassage.sync_group_id === passage.sync_group_id &&
      prevEndIndex >= 0 &&
      startIndex > prevEndIndex + 1
    ) {
      blocks.push({
        kind: 'gap',
        syncGroupId: passage.sync_group_id,
        startIndex: prevEndIndex + 1,
        endIndex: startIndex - 1,
        afterPassageId: prevPassage.id ?? '',
      })
    }

    blocks.push({ kind: 'passage', passage, syncGroupId: passage.sync_group_id, startIndex, endIndex })
    prevPassage = passage
    prevEndIndex = endIndex
  }

  return blocks
}

/** Flattened (block, wordIndexWithinBlock) -> word id, for selection math and virtualization. */
export interface FlatWord {
  wordId: string
  text: string
  syncGroupId: string
  blockIndex: number
  deleted: boolean
  passageId: string | null
  angleSourceId: string | null
  /** true for the first word of a block whose block differs from the previous word's --
   * where the transcript surface draws its thin divider + source/angle chip. */
  isBlockStart: boolean
  /** Seconds, from the source Word -- used by `RawTranscript` to break paragraphs at long
   * pauses (T24). Not used by the media-backed `TranscriptView`. */
  start: number
  end: number
  /** T35: the provider's diarization label (`SPEAKER_00`); its name lives on the transcript. */
  speaker?: string
}

export function flattenBlocks(blocks: Block[], wordIndexBySyncGroup: Map<string, WordIndex>): FlatWord[] {
  const out: FlatWord[] = []
  blocks.forEach((block, blockIndex) => {
    const wordIndex = wordIndexBySyncGroup.get(block.syncGroupId)
    if (!wordIndex) return
    for (let i = block.startIndex; i <= block.endIndex; i++) {
      const word = wordIndex.words[i]
      if (!word) continue
      out.push({
        wordId: word.id,
        text: word.text,
        syncGroupId: block.syncGroupId,
        blockIndex,
        deleted: block.kind === 'gap',
        passageId: block.kind === 'passage' ? (block.passage.id ?? null) : null,
        angleSourceId: block.kind === 'passage' ? block.passage.angle_source_id : null,
        isBlockStart: i === block.startIndex,
        start: word.start,
        end: word.end,
        speaker: word.speaker,
      })
    }
  })
  return out
}
