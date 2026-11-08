import type { Page, Route } from '@playwright/test'

/** Minimal hand-authored fixture for the T23/T24 no-media path (RawTranscript): one shoot with
 * a single `kind: "virtual"` source (no media at all), one transcript, one cut whose single
 * passage plays that virtual source -- `isNoMediaCut` (web/src/edit/sections.ts) routes
 * EditWorkspace into RawTranscript for exactly this shape. Built by hand (not
 * `gen_e2e_fixture.py`, which needs ffmpeg + a real post_api process) since RawTranscript never
 * touches media at all. */
export const pid = 'proj-rt'
export const cutId = 'cut-rt'
const transcriptId = 'tr-rt'
const syncGroupId = 'sg-rt'
const sourceId = 'src-rt-virtual'

const VOCAB = ['So', 'today', 'we', 'are', 'going', 'to', 'talk', 'about', 'the', 'launch', 'plan', 'now']
const words = VOCAB.map((text, i) => ({ id: `w${i}`, text, start: i * 0.4, end: i * 0.4 + 0.35 }))

const shoots = [
  {
    id: 'shoot-rt', schema_version: 1, name: 'script', sources: [
      { id: sourceId, schema_version: 1, path: null, fps: { num: 25, den: 1 }, start_timecode: '00:00:00:00', role: 'a_roll', kind: 'virtual', proxy_path: null, peaks_path: null, audio_proxy_path: null, content_fingerprint: 'virtual:rt' },
    ],
    sync_groups: [{ id: syncGroupId, schema_version: 1, source_ids: [sourceId], offsets: { [sourceId]: 0 } }],
    transcript_ids: [transcriptId],
  },
]

const transcript = {
  revision: 1,
  transcript: { id: transcriptId, schema_version: 1, sync_group_id: syncGroupId, provider: 'import:json', fingerprint: 'rt' },
}

const basePassage = {
  id: 'passage-rt', schema_version: 1, sync_group_id: syncGroupId,
  start_word_id: words[0]!.id, end_word_id: words[words.length - 1]!.id,
  trims: { head: 0, tail: 0 }, angle_source_id: sourceId, framing: null,
}

function freshState() {
  return { revision: 1, spans: [] as Record<string, unknown>[] }
}
type State = ReturnType<typeof freshState>

function currentCut(state: State) {
  return {
    id: cutId, schema_version: 1, aspect: { num: 16, den: 9 }, fps: { num: 25, den: 1 },
    parent_cut_id: null, variant_label: '', sections: [], passages: [basePassage], spans: state.spans,
  }
}

/** Wires the handful of `/api/**` routes EditWorkspace/cutStore need to render RawTranscript
 * and exercise "Add visual" end to end, without a real post_api process. */
export async function mockRawTranscriptApi(page: Page) {
  const state = freshState()

  await page.route('**/api/**', async (route: Route) => {
    const req = route.request()
    const url = new URL(req.url())
    const path = url.pathname
    const method = req.method()

    if (path === `/api/projects/${pid}/shoots`) return route.fulfill({ json: shoots })
    if (path === `/api/projects/${pid}/transcripts/${transcriptId}/words`) {
      return route.fulfill({ json: { words, total: words.length } })
    }
    if (path === `/api/projects/${pid}/transcripts/${transcriptId}/suggestions`) return route.fulfill({ json: [] })
    if (path === `/api/projects/${pid}/transcripts/${transcriptId}`) return route.fulfill({ json: transcript })
    if (path === `/api/projects/${pid}/events`) return route.abort()
    // T13b's SuggestOverlay mounts alongside RawTranscript and fetches its pending list on
    // load -- stub it out (empty) so it doesn't 404/hang and drag this suite into its scope.
    if (path === `/api/projects/${pid}/cuts/${cutId}/suggested-visuals` && method === 'GET') {
      return route.fulfill({ json: { items: [] } })
    }
    // T30e: the top-bar Decisions view polls this on every mount -- stub it out (empty) so it
    // doesn't fall through to a real network request and drag unrelated latency in.
    if (path === `/api/projects/${pid}/cuts/${cutId}/decisions` && method === 'GET') {
      return route.fulfill({ json: { rows: [], counts: { pick: 0, approve: 0, failed: 0, waiting_on: 0 } } })
    }

    if (path === `/api/projects/${pid}/cuts/${cutId}` && method === 'GET') {
      return route.fulfill({ json: { revision: state.revision, cut: currentCut(state) } })
    }
    if (path === `/api/projects/${pid}/cuts/${cutId}/timeline`) return route.fulfill({ json: [] })

    if (path === `/api/projects/${pid}/cuts/${cutId}/ops` && method === 'POST') {
      const body = req.postDataJSON() as { name: string; args: Record<string, unknown>; expected_rev: number }
      if (body.expected_rev !== state.revision) {
        return route.fulfill({ status: 409, json: { detail: 'conflict', current_revision: state.revision } })
      }
      if (body.name === 'add_span') {
        state.spans.push({
          id: `span-${state.spans.length + 1}`, schema_version: 1, layer: body.args.layer, kind: body.args.kind,
          orphaned: false, provenance: 'human', note: body.args.note ?? '',
          start_anchor: { transcript_id: transcriptId, word_id: body.args.start_word_id },
          end_anchor: { transcript_id: transcriptId, word_id: body.args.end_word_id },
        })
      } else if (body.name === 'add_beat_spans') {
        // T30c: what `RawTranscript.tsx`'s Save/Open-in-graph actually calls now (see
        // `post_core/edit/_spans.py::add_beat_spans`) -- a picture Span (iff `picture_kind`)
        // and/or an overlay Span (iff `overlay_depth`) sharing the same anchors, in one op.
        const anchor = {
          start_anchor: { transcript_id: transcriptId, word_id: body.args.start_word_id },
          end_anchor: { transcript_id: transcriptId, word_id: body.args.end_word_id },
        }
        const brief = { text: body.args.brief_text ?? '', provenance: body.args.provenance === 'agent' ? 'agent' : 'human' }
        if (body.args.picture_kind) {
          state.spans.push({
            id: `span-${state.spans.length + 1}`, schema_version: 1, layer: 'picture', kind: body.args.picture_kind,
            orphaned: false, provenance: body.args.provenance ?? 'human', note: '',
            direction_note: body.args.direction_note ?? '', flags: body.args.flags ?? [], brief, ...anchor,
          })
        }
        if (body.args.overlay_depth) {
          state.spans.push({
            id: `span-${state.spans.length + 1}`, schema_version: 1, layer: 'overlay', kind: 'overlay',
            orphaned: false, provenance: body.args.provenance ?? 'human', note: '',
            overlay_depth: body.args.overlay_depth, overlay_position: body.args.overlay_position ?? null, brief, ...anchor,
          })
        }
      } else if (body.name === 'remove_span') {
        state.spans = state.spans.filter((s) => s.id !== body.args.span_id)
      }
      state.revision += 1
      return route.fulfill({ json: { cut_id: cutId, revision: state.revision, report: { affected_spans: [], orphaned_spans: [] } } })
    }

    return route.continue()
  })

  return state
}
