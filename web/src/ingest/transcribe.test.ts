import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createBudget, getTranscribeEstimate, startTranscription } from './api'
import { foldTranscribe, transcribeSummary, transcribeWithConfirm } from './transcribe'
import type { IngestEvent } from './steps'

vi.mock('./api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./api')>()),
  getTranscribeEstimate: vi.fn(),
  createBudget: vi.fn().mockResolvedValue({}),
  startTranscription: vi.fn().mockResolvedValue({ job_id: 'job-1', workflow_id: 'transcribe-sg1', amount: 0.28, unit: 'usd' }),
}))

const EPISODE = { sync_group_id: 'sg1', provider: 'deepgram', audio_path: '/p/.post3/proxies/x.audio.m4a', minutes: 43, usd_per_minute: 0.0063, amount: 0.28, unit: 'usd' }

beforeEach(() => {
  vi.mocked(getTranscribeEstimate).mockResolvedValue(EPISODE)
  vi.mocked(createBudget).mockClear()
  vi.mocked(startTranscription).mockClear()
})

describe('T35 transcribe', () => {
  it('shows a 43-minute episode as one estimate in usd', () => {
    expect(transcribeSummary('episode-37.mp4', EPISODE)).toEqual({
      nodeIds: ['transcribe'], amount: 0.28, unit: 'usd', label: '43 min of audio (Deepgram)', title: 'Transcribe episode-37.mp4?',
    })
    expect(() => transcribeSummary('x.mp4', { ...EPISODE, amount: null })).toThrow('nothing spends blind')
  })

  it('Cancel spends nothing; Confirm makes one budget capped at the shown amount, then queues', async () => {
    const source = { name: 'episode-37.mp4', sync_group_id: 'sg1' }
    expect(await transcribeWithConfirm('p1', source, async () => false)).toEqual({ cancelled: true })
    expect(createBudget).not.toHaveBeenCalled()
    expect(startTranscription).not.toHaveBeenCalled()

    const confirm = vi.fn().mockResolvedValue(true)
    const queued = await transcribeWithConfirm('p1', source, confirm, () => 123)
    expect(confirm.mock.calls[0]![0]).toMatchObject({ amount: 0.28, unit: 'usd' })
    expect(createBudget).toHaveBeenCalledWith('p1', 'transcribe-sg1-123', 0.28, 'usd')
    expect(startTranscription).toHaveBeenCalledWith('p1', 'sg1', 'transcribe-sg1-123')
    expect(queued).toMatchObject({ job_id: 'job-1' })
  })

  it('folds the worker events into a label, a percent and the outcome', () => {
    const e = (seq: number, kind: string, event: Record<string, unknown>): IngestEvent => ({ job_id: 'j', seq, kind, event })
    expect(foldTranscribe([e(0, 'step', { label: 'Uploading the audio to Deepgram' }), e(1, 'progress', { i: 42, n: 100 })]))
      .toEqual({ label: 'Uploading the audio to Deepgram', percent: 42, result: null })
    expect(foldTranscribe([e(0, 'progress', { i: 100, n: 100 }), e(1, 'step', { label: 'Saving the transcript' }),
      e(2, 'result', { ok: true, detail: 'Transcribed 6 words, 2 speakers.' })]))
      .toEqual({ label: 'Saving the transcript', percent: null, result: { ok: true, detail: 'Transcribed 6 words, 2 speakers.' } })
  })
})
