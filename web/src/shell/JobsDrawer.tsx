import { useEffect, useState } from 'react'
import { jobTitle } from '../store/jobEvents'
import { useJobsStore } from '../store/jobsStore'
import { cancelJob } from './api'

interface Props {
  pid: string
}

const RESOLVED_KINDS = new Set(['result', 'ok', 'failed'])

/** T30e: each job's exact prompt text (backend records `prompt` events -- see
 * `packages/post_core/post_core/workers/contract.py`'s `EVENT_KINDS["prompt"]`, kept sticky
 * per job in `jobsStore` across later events) and a Cancel button (`POST .../queue/{job_id}/
 * cancel`, already backing `post queue cancel`). Cancel only shows while a job still looks
 * live -- once it has resolved (`result`/`ok`/`failed`), the backend itself rejects a cancel
 * with 400 anyway. T35: what each job is doing now (its step label, upload %), its cost and
 * how it ended -- e.g. a transcription's "Uploading the audio to Deepgram 40%". */
export function JobsDrawer({ pid }: Props) {
  const [open, setOpen] = useState(false)
  const [cancelling, setCancelling] = useState<string | null>(null)
  const connect = useJobsStore((s) => s.connect)
  const disconnect = useJobsStore((s) => s.disconnect)
  const jobsById = useJobsStore((s) => s.jobsById)

  useEffect(() => {
    connect(pid)
    return () => disconnect()
  }, [pid, connect, disconnect])

  const jobs = [...jobsById.values()].sort((a, b) => b.at - a.at) // latest activity first

  async function handleCancel(jobId: string) {
    setCancelling(jobId)
    try {
      await cancelJob(pid, jobId)
    } catch {
      // The backend already refuses a cancel on a job that isn't live (400) -- nothing more
      // to do here than let the button re-enable.
    } finally {
      setCancelling(null)
    }
  }

  return (
    <div className="border-l border-neutral-200 dark:border-neutral-800 flex flex-col">
      <button
        type="button"
        data-testid="jobs-drawer-toggle"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center justify-between gap-2 px-3 py-1.5 text-left w-56"
      >
        <span>Jobs</span>
      </button>
      {open && (
        <div data-testid="jobs-drawer" className="w-56 flex-1 overflow-y-auto border-t border-neutral-200 dark:border-neutral-800">
          {jobs.length === 0 && <p className="px-3 py-2 text-neutral-500">No jobs yet.</p>}
          {jobs.map((j) => {
            const resolved = j.result !== undefined || RESOLVED_KINDS.has(j.kind)
            return (
              <div key={j.job_id} data-testid="job-row" data-job-id={j.job_id}
                className="px-3 py-1.5 border-b border-neutral-100 dark:border-neutral-900 space-y-1">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-medium">{jobTitle(j)}</span>
                  <span className="font-mono text-[11px] text-neutral-500">{j.job_id.slice(0, 8)}</span>
                </div>
                {j.label && !resolved && <div data-testid="job-label">{j.label}</div>}
                {j.percent !== undefined && !resolved && (
                  <div data-testid="job-progress" className="flex items-center gap-2">
                    <div className="h-1 flex-1 rounded bg-neutral-200 dark:bg-neutral-800">
                      <div className="h-1 rounded bg-blue-600" style={{ width: `${j.percent}%` }} />
                    </div>
                    <span>{j.percent}%</span>
                  </div>
                )}
                {j.cost && <div data-testid="job-cost">{j.cost.amount.toFixed(2)} {j.cost.unit}</div>}
                {j.result && (
                  <div data-testid="job-result" className={j.result.ok ? 'text-neutral-500' : 'text-red-600'}>
                    {j.result.detail || (j.result.ok ? 'Done' : 'Failed')}
                  </div>
                )}
                {j.promptText && (
                  <div data-testid="job-prompt-text" className="text-neutral-500 italic">
                    “{j.promptText}”{j.promptModel ? ` (${j.promptModel})` : ''}
                  </div>
                )}
                {!resolved && (
                  <button
                    type="button"
                    data-testid="job-cancel"
                    disabled={cancelling === j.job_id}
                    onClick={() => void handleCancel(j.job_id)}
                    className="text-red-600 disabled:opacity-50"
                  >
                    {cancelling === j.job_id ? 'Cancelling…' : 'Cancel'}
                  </button>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
