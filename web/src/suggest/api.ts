import { api } from '../api/client'
import type { AcceptAllResult, AcceptSuggestionResult, VisualSuggestion } from '../api/types'

export type SuggestScope =
  | { kind: 'cut' }
  | { kind: 'selection'; syncGroupId: string; startWordId: string; endWordId: string }

/** T13b: thin wrappers over `/api/projects/{pid}/cuts/{cut_id}/suggested-visuals` -- one
 * function per server operation, so `useSuggestions.ts` never spells out the fetch client. */

export async function fetchPendingSuggestions(pid: string, cutId: string): Promise<VisualSuggestion[]> {
  const { data } = await api.GET('/api/projects/{pid}/cuts/{cut_id}/suggested-visuals', {
    params: { path: { pid, cut_id: cutId } },
  })
  return data?.items ?? []
}

export async function requestSuggestVisuals(pid: string, cutId: string, scope: SuggestScope): Promise<VisualSuggestion[]> {
  const body =
    scope.kind === 'cut'
      ? { scope: 'cut' as const }
      : {
          scope: 'selection' as const,
          sync_group_id: scope.syncGroupId,
          start_word_id: scope.startWordId,
          end_word_id: scope.endWordId,
        }
  const { data, error, response } = await api.POST('/api/projects/{pid}/cuts/{cut_id}/suggested-visuals', {
    params: { path: { pid, cut_id: cutId } },
    body,
  })
  if (error || !data) {
    // T36: in real mode a terminal agent answers; when it is missing, times out or replies
    // with garbage the server says why (502 `{error, reason}`) -- surface that sentence.
    const payload = (error ?? {}) as { error?: unknown; detail?: unknown }
    const message = typeof payload.error === 'string' ? payload.error : typeof payload.detail === 'string' ? payload.detail : null
    throw new Error(message ?? `Suggest visuals failed (${response.status})`)
  }
  return data.items
}

export async function acceptSuggestion(pid: string, cutId: string, suggestionId: string): Promise<AcceptSuggestionResult | null> {
  const { data } = await api.POST('/api/projects/{pid}/cuts/{cut_id}/suggested-visuals/{suggestion_id}/accept', {
    params: { path: { pid, cut_id: cutId, suggestion_id: suggestionId } },
  })
  return data ?? null
}

export async function dismissSuggestion(pid: string, cutId: string, suggestionId: string): Promise<void> {
  await api.POST('/api/projects/{pid}/cuts/{cut_id}/suggested-visuals/{suggestion_id}/dismiss', {
    params: { path: { pid, cut_id: cutId, suggestion_id: suggestionId } },
  })
}

export async function acceptAllSuggestions(pid: string, cutId: string): Promise<AcceptAllResult | null> {
  const { data } = await api.POST('/api/projects/{pid}/cuts/{cut_id}/suggested-visuals/accept-all', {
    params: { path: { pid, cut_id: cutId } },
  })
  return data ?? null
}

/** T40: the fields a proposed card can edit before it is accepted. `medium: null` = overlay only. */
export interface SuggestionEdits {
  brief?: string
  direction_note?: string
  medium?: 'aroll' | 'provided' | 'live_action' | 'motion_graphic' | null
}

export async function patchSuggestion(pid: string, cutId: string, suggestionId: string, edits: SuggestionEdits): Promise<VisualSuggestion> {
  const { data, error, response } = await api.PATCH('/api/projects/{pid}/cuts/{cut_id}/suggested-visuals/{suggestion_id}', {
    params: { path: { pid, cut_id: cutId, suggestion_id: suggestionId } },
    body: edits,
  })
  if (error || !data) {
    const payload = (error ?? {}) as { error?: unknown; detail?: unknown }
    const message = typeof payload.error === 'string' ? payload.error : typeof payload.detail === 'string' ? payload.detail : null
    throw new Error(message ?? `Saving the suggestion failed (${response.status})`)
  }
  return data
}

/** T42: make another of the proposal's ideas ("Variant A", "Variant B", ...) the active one. */
export async function switchSuggestionVariant(pid: string, cutId: string, suggestionId: string, index: number): Promise<VisualSuggestion> {
  const { data, error, response } = await api.POST('/api/projects/{pid}/cuts/{cut_id}/suggested-visuals/{suggestion_id}/variant', {
    params: { path: { pid, cut_id: cutId, suggestion_id: suggestionId } },
    body: { index },
  })
  if (error || !data) {
    const payload = (error ?? {}) as { error?: unknown; detail?: unknown }
    const message = typeof payload.error === 'string' ? payload.error : typeof payload.detail === 'string' ? payload.detail : null
    throw new Error(message ?? `Switching the variant failed (${response.status})`)
  }
  return data
}
