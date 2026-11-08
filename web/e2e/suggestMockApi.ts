import type { Page, Route } from '@playwright/test'
import { pid, cutId } from './rawTranscriptMockApi'

/** T13b: layered on top of `mockRawTranscriptApi` -- that fixture's own `**\/api/**` handler
 * `route.continue()`s anything it doesn't recognise, and Playwright runs the most-recently
 * registered matching route first, so registering this AFTER `mockRawTranscriptApi(page)`
 * is enough to intercept `.../suggested-visuals...` without touching that file. Two
 * deterministic proposals over the fixture's 12-word vocab ("So today we are going to talk
 * about the launch plan now"), independent word ranges so accept/dismiss/accept-all are each
 * exercisable without one blocking the other. */
const proposal = { transcript_id: 'tr-rt', overlay_depth: null, overlay_position: null, direction_note: '', flags: [], cast_refs: [], density_hint: null, variants: [], active_variant: 0 }

/** `cutState` (what `mockRawTranscriptApi` returns): when given, accept lands a real picture span
 * on the mocked cut carrying the suggestion's (possibly edited) brief, like the server does. */
export async function mockSuggestApi(
  page: Page,
  cutState?: { revision: number; spans: Record<string, unknown>[] },
  /** T41: replace the two default proposals (e.g. with `overlapProposals`). */
  pending?: Record<string, unknown>[],
) {
  const state = {
    pending: pending ?? [
      { ...proposal, id: 'sugg-1', start_word_id: 'w1', end_word_id: 'w3', medium: 'live_action', brief: 'Show the calendar.', rationale: 'Names a concrete date.' },
      { ...proposal, id: 'sugg-2', start_word_id: 'w8', end_word_id: 'w10', medium: 'motion_graphic', brief: 'Show the launch plan diagram.', rationale: 'Names the launch plan.' },
    ] as Record<string, unknown>[],
    dismissed: new Set<string>(),
    /** T40: set to make the next suggest run wait (ms) so the spinner/placeholder can be seen. */
    suggestDelayMs: 0,
    /** T40: set to make the next suggest run fail with this reason (502, like a missing agent). */
    failWith: null as string | null,
  }

  await page.route('**/suggested-visuals**', async (route: Route) => {
    const req = route.request()
    const url = new URL(req.url())
    const path = url.pathname
    const method = req.method()
    const base = `/api/projects/${pid}/cuts/${cutId}/suggested-visuals`

    if (path === base && method === 'GET') return route.fulfill({ json: { items: state.pending } })
    if (path === base && method === 'POST') {
      if (state.suggestDelayMs) await new Promise((r) => setTimeout(r, state.suggestDelayMs))
      if (state.failWith) return route.fulfill({ status: 502, json: { error: state.failWith, reason: 'agent_missing' } })
      return route.fulfill({ json: { items: state.pending } })
    }

    const itemMatch = path.match(new RegExp(`^${base}/([^/]+)$`))
    if (itemMatch && method === 'PATCH') {
      const id = itemMatch[1]!
      const edits = req.postDataJSON() as Record<string, unknown>
      state.pending = state.pending.map((s) => (s.id === id ? { ...s, ...edits } : s))
      return route.fulfill({ json: state.pending.find((s) => s.id === id) })
    }

    // T42: switch a proposal to another of its variants (the server swaps the idea fields in).
    const variantMatch = path.match(new RegExp(`^${base}/([^/]+)/variant$`))
    if (variantMatch && method === 'POST') {
      const id = variantMatch[1]!
      const { index } = req.postDataJSON() as { index: number }
      state.pending = state.pending.map((s) => {
        if (s.id !== id) return s
        const variants = s.variants as Record<string, unknown>[]
        return { ...s, ...variants[index], active_variant: index }
      })
      return route.fulfill({ json: state.pending.find((s) => s.id === id) })
    }

    if (path === `${base}/accept-all` && method === 'POST') {
      const accepted = state.pending.map((s) => s.id as string)
      state.pending = []
      return route.fulfill({ json: { accepted, blocked: [] } })
    }

    const acceptMatch = path.match(new RegExp(`^${base}/([^/]+)/accept$`))
    if (acceptMatch && method === 'POST') {
      const id = acceptMatch[1]!
      const found = state.pending.find((s) => s.id === id)
      state.pending = state.pending.filter((s) => s.id !== id)
      if (cutState && found) {
        cutState.spans.push({
          id: `span-from-${id}`, schema_version: 1, layer: 'picture', kind: found.medium, orphaned: false, provenance: 'agent', note: '',
          direction_note: found.direction_note, flags: [], brief: { text: found.brief, provenance: 'agent' },
          start_anchor: { transcript_id: 'tr-rt', word_id: found.start_word_id },
          end_anchor: { transcript_id: 'tr-rt', word_id: found.end_word_id },
        })
        cutState.revision += 1
      }
      return route.fulfill({ json: { cut_id: cutId, revision: 2, span_id: `span-from-${id}` } })
    }

    const dismissMatch = path.match(new RegExp(`^${base}/([^/]+)/dismiss$`))
    if (dismissMatch && method === 'POST') {
      const id = dismissMatch[1]!
      const found = state.pending.find((s) => s.id === id)
      state.pending = state.pending.filter((s) => s.id !== id)
      state.dismissed.add(id)
      return route.fulfill({ json: found ?? {} })
    }

    return route.continue()
  })

  return state
}
