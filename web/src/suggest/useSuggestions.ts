import { useCallback, useEffect, useState } from 'react'
import type { VisualSuggestion } from '../api/types'
import {
  acceptAllSuggestions,
  acceptSuggestion,
  dismissSuggestion,
  fetchPendingSuggestions,
  patchSuggestion,
  requestSuggestVisuals,
  switchSuggestionVariant,
  type SuggestionEdits,
  type SuggestScope,
} from './api'

interface UseSuggestionsResult {
  suggestions: VisualSuggestion[]
  running: boolean
  /** Why the last "Suggest visuals" run failed (agent missing, timed out, bad reply), if it did. */
  error: string | null
  suggest: (scope: SuggestScope) => Promise<void>
  accept: (id: string) => Promise<void>
  dismiss: (id: string) => Promise<void>
  /** T40: persist inline edits from a proposed card; rejects (list unchanged) if refused. */
  update: (id: string, edits: SuggestionEdits) => Promise<void>
  acceptAll: () => Promise<{ accepted: number; blocked: number }>
  /** T42: switch a proposal to another of its variants. */
  switchVariant: (id: string, index: number) => Promise<void>
}

/** T13b: owns the pending-suggestions list for one cut and every action on it (generate,
 * accept, dismiss, accept-all), refreshing the shared cut store after any op that lands a
 * real span so the rest of the app (VisualsRail's cards) picks it up through its normal
 * path -- this hook never touches cut/span state directly. */
export function useSuggestions(pid: string | null, cutId: string | null, onAccepted: () => void): UseSuggestionsResult {
  const [suggestions, setSuggestions] = useState<VisualSuggestion[]>([])
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!pid || !cutId) {
      setSuggestions([])
      return
    }
    let cancelled = false
    void fetchPendingSuggestions(pid, cutId).then((items) => {
      if (!cancelled) setSuggestions(items)
    })
    return () => {
      cancelled = true
    }
  }, [pid, cutId])

  const suggest = useCallback(
    async (scope: SuggestScope) => {
      if (!pid || !cutId) return
      setRunning(true)
      setError(null)
      try {
        const items = await requestSuggestVisuals(pid, cutId, scope)
        setSuggestions(items)
      } catch (e) {
        // Pending proposals stay as they were: a failed run applies nothing.
        setError(e instanceof Error ? e.message : String(e))
      } finally {
        setRunning(false)
      }
    },
    [pid, cutId],
  )

  const accept = useCallback(
    async (id: string) => {
      if (!pid || !cutId) return
      const result = await acceptSuggestion(pid, cutId, id)
      if (result) {
        setSuggestions((prev) => prev.filter((s) => s.id !== id))
        onAccepted()
      }
    },
    [pid, cutId, onAccepted],
  )

  const dismiss = useCallback(
    async (id: string) => {
      if (!pid || !cutId) return
      await dismissSuggestion(pid, cutId, id)
      setSuggestions((prev) => prev.filter((s) => s.id !== id))
    },
    [pid, cutId],
  )

  const update = useCallback(
    async (id: string, edits: SuggestionEdits) => {
      if (!pid || !cutId) return
      const saved = await patchSuggestion(pid, cutId, id, edits)
      setSuggestions((prev) => prev.map((s) => (s.id === id ? saved : s)))
    },
    [pid, cutId],
  )

  const switchVariant = useCallback(
    async (id: string, index: number) => {
      if (!pid || !cutId) return
      const saved = await switchSuggestionVariant(pid, cutId, id, index)
      setSuggestions((prev) => prev.map((s) => (s.id === id ? saved : s)))
    },
    [pid, cutId],
  )

  const acceptAll = useCallback(async () => {
    if (!pid || !cutId) return { accepted: 0, blocked: 0 }
    const result = await acceptAllSuggestions(pid, cutId)
    if (!result) return { accepted: 0, blocked: 0 }
    setSuggestions((prev) => prev.filter((s) => !result.accepted.includes(s.id)))
    if (result.accepted.length > 0) onAccepted()
    return { accepted: result.accepted.length, blocked: result.blocked.length }
  }, [pid, cutId, onAccepted])

  return { suggestions, running, error, suggest, accept, dismiss, update, acceptAll, switchVariant }
}
