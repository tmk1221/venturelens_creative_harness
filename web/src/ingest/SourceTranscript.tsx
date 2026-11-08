import { useEffect, useState } from 'react'
import type { IngestSource } from '../api/types'
import { useSpendConfirmStore } from '../store/spendConfirmStore'
import { importTranscript } from './api'
import { foldTranscribe, transcribeWithConfirm, transcribeWorkflow } from './transcribe'
import { useIngestEvents } from './useIngestEvents'

const BUTTON = 'rounded border border-neutral-300 dark:border-neutral-700 px-3 py-1 text-sm disabled:opacity-50'
const LIVE = new Set(['queued', 'running', 'retry_later'])
const POLL_MS = 3000

/** T35: one transcription job as it runs -- the worker's step label and upload percent over
 * SSE (`?workflow=transcribe-<sync group>`), with a slow status poll as the fallback. */
function TranscribeStatus({ pid, syncGroupId, jobId, onEnded, onPoll }: {
  pid: string; syncGroupId: string; jobId: string; onEnded: () => void; onPoll: () => void
}) {
  const byJob = useIngestEvents(pid, (id) => { if (id === jobId) onEnded() }, transcribeWorkflow(syncGroupId))
  useEffect(() => {
    const t = window.setInterval(onPoll, POLL_MS)
    return () => window.clearInterval(t)
  }, [onPoll])
  const progress = foldTranscribe(byJob.get(jobId) ?? [])
  if (progress.result) return null // the refreshed status says how it ended
  return (
    <p data-testid="transcribe-progress" className="text-sm text-neutral-500">
      Transcribing… {progress.label ?? 'waiting to start'}
      {progress.percent !== null && ` ${progress.percent}%`}
    </p>
  )
}

/** T34/T35: one recording without a transcript yet -- transcribe it (paid, confirmed, queued)
 * or import a finished transcript file (free). */
export function SourceTranscript({ pid, source, onChanged }: { pid: string; source: IngestSource; onChanged: () => void }) {
  const [open, setOpen] = useState(false)
  const [path, setPath] = useState('')
  const [busy, setBusy] = useState(false)
  const [started, setStarted] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const request = useSpendConfirmStore((s) => s.request)

  if (source.transcript_id) {
    return (
      <p data-testid="transcript-ready" className="text-sm text-neutral-500">
        {source.name}: transcript ready ({source.words.toLocaleString()} words)
      </p>
    )
  }

  const job = source.transcribe_job ?? null
  const liveJobId = job && LIVE.has(job.state) ? job.id : started
  const ended = !liveJobId && job && job.state !== 'ok' ? job : null

  async function transcribe() {
    setBusy(true)
    setError(null)
    try {
      const queued = await transcribeWithConfirm(pid, source, request)
      if (!('cancelled' in queued)) {
        setStarted(queued.job_id)
        onChanged()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start the transcription')
    } finally {
      setBusy(false)
    }
  }

  async function submit() {
    if (!path.trim()) return
    setBusy(true)
    setError(null)
    try {
      await importTranscript(pid, source.sync_group_id, path.trim())
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not import the transcript')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-2">
      <p className="text-sm">{source.name} needs a transcript.</p>
      <div className="flex flex-wrap gap-2">
        <button type="button" data-testid="transcribe" disabled={busy || liveJobId !== null} className={BUTTON}
          title="Deepgram transcribes the recording's audio. It costs money: you'll see the estimate first."
          onClick={() => void transcribe()}>
          Transcribe…
        </button>
        <button type="button" data-testid="import-transcript" className={BUTTON} onClick={() => setOpen((o) => !o)}>
          Import transcript…
        </button>
      </div>
      {liveJobId && (
        <TranscribeStatus pid={pid} syncGroupId={source.sync_group_id} jobId={liveJobId} onPoll={onChanged}
          onEnded={() => { setStarted(null); onChanged() }} />
      )}
      {ended && (
        <p data-testid="transcribe-failed" className="text-xs text-red-600">
          The last transcription {ended.state === 'failed' ? 'failed' : `stopped (${ended.state})`}: {ended.summary ?? 'no details'}
        </p>
      )}
      {open && (
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void submit() }}>
          <input
            data-testid="transcript-path"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="/path/to/transcript.json (JSON, SRT or VTT)"
            className="flex-1 rounded border border-neutral-300 dark:border-neutral-700 bg-transparent px-2 py-1 text-sm"
          />
          <button type="submit" data-testid="transcript-import-submit" disabled={busy || !path.trim()} className={BUTTON}>
            {busy ? 'Importing…' : 'Import'}
          </button>
        </form>
      )}
      {error && <p data-testid="transcript-error" className="text-xs text-red-600">{error}</p>}
    </div>
  )
}
