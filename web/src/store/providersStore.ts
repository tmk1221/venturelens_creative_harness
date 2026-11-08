import { create } from 'zustand'

/** T31: `GET /api/doctor`'s `providers` -- `real` means generation calls paid providers.
 * `unknown` until the shell's `useProvidersMode` has asked (and if the backend is down). */
export type ProvidersMode = 'fake' | 'real' | 'unknown'

export const useProvidersStore = create<{ mode: ProvidersMode; setMode: (mode: ProvidersMode) => void }>((set) => ({
  mode: 'unknown',
  setMode: (mode) => set({ mode }),
}))
