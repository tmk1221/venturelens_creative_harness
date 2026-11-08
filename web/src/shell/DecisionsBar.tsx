import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { DecisionRow } from '../api/types'
import { useCutStore } from '../store/cutStore'
import { useFocusRequestStore } from '../store/focusRequestStore'
import { useGraphPanelStore } from '../store/graphPanelStore'
import { useJobsStore } from '../store/jobsStore'
import { getDecisions } from './api'

const KIND_LABEL: Record<string, string> = {
  pick: 'Pick a variant',
  approve: 'Needs approval',
  failed: 'Failed',
  waiting_on: 'Waiting on',
}

/** T30e: the top-bar Decisions view -- renamed everywhere from the old app's "Needs you"
 * (read-only reference for row vocabulary: `~/cc/post/frontend/src/Attention.jsx`). Rows come
 * straight from `GET .../cuts/{cut_id}/decisions`: the same states the graph/card already
 * derive from, no separate evidence scan. Clicking a row focuses that beat's card and, for a
 * node-level decision (pick/approve/failed always carry a `node_id`; `waiting_on` never
 * does), opens its graph on that node -- card focus goes through `useFocusRequestStore`
 * (consumed by `RawTranscript`, several routes away from this bar); the graph itself is
 * opened directly on the workspace-level `graphPanelStore`, callable from anywhere. */
export function DecisionsBar({ pid }: { pid: string }) {
  const cutId = useCutStore((s) => s.cutId)
  const navigate = useNavigate()
  const requestFocus = useFocusRequestStore((s) => s.requestFocus)
  const openGraph = useGraphPanelStore((s) => s.openGraph)
  const [open, setOpen] = useState(false)
  const [rows, setRows] = useState<DecisionRow[]>([])
  const [counts, setCounts] = useState<Record<string, number>>({})
  // Refetch whenever a job event lands: a decision's cause is exactly a node reaching
  // pick/approve/failed, and the project SSE stream (connected by `JobsDrawer`) already
  // carries one event per state change.
  const lastJobSeq = useJobsStore((s) => {
    let latest = 0
    for (const job of s.jobsById.values()) if (job.seq > latest) latest = job.seq
    return latest
  })

  const load = useCallback(() => {
    if (!cutId) return
    getDecisions(pid, cutId)
      .then((data) => {
        setRows(data.rows)
        setCounts(data.counts)
      })
      .catch(() => undefined)
  }, [pid, cutId])

  useEffect(() => {
    load()
  }, [load, lastJobSeq])

  const total = Object.values(counts).reduce((n, c) => n + c, 0)

  return (
    <div className="relative border-b border-neutral-200 dark:border-neutral-800 flex items-center px-3 py-1.5">
      <button
        type="button"
        data-testid="decisions-toggle"
        disabled={!cutId}
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 font-medium disabled:opacity-50"
      >
        <span>Decisions</span>
        {total > 0 && (
          <span data-testid="decisions-count" className="rounded-full bg-amber-500 text-white text-[11px] px-1.5">
            {total}
          </span>
        )}
      </button>
      {open && (
        <div
          data-testid="decisions-panel"
          className="absolute top-full left-3 z-20 mt-1 w-96 max-h-96 overflow-y-auto border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 shadow-lg rounded"
        >
          {rows.length === 0 && <p className="px-3 py-2 text-neutral-500">Nothing needs a decision.</p>}
          {rows.map((row) => (
            <button
              type="button"
              key={`${row.span_id}-${row.node_id ?? ''}-${row.kind}`}
              data-testid="decision-row"
              data-kind={row.kind}
              data-span-id={row.span_id}
              className="block w-full text-left px-3 py-1.5 border-b border-neutral-100 dark:border-neutral-900 hover:bg-neutral-50 dark:hover:bg-neutral-800"
              onClick={() => {
                setOpen(false)
                if (!cutId) return
                navigate(`/p/${pid}/edit/${cutId}`)
                requestFocus({ spanId: row.span_id })
                if (row.node_id) openGraph(row.span_id, row.node_id)
              }}
            >
              <div className="font-medium">{KIND_LABEL[row.kind] ?? row.kind}</div>
              <div className="text-neutral-500">{row.cause}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
