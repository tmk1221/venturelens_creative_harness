import path from 'node:path'
import { fileURLToPath } from 'node:url'
import type { Page, Route } from '@playwright/test'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

export const pid = 'pid-boundary'
export const cutId = 'cut-boundary'
const transcriptId = 't-boundary'
const syncGroupId = 'sg-boundary'
const passageId = 'p-boundary'
const sourceA = 'src-a'
const sourceB = 'src-b'

const FPS = 25

/** Two one-second timeline segments, each backed by its own tiny ffmpeg-generated audio
 * proxy (`fixtures/audio/seg-{a,b}.m4a`, distinct sine tones so a human could tell them
 * apart too) -- exercises the pooled-`<audio>` boundary swap in `Monitor.tsx` for real, not
 * via a synthetic timeline the component never actually renders. T22: Post is audio-only. */
export const timeline = [
  { passage_id: passageId, sync_group_id: syncGroupId, angle_source_id: sourceA, audio_source_id: sourceA, source_start: 0, source_end: 1, start_frame: 0, duration_frames: FPS },
  { passage_id: passageId, sync_group_id: syncGroupId, angle_source_id: sourceB, audio_source_id: sourceB, source_start: 0, source_end: 1, start_frame: FPS, duration_frames: FPS },
]

const cut = {
  id: cutId, schema_version: 1, aspect: { num: 16, den: 9 }, fps: { num: FPS, den: 1 },
  parent_cut_id: null, variant_label: '', sections: [],
  passages: [{
    id: passageId, schema_version: 1, sync_group_id: syncGroupId,
    start_word_id: 'w1', end_word_id: 'w2', trims: { head: 0, tail: 0 },
    angle_source_id: sourceA, framing: null,
  }],
  spans: [],
}

const shoots = [{
  id: 'shoot-boundary', schema_version: 1, name: 'default',
  sources: [
    { id: sourceA, schema_version: 1, path: '/dev/null', fps: { num: FPS, den: 1 }, start_timecode: '00:00:00:00', role: 'a_roll', proxy_path: null, peaks_path: null, content_fingerprint: 'a' },
    { id: sourceB, schema_version: 1, path: '/dev/null', fps: { num: FPS, den: 1 }, start_timecode: '00:00:00:00', role: 'a_roll', proxy_path: null, peaks_path: null, content_fingerprint: 'b' },
  ],
  sync_groups: [{ id: syncGroupId, schema_version: 1, source_ids: [sourceA, sourceB], offsets: { [sourceA]: 0, [sourceB]: 0 } }],
  transcript_ids: [transcriptId],
}]

const words = [
  { id: 'w1', schema_version: 1, text: 'one', start: 0, end: 0.2, speaker: '', confidence: 1 },
  { id: 'w2', schema_version: 1, text: 'two', start: 0.2, end: 0.4, speaker: '', confidence: 1 },
]

export async function mockBoundaryApi(page: Page) {
  await page.route('**/api/**', async (route: Route) => {
    const req = route.request()
    const url = new URL(req.url())
    const p = url.pathname
    const method = req.method()

    if (p === '/api/projects' && method === 'GET') return route.fulfill({ json: { projects: [{ id: pid, root: '/tmp/boundary', name: 'Boundary' }] } })
    if (p === `/api/projects/${pid}/shoots`) return route.fulfill({ json: shoots })
    if (p === `/api/projects/${pid}/cuts` && method === 'GET') return route.fulfill({ json: [{ id: cutId, aspect: cut.aspect, variant_label: '', parent_cut_id: null, passage_count: 1 }] })
    if (p === `/api/projects/${pid}/cuts/${cutId}` && method === 'GET') return route.fulfill({ json: { revision: 1, cut } })
    if (p === `/api/projects/${pid}/cuts/${cutId}/timeline`) return route.fulfill({ json: timeline })
    if (p === `/api/projects/${pid}/transcripts/${transcriptId}/words`) return route.fulfill({ json: { transcript_id: transcriptId, total: words.length, offset: 0, limit: 500, words } })
    if (p === `/api/projects/${pid}/transcripts/${transcriptId}/suggestions`) return route.fulfill({ json: [] })
    if (p === `/api/projects/${pid}/transcripts/${transcriptId}` && method === 'GET') {
      return route.fulfill({ json: { revision: 1, transcript: { id: transcriptId, schema_version: 1, sync_group_id: syncGroupId, provider: 'test', fingerprint: 'x' }, word_count: words.length } })
    }
    if (p === `/api/projects/${pid}/events`) return route.abort()
    // T30e: the top-bar Decisions view polls this on every mount -- stub it out so it
    // doesn't fall through to a real network request.
    if (p === `/api/projects/${pid}/cuts/${cutId}/decisions` && method === 'GET') {
      return route.fulfill({ json: { rows: [], counts: { pick: 0, approve: 0, failed: 0, waiting_on: 0 } } })
    }

    if (p === `/api/projects/${pid}/media/${sourceA}/audio`) {
      return route.fulfill({ path: path.join(__dirname, 'fixtures/audio/seg-a.m4a'), headers: { 'Content-Type': 'audio/mp4' } })
    }
    if (p === `/api/projects/${pid}/media/${sourceB}/audio`) {
      return route.fulfill({ path: path.join(__dirname, 'fixtures/audio/seg-b.m4a'), headers: { 'Content-Type': 'audio/mp4' } })
    }
    if (p.startsWith(`/api/projects/${pid}/media/`)) return route.abort()

    return route.continue()
  })
}
