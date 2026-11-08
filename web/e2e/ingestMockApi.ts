import type { Page, Route } from '@playwright/test'
import { freshTranscribeState, handleTranscribeRoute, TRANSCRIBE_JOB, type TranscribeMockState } from './transcribeMockApi'

/** T34 (+T35: transcription and speakers, `transcribeMockApi.ts`): a stateful stand-in for the new-project flow -- `POST /api/projects/new` (202 + job),
 * the ingest job's SSE stream (`?workflow=_ingest`: the step/progress/result events the real
 * `post_core.project_new` op emits), `.../ingest/status`, transcript import and open-editor --
 * plus the handful of editor routes the first cut needs once it opens. `fail: true` makes the
 * job's audio step fail the way a broken file does. */
export const pid = 'proj-new'
export const jobId = 'job-ingest-1'
export const cutId = 'cut-first'
const shootId = 'shoot-1'
const sourceId = 'src-1'
const syncGroupId = 'sg-1'
const transcriptId = 'tr-1'
const ROOT = '/Users/me/Post/show-37-keith'
export const RECORDING = '/Volumes/MediaDrive/Show/episode-37.mp4'
const FAILURE = 'Audio for episode-37.mp4: ffmpeg could not read the file (Invalid data found when processing input).'

// Three turns (T35): SPEAKER_00, SPEAKER_01, SPEAKER_00 again -- so a rename shows "everywhere".
const words = 'so is AI becoming permanent Andrew I think it is'.split(' ').map((text, i) => ({
  id: `w${i}`, schema_version: 1, text, start: i * 0.4, end: i * 0.4 + 0.3, speaker: `SPEAKER_0${i >= 4 && i < 7 ? 1 : 0}`, confidence: 1,
}))

function sse(events: { kind: string; event: Record<string, unknown> }[]): string {
  return 'retry: 60000\n\n' + events.map(({ kind, event }, seq) => {
    const data = { job_id: jobId, workflow_id: '_ingest', seq, kind, at: 0, event: { kind, ...event } }
    return `id: ${seq + 1}\nevent: ${kind}\ndata: ${JSON.stringify(data)}\n\n`
  }).join('')
}

function jobEvents(fail: boolean) {
  const plan = [['check', 'Check the project folder'], ['init', 'Create the project'], ['kit', 'Use the show brand kit'],
    ['source:0', 'Add episode-37.mp4'], ['audio:0', 'Audio for episode-37.mp4'], ['peaks:0', 'Waveform for episode-37.mp4']]
  const out = plan.map(([step, label]) => ({ kind: 'step', event: { step, label, status: 'pending' } }))
  for (const [step, label] of plan) {
    out.push({ kind: 'step', event: { step, label, status: 'running' } })
    if (step === 'audio:0') {
      for (const i of [0, 25, 50, 75]) out.push({ kind: 'progress', event: { step, label, i, n: 100 } })
      if (fail) {
        out.push({ kind: 'step', event: { step, label, status: 'failed', error: FAILURE } })
        out.push({ kind: 'result', event: { ok: false, detail: FAILURE } })
        return out
      }
    }
    out.push({ kind: 'step', event: { step, label, status: 'done' } })
  }
  out.push({ kind: 'result', event: { ok: true, detail: 'Ready: 1 recording(s), 6 step(s) done, 0 already done.' } })
  return out
}

export interface IngestMockState {
  created: Record<string, unknown> | null
  statusCalls: number
  imported: boolean
  cutMade: boolean
  t35: TranscribeMockState
  /** T42: `Project.picture_mode`, changed by `PATCH /api/projects/{pid}`. */
  pictureMode: string
}

/** `lockedCut` (T35's editor tests): the cut plays a `kind: "virtual"` stand-in source, so the
 * Playwright build (`VITE_PRE_LOCK_TOOLS=1`) renders the same RawTranscript production always
 * does; the recording itself stays in the sync group as its audio, for speaker samples. */
export async function mockIngestApi(page: Page, { fail = false, lockedCut = false } = {}): Promise<IngestMockState> {
  const state: IngestMockState = { created: null, statusCalls: 0, imported: false, cutMade: false, t35: freshTranscribeState(), pictureMode: 'presenter' }
  const base = `/api/projects/${pid}`

  function status() {
    state.statusCalls += 1
    const running = state.statusCalls === 1 // the first look sees the job still running
    const done = !running && !fail
    const transcribed = state.t35.phase === 2
    const hasTranscript = state.imported || transcribed
    const transcribeJob = state.t35.phase === 0 ? null
      : { id: TRANSCRIBE_JOB, state: transcribed ? 'ok' : 'running', summary: transcribed ? 'Transcribed 10 words, 2 speakers.' : null }
    return {
      name: 'Show 37 Sample', root: ROOT, brand_kit: 'show', cut_ids: state.cutMade ? [cutId] : [],
      job: { id: jobId, state: running ? 'running' : fail ? 'failed' : 'ok', summary: running ? null : fail ? FAILURE : 'Ready: 1 recording(s).' },
      sources: [{
        source_id: sourceId, shoot_id: shootId, sync_group_id: syncGroupId, name: 'episode-37.mp4', path: RECORDING,
        audio_ready: done, peaks_ready: done, transcript_id: hasTranscript ? transcriptId : null, words: hasTranscript ? words.length : 0,
        transcribe_job: transcribeJob,
      }],
      audio_ready: done, has_transcript: hasTranscript,
    }
  }

  await page.route('**/api/**', async (route: Route) => {
    const req = route.request()
    const url = new URL(req.url())
    const path = url.pathname
    const method = req.method()
    if (await handleTranscribeRoute(route, state.t35, { base, syncGroupId, transcriptId, sourceId })) return

    if (path === '/api/projects/new' && method === 'POST') {
      state.created = req.postDataJSON() as Record<string, unknown>
      if (String(state.created.root).includes('/Video/source')) {
        return route.fulfill({ status: 400, json: { detail: `The project folder ${state.created.root} is inside the footage folder. Post never writes there.` } })
      }
      return route.fulfill({ status: 202, json: { project: { id: pid, root: ROOT, name: 'Show 37 Sample' }, job_id: jobId } })
    }
    if (path === `${base}/events`) {
      if (url.searchParams.get('workflow') !== '_ingest') return route.abort()
      return route.fulfill({ status: 200, headers: { 'content-type': 'text/event-stream', 'cache-control': 'no-cache' }, body: sse(jobEvents(fail)) })
    }
    if (path === `${base}/ingest/status`) return route.fulfill({ json: status() })
    if (path === `${base}/ingest/transcript` && method === 'POST') {
      state.imported = true
      return route.fulfill({ json: { ...status().sources[0], transcript_id: transcriptId, words: words.length } })
    }
    if (path === `${base}/ingest/open-editor` && method === 'POST') {
      const created = !state.cutMade
      state.cutMade = true
      return route.fulfill({ json: { cut_id: cutId, created } })
    }
    if (path === `${base}/ingest/run` && method === 'POST') return route.fulfill({ status: 202, json: { id: 'job-ingest-2', state: 'running' } })

    // The shell around every project page.
    if (path === '/api/projects' && method === 'GET') return route.fulfill({ json: { projects: [] } })
    if (path === base) {
      if (method === 'PATCH') state.pictureMode = String((req.postDataJSON() as { picture_mode?: string }).picture_mode ?? state.pictureMode)
      return route.fulfill({ json: { id: pid, schema_version: 1, name: 'Show 37 Sample', root: ROOT, brand_kit: 'show', picture_mode: state.pictureMode } })
    }
    if (path === '/api/brand-kits') {
      return route.fulfill({ json: { kits: [{ id: 'show', name: 'Sample Weekly Show', status: 'guessed', counts: null, error: null }] } })
    }
    if (path === '/api/library') return route.fulfill({ json: { root: '/Volumes/MediaDrive', exists: true, companies: [] } })
    if (path === '/api/doctor') return route.fulfill({ json: { providers: 'fake' } })

    // The first cut, as the editor loads it.
    const source = { id: sourceId, schema_version: 1, path: RECORDING, fps: { num: 25, den: 1 }, start_timecode: '00:00:00:00', role: 'a_roll', kind: 'real', proxy_path: null, peaks_path: null, audio_proxy_path: `${ROOT}/.post3/proxies/x.audio.m4a`, content_fingerprint: 'fp' }
    const virtual = { ...source, id: 'src-locked', path: null, role: 'a_roll', kind: 'virtual', audio_proxy_path: null }
    const audio = { ...source, role: 'audio' }
    const sources = lockedCut ? [virtual, audio] : [source]
    const angleId = lockedCut ? virtual.id : sourceId
    if (path === `${base}/shoots`) {
      const group = { id: syncGroupId, schema_version: 1, source_ids: sources.map((x) => x.id), offsets: Object.fromEntries(sources.map((x) => [x.id, 0])) }
      return route.fulfill({ json: [{ id: shootId, schema_version: 1, name: 'default', sources, sync_groups: [group], transcript_ids: state.imported || state.t35.phase === 2 ? [transcriptId] : [] }] })
    }
    if (path === `${base}/transcripts/${transcriptId}`) {
      return route.fulfill({ json: { revision: 1, word_count: words.length, transcript: { id: transcriptId, schema_version: 1, sync_group_id: syncGroupId, provider: 'import:json', fingerprint: 'x' } } })
    }
    if (path === `${base}/transcripts/${transcriptId}/words`) return route.fulfill({ json: { transcript_id: transcriptId, total: words.length, offset: 0, limit: 2000, words } })
    if (path === `${base}/transcripts/${transcriptId}/suggestions`) return route.fulfill({ json: [] })
    if (path === `${base}/cuts/${cutId}`) {
      return route.fulfill({ json: { revision: 1, cut: { id: cutId, schema_version: 1, aspect: { num: 16, den: 9 }, fps: { num: 25, den: 1 }, parent_cut_id: null, variant_label: '', sections: [], spans: [], passages: [{ id: 'p1', schema_version: 1, sync_group_id: syncGroupId, start_word_id: 'w0', end_word_id: `w${words.length - 1}`, trims: { head: 0, tail: 0 }, angle_source_id: angleId, framing: null }] } } })
    }
    if (path === `${base}/cuts/${cutId}/timeline`) return route.fulfill({ json: [] })
    if (path === `${base}/cuts/${cutId}/suggested-visuals`) return route.fulfill({ json: { items: [] } })
    if (path === `${base}/cuts/${cutId}/decisions`) return route.fulfill({ json: { rows: [], counts: { pick: 0, approve: 0, failed: 0, waiting_on: 0 } } })
    return route.abort() // media and anything else: not part of this flow
  })
  return state
}
