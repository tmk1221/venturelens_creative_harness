import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { VisualSuggestion } from '../api/types'
import { fetchPendingSuggestions, requestSuggestVisuals } from './api'
import { useSuggestions } from './useSuggestions'

/** T36: a failed real-mode run (terminal agent missing, timed out, bad reply) says why and
 * leaves the pending proposals exactly as they were. */
vi.mock('./api', () => ({
  fetchPendingSuggestions: vi.fn(),
  requestSuggestVisuals: vi.fn(),
  acceptSuggestion: vi.fn(),
  dismissSuggestion: vi.fn(),
  acceptAllSuggestions: vi.fn(),
  patchSuggestion: vi.fn(),
}))

const pending = { id: 's1', brief: 'A woman searching on her phone' } as VisualSuggestion

beforeEach(() => {
  vi.mocked(fetchPendingSuggestions).mockReset().mockResolvedValue([pending])
  vi.mocked(requestSuggestVisuals).mockReset()
})

describe('useSuggestions', () => {
  it('keeps pending proposals and exposes the reason when a run fails', async () => {
    const reason = 'suggest_visuals (claude / CLI default) timed out after 420 s; the agent was stopped'
    vi.mocked(requestSuggestVisuals).mockRejectedValue(new Error(reason))
    const { result } = renderHook(() => useSuggestions('p1', 'c1', () => {}))
    await waitFor(() => expect(result.current.suggestions).toEqual([pending]))
    await act(() => result.current.suggest({ kind: 'cut' }))
    expect(result.current.error).toBe(reason)
    expect(result.current.suggestions).toEqual([pending])
    expect(result.current.running).toBe(false)
  })

  it('clears the reason on the next successful run', async () => {
    vi.mocked(requestSuggestVisuals).mockRejectedValueOnce(new Error('claude CLI not found')).mockResolvedValueOnce([])
    const { result } = renderHook(() => useSuggestions('p1', 'c1', () => {}))
    await act(() => result.current.suggest({ kind: 'cut' }))
    expect(result.current.error).toBe('claude CLI not found')
    await act(() => result.current.suggest({ kind: 'cut' }))
    expect(result.current.error).toBeNull()
    expect(result.current.suggestions).toEqual([])
  })
})
