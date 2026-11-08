import type { Page, Route } from '@playwright/test'
import fixture from './fixtures/basic.json' with { type: 'json' }

export const pid = fixture.pid
export const cutId = fixture.cut_id

type PassageT = (typeof fixture.cut.cut.passages)[number]

const words = fixture.words.words
const origPassage = fixture.cut.cut.passages[0]!

function idxOf(wordId: string): number {
  return words.findIndex((w) => w.id === wordId)
}

/** Turn a display-order list of source-word indices into passages: each maximal run of
 * consecutive-ascending indices becomes one passage (this is a simplified stand-in for what
 * `delete_words`/`move_words`/`replace_range_with` do server-side -- good enough to drive the
 * UI through a real reorder without a live post_api process). */
function passagesFromOrder(order: number[]): PassageT[] {
  const out: PassageT[] = []
  let runStart = 0
  for (let i = 1; i <= order.length; i++) {
    if (i === order.length || order[i] !== order[i - 1]! + 1) {
      const idxs = order.slice(runStart, i)
      out.push({
        ...origPassage,
        id: `seg-${idxs[0]}-${idxs[idxs.length - 1]}`,
        start_word_id: words[idxs[0]!]!.id,
        end_word_id: words[idxs[idxs.length - 1]!]!.id,
      })
      runStart = i
    }
  }
  return out
}

export function freshState() {
  return {
    order: words.map((_, i) => i),
    revision: fixture.cut.revision,
    timeline: structuredClone(fixture.timeline),
    revisionHistory: [] as number[][],
    redoStack: [] as number[][],
    forceConflictOnce: false,
    derived: null as null | { id: string; cut: typeof fixture.cut.cut; revision: number },
  }
}
type State = ReturnType<typeof freshState>

function currentCut(state: State): typeof fixture.cut.cut {
  return { ...fixture.cut.cut, passages: passagesFromOrder(state.order) }
}

function applyDelete(state: State, args: Record<string, unknown>) {
  const s = idxOf(args.start_word_id as string)
  const e = idxOf(args.end_word_id as string)
  state.order = state.order.filter((i) => i < s || i > e)
}

function applyRestore(state: State) {
  // Simplified: the fixture only ever exercises "delete then restore" in one gesture, so
  // restoring puts every word back in source order.
  state.order = words.map((_, i) => i)
}

function applyMove(state: State, args: Record<string, unknown>) {
  const s = idxOf(args.start_word_id as string)
  const e = idxOf(args.end_word_id as string)
  const moving = state.order.filter((i) => i >= s && i <= e)
  const rest = state.order.filter((i) => i < s || i > e)
  const before = args.before_word as { word_id: string } | null | undefined
  if (!before) {
    state.order = [...rest, ...moving]
    return
  }
  const targetIdx = idxOf(before.word_id)
  const insertAt = rest.findIndex((i) => i === targetIdx)
  if (insertAt === -1) {
    state.order = [...rest, ...moving]
  } else {
    state.order = [...rest.slice(0, insertAt), ...moving, ...rest.slice(insertAt)]
  }
}

function applyReplace(state: State, args: Record<string, unknown>) {
  const s = idxOf(args.start_word_id as string)
  const e = idxOf(args.end_word_id as string)
  const os = idxOf(args.other_start_word_id as string)
  const oe = idxOf(args.other_end_word_id as string)
  const replacement: number[] = []
  for (let i = os; i <= oe && replacement.length <= e - s; i++) replacement.push(i)
  const sPos = state.order.findIndex((i) => i === s)
  if (sPos === -1) return
  const count = e - s + 1
  state.order.splice(sPos, count, ...replacement)
}

/** A candidate offered by "Swap take": a different word range in the same fixture, so the
 * flow (open menu, pick a candidate, apply `replace_range_with`) is exercised end to end. */
function swapCandidateFor(startWordId: string, endWordId: string) {
  const s = idxOf(startWordId)
  const e = idxOf(endWordId)
  const len = e - s + 1
  const altStart = s === 0 ? words.length - len : 0
  const altEnd = altStart + len - 1
  return {
    sync_group_id: origPassage.sync_group_id,
    start_word_id: words[altStart]!.id,
    end_word_id: words[altEnd]!.id,
    text: words.slice(altStart, altEnd + 1).map((w) => w.text).join(' '),
    score: 0.82,
  }
}

/** Wires every `/api/**` request this app makes to the committed fixture (generated from
 * real post_core/post_api output -- see `packages/post_api/tests/fixtures/gen_e2e_fixture.py`),
 * with a small stateful `ops`/`undo`/`redo`/`derive` so the transcript flows (delete, restore,
 * move, swap take, derive, 409, undo/redo) can be exercised without a real post_api process.
 * One route handler, dispatched by parsed path, so match precedence between overlapping glob
 * patterns is never a question. */
export async function mockApi(page: Page) {
  const state = freshState()

  await page.route('**/api/**', async (route: Route) => {
    const req = route.request()
    const url = new URL(req.url())
    const path = url.pathname
    const method = req.method()

    if (path === '/api/projects' && method === 'GET') return route.fulfill({ json: fixture.projects })
    if (path === `/api/projects/${pid}/shoots`) return route.fulfill({ json: fixture.shoots })
    if (path === `/api/projects/${pid}/transcripts/${fixture.transcript_id}/words`) return route.fulfill({ json: fixture.words })
    if (path === `/api/projects/${pid}/transcripts/${fixture.transcript_id}/suggestions`) return route.fulfill({ json: fixture.suggestions })
    if (path === `/api/projects/${pid}/transcripts/${fixture.transcript_id}`) return route.fulfill({ json: fixture.transcript })
    if (path === `/api/projects/${pid}/events`) return route.abort()
    if (path.startsWith(`/api/projects/${pid}/media/`)) return route.abort()
    // T30e: the top-bar Decisions view polls this on every mount/job event -- stub it out
    // (empty) so it doesn't fall through to a real network request (there is no post_api
    // process behind this suite) and drag unrelated latency into these tests.
    if (path.match(new RegExp(`^/api/projects/${pid}/cuts/[^/]+/decisions$`)) && method === 'GET') {
      return route.fulfill({ json: { rows: [], counts: { pick: 0, approve: 0, failed: 0, waiting_on: 0 } } })
    }

    if (path === `/api/projects/${pid}/cuts` && method === 'GET') {
      const list = [...fixture.cutList]
      if (state.derived) {
        list.push({ id: state.derived.id, aspect: state.derived.cut.aspect, variant_label: state.derived.cut.variant_label, parent_cut_id: cutId, passage_count: state.derived.cut.passages.length })
      }
      return route.fulfill({ json: list })
    }

    if (path === `/api/projects/${pid}/cuts/derive` && method === 'POST') {
      const body = req.postDataJSON() as { parent: string; passage_ids: string[]; aspect: string; variant_label?: string }
      const parentPassages = passagesFromOrder(state.order)
      const chosen = parentPassages.filter((p) => body.passage_ids.includes(p.id!))
      const [num, den] = body.aspect.split(':').map(Number)
      const newId = 'derived-cut-1'
      state.derived = {
        id: newId,
        cut: { ...fixture.cut.cut, id: newId, aspect: { num: num || 9, den: den || 16 }, parent_cut_id: cutId, variant_label: body.variant_label || 'short', passages: chosen, spans: [] },
        revision: 1,
      }
      return route.fulfill({ json: { cut_id: newId, parent_cut_id: body.parent, report: { affected_spans: [], orphaned_spans: [] } } })
    }

    const cutMatch = path.match(new RegExp(`^/api/projects/${pid}/cuts/([^/]+)(/.*)?$`))
    if (cutMatch) {
      const targetId = cutMatch[1]!
      const sub = cutMatch[2] ?? ''
      const isDerived = state.derived?.id === targetId

      if (targetId === cutId && sub === '/swap-candidates' && method === 'GET') {
        const q = url.searchParams
        const c = swapCandidateFor(q.get('start_word_id')!, q.get('end_word_id')!)
        return route.fulfill({ json: [c] })
      }

      if (isDerived && sub === '') return route.fulfill({ json: { revision: state.derived!.revision, cut: state.derived!.cut } })
      if (isDerived && sub === '/timeline') return route.fulfill({ json: [] })

      if (targetId === cutId && sub === '') return route.fulfill({ json: { revision: state.revision, cut: currentCut(state) } })
      if (targetId === cutId && sub === '/timeline') return route.fulfill({ json: state.timeline })

      if (targetId === cutId && sub === '/ops' && method === 'POST') {
        const body = req.postDataJSON() as { name: string; args: Record<string, unknown>; expected_rev: number }
        if (state.forceConflictOnce || body.expected_rev !== state.revision) {
          state.forceConflictOnce = false
          return route.fulfill({ status: 409, json: { detail: 'conflict', current_revision: state.revision } })
        }
        state.revisionHistory.push([...state.order])
        state.redoStack = []
        if (body.name === 'delete_words') applyDelete(state, body.args)
        else if (body.name === 'restore_words') applyRestore(state)
        else if (body.name === 'move_words') applyMove(state, body.args)
        else if (body.name === 'replace_range_with') applyReplace(state, body.args)
        state.revision += 1
        return route.fulfill({ json: { cut_id: cutId, revision: state.revision, report: { affected_spans: [], orphaned_spans: [] } } })
      }

      if (targetId === cutId && sub === '/undo' && method === 'POST') {
        const prev = state.revisionHistory.pop()
        if (prev) {
          state.redoStack.push([...state.order])
          state.order = prev
          state.revision += 1
        }
        return route.fulfill({ json: { cut_id: cutId } })
      }
      if (targetId === cutId && sub === '/redo' && method === 'POST') {
        const next = state.redoStack.pop()
        if (next) {
          state.revisionHistory.push([...state.order])
          state.order = next
          state.revision += 1
        }
        return route.fulfill({ json: { cut_id: cutId } })
      }
    }

    return route.continue()
  })

  return state
}
