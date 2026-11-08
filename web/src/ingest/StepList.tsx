import { STATUS_TEXT, type IngestStep, type StepStatus } from './steps'

const DOT: Record<StepStatus, string> = {
  pending: 'bg-neutral-300 dark:bg-neutral-700',
  running: 'bg-sky-500 animate-pulse',
  done: 'bg-emerald-600',
  skipped: 'bg-emerald-600/50',
  failed: 'bg-red-600',
}

/** T34: the ingest job's steps as they happen -- one row each, a bar while the audio is being
 * extracted, and a failure's own plain sentence under the step that failed. */
export function StepList({ steps }: { steps: IngestStep[] }) {
  if (steps.length === 0) return null
  return (
    <ol data-testid="ingest-steps" className="space-y-1.5">
      {steps.map((s) => (
        <li key={s.step} data-testid="ingest-step" data-step={s.step} data-status={s.status} className="text-sm">
          <div className="flex items-center gap-2">
            <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${DOT[s.status]}`} aria-hidden />
            <span className="flex-1 min-w-0 truncate">{s.label}</span>
            <span className={`text-xs ${s.status === 'failed' ? 'text-red-600' : 'text-neutral-500'}`}>
              {s.status === 'running' && s.percent !== null ? `${s.percent}%` : STATUS_TEXT[s.status]}
            </span>
          </div>
          {s.status === 'running' && s.percent !== null && (
            <div className="ml-4 mt-1 h-1 rounded bg-neutral-200 dark:bg-neutral-800" role="progressbar" aria-valuenow={s.percent}>
              <div className="h-1 rounded bg-sky-500" style={{ width: `${s.percent}%` }} />
            </div>
          )}
          {s.error && (
            <p data-testid="ingest-step-error" className="ml-4 mt-1 text-xs text-red-600">
              {s.error}
            </p>
          )}
        </li>
      ))}
    </ol>
  )
}
