import { renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useProvidersStore } from '../store/providersStore'
import { getDoctor } from './api'
import { useProvidersMode } from './useProvidersMode'

/** T31/T41: the shell asks `GET /api/doctor` for the providers mode (the spend confirm reads it);
 * nothing is drawn in the header any more. */
vi.mock('./api', () => ({ getDoctor: vi.fn() }))

beforeEach(() => {
  useProvidersStore.setState({ mode: 'unknown' })
})

describe('useProvidersMode', () => {
  it('records fake mode', async () => {
    vi.mocked(getDoctor).mockResolvedValue({ providers: 'fake' })
    renderHook(() => useProvidersMode())
    await waitFor(() => expect(useProvidersStore.getState().mode).toBe('fake'))
  })

  it('records real mode', async () => {
    vi.mocked(getDoctor).mockResolvedValue({ providers: 'real' })
    renderHook(() => useProvidersMode())
    await waitFor(() => expect(useProvidersStore.getState().mode).toBe('real'))
  })

  it('stays unknown when the backend cannot be asked', async () => {
    vi.mocked(getDoctor).mockRejectedValue(new Error('down'))
    renderHook(() => useProvidersMode())
    await waitFor(() => expect(getDoctor).toHaveBeenCalled())
    expect(useProvidersStore.getState().mode).toBe('unknown')
  })
})
