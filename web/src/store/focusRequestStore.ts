import { create } from 'zustand'

export interface FocusRequest {
  spanId: string
}

interface FocusRequestState {
  request: FocusRequest | null
  requestFocus: (req: FocusRequest) => void
  clearFocusRequest: () => void
}

/** T30e: lets the top-bar Decisions panel (`shell/DecisionsBar.tsx`, mounted at the Shell
 * level, a sibling of the edit route's own `Outlet`) tell `RawTranscript` -- deep inside that
 * `Outlet` -- to focus/highlight one beat's card in the transcript rail. Opening that beat's
 * graph is a separate, workspace-level concern now (`graphPanelStore`), callable directly
 * from wherever a node-level decision is clicked; this store only carries the "which card"
 * part, which still has to reach `RawTranscript`'s own local `focusedSpanId` state. */
export const useFocusRequestStore = create<FocusRequestState>((set) => ({
  request: null,
  requestFocus: (req) => set({ request: req }),
  clearFocusRequest: () => set({ request: null }),
}))
