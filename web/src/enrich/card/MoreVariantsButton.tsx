import * as enrichApi from '../api'
import { EnrichApiError } from '../api'

/** T30b/T30c: "+3 more" -- grows a `live_action` card's still batch with a second
 * `still.generate` node group sharing the existing `human.pick` (`/workflow/more-variants`).
 * Only offered once the first batch has already picked -- adding more variants before a pick
 * exists is just "Generate" again. */
export function MoreVariantsButton({
  pid, cutId, spanId, busy, onAdded,
}: {
  pid: string
  cutId: string
  spanId: string
  busy: boolean
  onAdded: () => void
}) {
  async function onClick() {
    try {
      await enrichApi.moreVariants(pid, cutId, spanId, 3)
      onAdded()
    } catch (err) {
      window.alert(err instanceof EnrichApiError ? err.message : 'Could not add more variants.')
    }
  }

  return (
    <button type="button" data-testid="enrich-more-variants" className="underline text-neutral-500" disabled={busy} onClick={() => void onClick()}>
      +3 more
    </button>
  )
}
