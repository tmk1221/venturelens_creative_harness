import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { JobsDrawer } from './JobsDrawer'
import { useJobsStore, type JobView } from '../store/jobsStore'
import { cancelJob } from './api'

/** T35: the drawer used to stay empty -- the server names every SSE event after its kind and
 * the store only had `onmessage`. T30e: the jobs drawer shows each job's exact prompt text (a worker's `prompt` event,
 * `packages/post_core/post_core/workers/contract.py::EVENT_KINDS["prompt"]`) and a Cancel
 * button. Exercised at the component level (mocked `cancelJob`, a hand-seeded `jobsStore`)
 * rather than through the real backend -- the fake providers run near-instantly, so a real
 * e2e run can't reliably catch a job still "live" long enough to click Cancel on it. */
vi.mock('./api', () => ({
  cancelJob: vi.fn().mockResolvedValue({ job_id: 'job-1', cancelled: true }),
}))

// `JobsDrawer` connects the project SSE stream on mount; jsdom has no `EventSource`. This
// stand-in keeps listeners by event name, the way a real `EventSource` dispatches the
// server's named events (`event: progress`) -- never to `onmessage`.
class EventSourceStub {
  static last: EventSourceStub | null = null
  url: string
  listeners = new Map<string, ((e: MessageEvent<string>) => void)[]>()
  onmessage: ((e: MessageEvent<string>) => void) | null = null
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  constructor(url: string) {
    this.url = url
    EventSourceStub.last = this
  }
  addEventListener(name: string, fn: (e: MessageEvent<string>) => void) {
    this.listeners.set(name, [...(this.listeners.get(name) ?? []), fn])
  }
  /** What the browser does with `event: <name>\ndata: <json>`. */
  emitNamed(name: string, data: unknown) {
    const msg = new MessageEvent('message', { data: JSON.stringify(data) })
    for (const fn of this.listeners.get(name) ?? []) fn(msg)
  }
  close() {}
}

beforeEach(() => {
  vi.stubGlobal('EventSource', EventSourceStub)
  useJobsStore.setState({ jobsById: new Map(), connected: false, source: null })
  vi.mocked(cancelJob).mockClear()
})
afterEach(() => {
  vi.unstubAllGlobals()
})

function seedJob(overrides: Partial<JobView> = {}) {
  const jobsById = new Map(useJobsStore.getState().jobsById)
  jobsById.set('job-1', { job_id: 'job-1', workflow_id: 'wf-1', seq: 1, kind: 'progress', at: 0, event: {}, ...overrides })
  useJobsStore.setState({ jobsById })
}

describe('JobsDrawer', () => {
  it("shows a job's exact prompt text, sticky across a later event", () => {
    seedJob({
      kind: 'prompt',
      event: { text: 'a cinematic still of a rooftop garden', model: 'nano_banana_2' },
      promptText: 'a cinematic still of a rooftop garden',
      promptModel: 'nano_banana_2',
    })
    render(<JobsDrawer pid="p1" />)
    fireEvent.click(screen.getByTestId('jobs-drawer-toggle'))
    expect(screen.getByTestId('job-prompt-text')).toHaveTextContent('a cinematic still of a rooftop garden')
    expect(screen.getByTestId('job-prompt-text')).toHaveTextContent('nano_banana_2')
  })

  it('shows Cancel for a live job and calls the cancel endpoint', () => {
    seedJob({ kind: 'progress', event: { progress: 0.4 } })
    render(<JobsDrawer pid="p1" />)
    fireEvent.click(screen.getByTestId('jobs-drawer-toggle'))
    fireEvent.click(screen.getByTestId('job-cancel'))
    expect(cancelJob).toHaveBeenCalledWith('p1', 'job-1')
  })

  it("follows a transcription job's progress from the server's named SSE events", () => {
    render(<JobsDrawer pid="p1" />)
    const es = EventSourceStub.last!
    expect(es.url).toBe('/api/projects/p1/events')
    const ev = (seq: number, kind: string, event: Record<string, unknown>) =>
      act(() => es.emitNamed(kind, { job_id: 'job-t', workflow_id: 'transcribe-sg1', seq, kind, at: seq, event: { kind, ...event } }))
    ev(0, 'step', { label: 'Uploading the audio to Deepgram' })
    ev(1, 'progress', { i: 40, n: 100, label: 'Uploading the audio to Deepgram' })
    fireEvent.click(screen.getByTestId('jobs-drawer-toggle'))
    expect(screen.getByTestId('job-row')).toHaveTextContent('Transcription')
    expect(screen.getByTestId('job-label')).toHaveTextContent('Uploading the audio to Deepgram')
    expect(screen.getByTestId('job-progress')).toHaveTextContent('40%')
    expect(screen.getByTestId('job-cancel')).toBeInTheDocument()

    ev(1, 'progress', { i: 10, n: 100 }) // a replayed event changes nothing
    expect(screen.getByTestId('job-progress')).toHaveTextContent('40%')
    ev(2, 'cost', { amount: 0.28, unit: 'usd', estimated: true })
    ev(3, 'result', { ok: true, detail: 'Transcribed 6,214 words, 2 speakers.' })
    expect(screen.getByTestId('job-result')).toHaveTextContent('Transcribed 6,214 words, 2 speakers.')
    expect(screen.getByTestId('job-cost')).toHaveTextContent('0.28 usd')
    expect(screen.queryByTestId('job-progress')).not.toBeInTheDocument()
    expect(screen.queryByTestId('job-cancel')).not.toBeInTheDocument()
  })

  it('hides Cancel once a job has resolved', () => {
    seedJob({ kind: 'result', event: { ok: true } })
    render(<JobsDrawer pid="p1" />)
    fireEvent.click(screen.getByTestId('jobs-drawer-toggle'))
    expect(screen.queryByTestId('job-cancel')).not.toBeInTheDocument()
  })
})
