import { useEffect } from 'react'
import { useProvidersStore } from '../store/providersStore'
import { getDoctor } from './api'

/** T31/T41: asks `GET /api/doctor` once whether the backend runs real providers and keeps the
 * answer in `providersStore` (the spend confirm reads it). T41 dropped the header's "REAL: spends
 * credits" badge: the mode stays in the doctor response and the startup log, and spending is
 * still gated by the cost confirm. */
export function useProvidersMode() {
  const setMode = useProvidersStore((s) => s.setMode)
  useEffect(() => {
    getDoctor()
      .then((d) => setMode(d.providers === 'real' ? 'real' : d.providers === 'fake' ? 'fake' : 'unknown'))
      .catch(() => setMode('unknown'))
  }, [setMode])
}
