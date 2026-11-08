import { stateText } from '../graphMeta'
import type { NodeStatus } from '../types'

// T29 item 4: colours only -- the labels themselves come from `graphMeta.stateText`, the
// same plain words the graph view's node pills use, so a card and its graph never disagree
// about what "stale" or "needs_approval" means in English.
const STATE_CLASS: Record<string, string> = {
  unresolved: 'bg-neutral-200 text-neutral-600', blocked: 'bg-neutral-200 text-neutral-600',
  ready: 'bg-blue-100 text-blue-700', done: 'bg-emerald-100 text-emerald-700',
  stale: 'bg-amber-100 text-amber-700', needs_pick: 'bg-violet-100 text-violet-700',
  needs_approval: 'bg-violet-100 text-violet-700', failed: 'bg-red-100 text-red-700',
}

export function StateBadge({ typeId, state, failCause }: { typeId: string; state: NodeStatus['state']; failCause?: string | null }) {
  return (
    <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${STATE_CLASS[state] ?? 'bg-neutral-200'}`}>
      {stateText(typeId, state, failCause)}
    </span>
  )
}
