import { formatEstimate } from '../enrich/spend'
import { useProvidersStore } from '../store/providersStore'
import { useSpendConfirmStore } from '../store/spendConfirmStore'

/** T31: the one confirm every spending run waits on (`spendConfirmStore`). Shows exactly what
 * the click will spend; Confirm creates a budget capped at that amount, Cancel spends nothing.
 * Rendered once in the shell, above the full-screen graph panel (z-50). */
export function SpendConfirmDialog() {
  const pending = useSpendConfirmStore((s) => s.pending)
  const settle = useSpendConfirmStore((s) => s.settle)
  const mode = useProvidersStore((s) => s.mode)
  if (!pending) return null
  const { summary } = pending
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/30" data-testid="spend-confirm">
      <div role="dialog" aria-label="Confirm spend" className="w-96 rounded border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4 shadow-lg space-y-3 text-sm">
        <p className="font-medium" data-testid="spend-confirm-title">{summary.title ?? `Generate ${summary.label}?`}</p>
        <p data-testid="spend-confirm-estimate">{formatEstimate(summary)}</p>
        <p className="text-xs text-neutral-500">
          {mode === 'fake'
            ? 'Fake providers: placeholder media, nothing is actually spent.'
            : `This click gets its own budget of exactly ${summary.amount.toFixed(2)} ${summary.unit}; nothing past it can run.`}
        </p>
        <div className="flex justify-end gap-3">
          <button type="button" className="underline" data-testid="spend-confirm-cancel" onClick={() => settle(false)}>
            Cancel
          </button>
          <button type="button" className="px-2 py-1 rounded bg-blue-600 text-white" data-testid="spend-confirm-ok" onClick={() => settle(true)}>
            Confirm
          </button>
        </div>
      </div>
    </div>
  )
}
