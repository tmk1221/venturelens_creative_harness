import { create } from 'zustand'
import type { SpendSummary } from '../enrich/spend'

interface SpendConfirmState {
  pending: { summary: SpendSummary; resolve: (ok: boolean) => void } | null
  /** Show the one shell-level confirm and resolve true on Confirm, false on Cancel. A new
   * request while one is open cancels the older one -- never two spends queued behind one click. */
  request: (summary: SpendSummary) => Promise<boolean>
  settle: (ok: boolean) => void
}

/** T31: the single "≈ X credits — Confirm" gate every web run goes through (`enrich/spend.ts`
 * `runWithSpendConfirm`, wired in `useWorkflow.run`), rendered once by `SpendConfirmDialog` in
 * the shell -- so a card's Generate/Pick/Regenerate and the graph's "run from here" can't
 * bypass it by forgetting their own confirm UI. */
export const useSpendConfirmStore = create<SpendConfirmState>((set, get) => ({
  pending: null,
  request: (summary) =>
    new Promise<boolean>((resolve) => {
      get().pending?.resolve(false)
      set({ pending: { summary, resolve } })
    }),
  settle: (ok) => {
    const pending = get().pending
    set({ pending: null })
    pending?.resolve(ok)
  },
}))
