import type { Suggestion } from '../../api/types'
import { useCutStore } from '../../store/cutStore'

interface Props {
  suggestions: Suggestion[]
}

export function SuggestionsBar({ suggestions }: Props) {
  const applyOp = useCutStore((s) => s.applyOp)

  if (suggestions.length === 0) return null

  async function acceptAll() {
    for (const s of suggestions) {
      // eslint-disable-next-line no-await-in-loop -- ops must land in order, each against the latest revision
      await applyOp('delete_words', { sync_group_id: s.sync_group_id, start_word_id: s.start_word_id, end_word_id: s.end_word_id })
    }
  }

  return (
    <div data-testid="suggestions-bar" className="flex items-center gap-2 border-b border-neutral-200 dark:border-neutral-800 px-3 py-1 text-amber-700 dark:text-amber-400">
      <span>{suggestions.length} suggestion(s)</span>
      <button type="button" data-testid="accept-all-suggestions" className="underline" onClick={() => void acceptAll()}>
        Accept all
      </button>
      {suggestions.map((s) => (
        <span
          key={`${s.sync_group_id}-${s.start_word_id}`}
          data-testid="suggestion-mark"
          className="border border-dashed border-amber-500 rounded px-1 cursor-pointer"
          title={s.reason}
          onClick={() => void applyOp('delete_words', { sync_group_id: s.sync_group_id, start_word_id: s.start_word_id, end_word_id: s.end_word_id })}
        >
          {s.kind}
        </span>
      ))}
    </div>
  )
}
