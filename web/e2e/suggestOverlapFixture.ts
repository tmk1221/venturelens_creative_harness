/** T41: the overlap shape from Travis's first real suggest pass (Show demo, 8 proposals on a
 * 70-word transcript; `GET .../suggested-visuals`, read once, shape copied, words re-pointed at
 * `rawTranscriptMockApi`'s 12 words w0..w11). Four pairs cover identical word ranges (one of
 * them a picture + an overlay "behind"), and one proposal starts inside another and ends on the
 * same word -- so badges collide unless they are laid out. Server order kept, not transcript order. */
const base = { transcript_id: 'tr-rt', overlay_depth: null, overlay_position: null, flags: [], cast_refs: [], density_hint: null }

function p(id: string, start: number, end: number, medium: string, brief: string, extra: Record<string, unknown> = {}) {
  return {
    ...base, id, start_word_id: `w${start}`, end_word_id: `w${end}`, medium, brief,
    direction_note: 'Hard cut in on the first word.', rationale: 'Rule 6: names a term.', ...extra,
  }
}

export const overlapProposals: Record<string, unknown>[] = [
  p('ov-a', 1, 4, 'motion_graphic', 'Title card: Virtual Machine.', { flags: ['picture_must_match_words'] }),
  p('ov-b', 5, 7, 'live_action', 'Montage of screens on an unattended remote machine.'),
  p('ov-c', 8, 9, 'motion_graphic', "Clean diagram: 'You' connects through an interface."),
  p('ov-d', 10, 11, 'aroll', 'Presenter on camera delivering the conclusion.', { flags: ['presenter_stays_on_camera'] }),
  p('ov-e', 2, 4, 'motion_graphic', 'Title card: "Virtual Machine" in clean type.'),
  p('ov-f', 5, 7, 'motion_graphic', 'A glowing agent node inside a cloud host.'),
  p('ov-g', 8, 9, 'aroll', 'The presenter stays in frame; a diagram builds behind him.', { overlay_depth: 'behind', overlay_position: 'right' }),
  p('ov-h', 10, 11, 'aroll', 'The presenter is on camera alone.', { flags: ['presenter_stays_on_camera'] }),
]
