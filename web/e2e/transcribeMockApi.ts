import type { Route } from '@playwright/test'

/** T35: the transcription + speaker routes of the mocked Ingest/editor API (wired into
 * `ingestMockApi.ts`). The transcription's SSE is served in two phases the test controls
 * (`phase`): 1 = uploading at 40 %, 2 = done. Every stream closes after what it has, with a
 * short `retry:`, so the browser's `EventSource` reconnects (sending `Last-Event-ID`) and picks
 * up the next phase -- the page's own `?workflow=transcribe-<sg>` stream and the Jobs drawer's
 * all-workflows stream alike. */
export const TRANSCRIBE_JOB = 'job-transcribe-1'

export interface TranscribeMockState {
  phase: 0 | 1 | 2
  budgets: { id: string; cap: number; unit: string }[]
  transcribeBody: Record<string, unknown> | null
  names: Record<string, string>
  renames: Record<string, string>[]
  audioRequests: number
}

export function freshTranscribeState(): TranscribeMockState {
  return { phase: 0, budgets: [], transcribeBody: null, names: {}, renames: [], audioRequests: 0 }
}

const UPLOAD = 'Uploading the audio to Deepgram'
const EVENTS: [phase: 1 | 2, kind: string, event: Record<string, unknown>][] = [
  [1, 'step', { label: UPLOAD }],
  [1, 'progress', { i: 40, n: 100, label: UPLOAD }],
  [2, 'progress', { i: 100, n: 100, label: UPLOAD }],
  [2, 'step', { label: 'Saving the transcript' }],
  [2, 'cost', { amount: 0.28, unit: 'usd', provider: 'deepgram', estimated: true }],
  [2, 'result', { ok: true, detail: 'Transcribed 10 words, 2 speakers.' }],
]

function transcribeStream(state: TranscribeMockState, lastId: number, workflowId: string): string {
  const out = EVENTS.map(([phase, kind, event], i) => ({ id: i + 1, phase, kind, event }))
    .filter((e) => e.id > lastId && e.phase <= state.phase)
    .map(({ id, kind, event }) => {
      const data = { job_id: TRANSCRIBE_JOB, workflow_id: workflowId, seq: id - 1, kind, at: id, event: { kind, ...event } }
      return `id: ${id}\nevent: ${kind}\ndata: ${JSON.stringify(data)}\n\n`
    })
  return 'retry: 300\n\n' + out.join('')
}

/** A short silent WAV (8 kHz mono 16-bit) to play speaker samples from, served with ranges. */
function silentWav(seconds: number): Buffer {
  const samples = 8000 * seconds
  const buf = Buffer.alloc(44 + samples * 2)
  buf.write('RIFF', 0); buf.writeUInt32LE(36 + samples * 2, 4); buf.write('WAVE', 8); buf.write('fmt ', 12)
  buf.writeUInt32LE(16, 16); buf.writeUInt16LE(1, 20); buf.writeUInt16LE(1, 22); buf.writeUInt32LE(8000, 24)
  buf.writeUInt32LE(16000, 28); buf.writeUInt16LE(2, 32); buf.writeUInt16LE(16, 34); buf.write('data', 36)
  buf.writeUInt32LE(samples * 2, 40)
  return buf
}
const WAV = silentWav(6)

export const SAMPLES = {
  SPEAKER_00: { start: 0, end: 1.5, words: 7, text: 'so is AI becoming' },
  SPEAKER_01: { start: 1.6, end: 2.7, words: 3, text: 'permanent Andrew I' },
}

function speakers(state: TranscribeMockState, transcriptId: string, sourceId: string) {
  return {
    transcript_id: transcriptId, revision: 1 + state.renames.length, source_id: sourceId,
    speakers: Object.entries(SAMPLES).map(([label, s]) => ({
      label, name: state.names[label] ?? null, words: s.words, sample: { start: s.start, end: s.end, text: s.text },
    })),
  }
}

/** Handles a T35 route, or returns false so the caller's own routes/fallback apply. */
export async function handleTranscribeRoute(
  route: Route, state: TranscribeMockState, ids: { base: string; syncGroupId: string; transcriptId: string; sourceId: string },
): Promise<boolean> {
  const req = route.request()
  const url = new URL(req.url())
  const path = url.pathname
  const method = req.method()
  const { base } = ids
  const workflowId = `transcribe-${ids.syncGroupId}`

  if (path === `${base}/ingest/transcribe/estimate`) {
    await route.fulfill({ json: { sync_group_id: ids.syncGroupId, provider: 'deepgram', audio_path: '/p/.post3/proxies/x.audio.m4a', minutes: 43.02, usd_per_minute: 0.0063, amount: 0.28, unit: 'usd' } })
    return true
  }
  if (path.startsWith(`${base}/budgets/`) && method === 'PUT') {
    const body = req.postDataJSON() as { cap: number; unit: string }
    state.budgets.push({ id: decodeURIComponent(path.slice(`${base}/budgets/`.length)), ...body })
    await route.fulfill({ json: { budget: { id: 'x', cap: body.cap, spent: 0, unit: body.unit } } })
    return true
  }
  if (path === `${base}/ingest/transcribe` && method === 'POST') {
    state.transcribeBody = req.postDataJSON() as Record<string, unknown>
    state.phase = 1
    await route.fulfill({ status: 202, json: { job_id: TRANSCRIBE_JOB, workflow_id: workflowId, amount: 0.28, unit: 'usd' } })
    return true
  }
  const workflow = url.searchParams.get('workflow')
  if (path === `${base}/events` && (workflow === workflowId || workflow === null)) {
    const lastId = Number(req.headers()['last-event-id'] ?? 0)
    await route.fulfill({ status: 200, headers: { 'content-type': 'text/event-stream', 'cache-control': 'no-cache' }, body: transcribeStream(state, lastId, workflowId) })
    return true
  }
  if (path === `${base}/transcripts/${ids.transcriptId}/speakers`) {
    if (method === 'PUT') {
      const { names } = req.postDataJSON() as { names: Record<string, string> }
      state.renames.push(names)
      Object.assign(state.names, names)
    }
    await route.fulfill({ json: speakers(state, ids.transcriptId, ids.sourceId) })
    return true
  }
  if (path === `${base}/media/${ids.sourceId}/audio`) {
    state.audioRequests += 1
    const range = /bytes=(\d+)-(\d*)/.exec(req.headers()['range'] ?? '')
    if (!range) {
      await route.fulfill({ status: 200, headers: { 'content-type': 'audio/wav', 'accept-ranges': 'bytes' }, body: WAV })
      return true
    }
    const start = Number(range[1])
    const end = range[2] ? Math.min(Number(range[2]), WAV.length - 1) : WAV.length - 1
    await route.fulfill({
      status: 206, body: WAV.subarray(start, end + 1),
      headers: { 'content-type': 'audio/wav', 'accept-ranges': 'bytes', 'content-range': `bytes ${start}-${end}/${WAV.length}` },
    })
    return true
  }
  return false
}
