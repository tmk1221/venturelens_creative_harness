import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { IngestStatus } from '../api/types'
import { openEditor } from './api'
import { SourceTranscript } from './SourceTranscript'

const PRIMARY = 'rounded bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900 px-3 py-1.5 text-sm font-medium disabled:opacity-50'

/** T34: once the audio is ready -- get a transcript in (T35: transcribe it, a paid confirmed
 * job, or import a file for free), then "Open editor", which makes the first cut from the
 * transcript if the project has none yet and opens it. */
export function TranscriptActions({ pid, status, onChanged }: { pid: string; status: IngestStatus; onChanged: () => void }) {
  const navigate = useNavigate()
  const [opening, setOpening] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function open() {
    setOpening(true)
    setError(null)
    try {
      const { cut_id } = await openEditor(pid)
      navigate(`/p/${pid}/edit/${cut_id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not open the editor')
      setOpening(false)
    }
  }

  return (
    <section data-testid="transcript-actions" className="space-y-3">
      <h2 className="text-sm font-medium">Transcript</h2>
      {status.sources.map((s) => (
        <SourceTranscript key={s.source_id} pid={pid} source={s} onChanged={onChanged} />
      ))}
      {status.has_transcript && (
        <button type="button" data-testid="open-editor" disabled={opening} onClick={() => void open()} className={PRIMARY}>
          {opening ? 'Opening…' : 'Open editor'}
        </button>
      )}
      {error && <p data-testid="open-editor-error" className="text-xs text-red-600">{error}</p>}
    </section>
  )
}
