import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import type { IngestStatus } from '../api/types'
import { getIngestStatus, rerunIngest } from './api'
import { BrandPanel } from './BrandPanel'
import { PictureModeSetting } from './PictureModeSetting'
import { StepList } from './StepList'
import { foldRun } from './steps'
import { TranscriptActions } from './TranscriptActions'
import { useIngestEvents } from './useIngestEvents'

const POLL_MS = 1500

/** T34: `/p/:pid/ingest` -- the project's ingest as it runs (live steps over SSE, progress,
 * failures in plain words with "Try again"), then, once the audio is ready, the transcript
 * actions and "Open editor". T41: the project's brand kit below, as a live style guide. */
export function IngestPage() {
  const { pid } = useParams<{ pid: string }>()
  const [status, setStatus] = useState<IngestStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [retrying, setRetrying] = useState(false)

  const refresh = useCallback(() => {
    if (!pid) return
    getIngestStatus(pid)
      .then((s) => {
        setStatus(s)
        setError(null)
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Could not load this project'))
  }, [pid])

  const byJob = useIngestEvents(pid ?? '', refresh)
  useEffect(refresh, [refresh])

  // Fallback while a job runs, in case the event stream can't connect: the status itself
  // says when the job ends (the step list then fills from the stream's replay, or stays
  // empty and the summary below says how it went).
  const running = status?.job?.state === 'running'
  useEffect(() => {
    if (!running) return
    const t = window.setInterval(refresh, POLL_MS)
    return () => window.clearInterval(t)
  }, [running, refresh])

  const jobId = status?.job?.id ?? null
  const run = useMemo(() => foldRun(jobId ? (byJob.get(jobId) ?? []) : []), [byJob, jobId])

  async function retry() {
    if (!pid) return
    setRetrying(true)
    try {
      await rerunIngest(pid)
      refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start the ingest again')
    } finally {
      setRetrying(false)
    }
  }

  if (!pid) return null
  const job = status?.job ?? null
  const failed = job && (job.state === 'failed' || job.state === 'interrupted')

  return (
    <div data-testid="ingest-page" className="p-6 max-w-2xl w-full space-y-6 overflow-y-auto">
      <header>
        <h1 className="text-lg font-medium">{status?.name ?? 'Ingest'}</h1>
        {status && <p className="text-xs text-neutral-500 break-all">{status.root}</p>}
      </header>
      {error && <p data-testid="ingest-error" className="text-sm text-red-600">{error}</p>}
      {status && !job && status.sources.length === 0 && (
        <p className="text-sm text-neutral-500">
          No recordings in this project yet. <Link to="/new" className="underline">Start a new project from a recording</Link>.
        </p>
      )}

      <section className="space-y-2">
        {job && <h2 className="text-sm font-medium">Getting the recording ready</h2>}
        <StepList steps={run.steps} />
        {job && job.state !== 'running' && (
          <p data-testid="ingest-summary" className={`text-sm ${failed ? 'text-red-600' : 'text-neutral-500'}`}>
            {job.summary}
          </p>
        )}
        {failed && (
          <button type="button" data-testid="ingest-retry" disabled={retrying} onClick={() => void retry()}
            className="rounded border border-neutral-300 dark:border-neutral-700 px-3 py-1 text-sm disabled:opacity-50">
            {retrying ? 'Starting…' : 'Try again'}
          </button>
        )}
      </section>

      {status?.audio_ready && <TranscriptActions pid={pid} status={status} onChanged={refresh} />}

      <PictureModeSetting pid={pid} />

      <BrandPanel pid={pid} />
    </div>
  )
}
