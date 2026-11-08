import type { NodeStatus } from '../types'

/** One approve gate: an "Approve" button once `approveNode` is `needs_approval` (see
 * `CardBody.tsx`'s original comment on why it's also gated on `readyNode.state === 'done'` --
 * `human.approve`'s own derived state turns `needs_approval` as soon as its input hash
 * resolves, before the upstream verify/render step it depends on has actually finished).
 * Shared by every recipe's single approve (live_action/overlay/provided) and by
 * `motion_graphic`'s two gates (draft approve, final approve) -- one instance per gate. */
export function ApproveGate({
  approveNode, readyNode, busy, onApprove, testId,
}: {
  approveNode: NodeStatus | undefined
  readyNode: NodeStatus | undefined
  busy: boolean
  onApprove: () => Promise<void>
  testId: string
}) {
  if (!approveNode || approveNode.state !== 'needs_approval' || readyNode?.state !== 'done') return null
  return (
    <div className="flex items-center gap-2">
      <button type="button" data-testid={testId} disabled={busy} className="px-2 py-1 rounded bg-emerald-600 text-white disabled:opacity-50" onClick={() => void onApprove()}>
        Approve
      </button>
    </div>
  )
}
