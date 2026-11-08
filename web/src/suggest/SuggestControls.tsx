import { useState } from 'react'
import type { SuggestScope } from './api'
import './suggest.css'

interface Props {
  running: boolean
  error: string | null
  pendingCount: number
  /** Current word selection, if any -- "Suggest visuals" then targets just the selection. */
  selection: { syncGroupId: string; startWordId: string; endWordId: string } | null
  suggest: (scope: SuggestScope) => Promise<void>
  acceptAll: () => Promise<{ accepted: number; blocked: number }>
}

/** T40: "Suggest visuals" and "Accept all", moved from a floating strip over the transcript
 * (which covered the "Read the story…" hint) into the Visuals rail header. */
export function SuggestControls({ running, error, pendingCount, selection, suggest, acceptAll }: Props) {
  const [note, setNote] = useState<string | null>(null)

  async function handleAcceptAll() {
    const { accepted, blocked } = await acceptAll()
    setNote(blocked > 0 ? `Accepted ${accepted}, skipped ${blocked} blocked` : `Accepted ${accepted}`)
    window.setTimeout(() => setNote(null), 4000)
  }

  return (
    <div className="suggest-controls" data-testid="suggest-controls">
      <button
        type="button"
        className="suggest-trigger"
        data-testid="suggest-visuals-button"
        disabled={running}
        aria-busy={running}
        onClick={() =>
          void suggest(
            selection
              ? { kind: 'selection', syncGroupId: selection.syncGroupId, startWordId: selection.startWordId, endWordId: selection.endWordId }
              : { kind: 'cut' },
          )
        }
      >
        {running && <span className="suggest-spinner" data-testid="suggest-spinner" aria-hidden="true" />}
        {running ? 'Suggesting visuals… (~20 s)' : selection ? 'Suggest visuals (selection)' : 'Suggest visuals'}
      </button>
      {pendingCount > 0 && (
        <button type="button" className="suggest-accept-all" data-testid="accept-all-visuals" onClick={() => void handleAcceptAll()}>
          Accept all ({pendingCount})
        </button>
      )}
      {note && <span className="suggest-note" data-testid="accept-all-note">{note}</span>}
      {error && (
        <span className="suggest-error" data-testid="suggest-error" role="alert">
          {error}
        </span>
      )}
    </div>
  )
}
