import { useEffect, useState } from 'react'

/** T30d: `brief.write`'s in-node body -- "a `brief.write` node with a 'Generate' button on
 * the node (uses transcript words + direction + writer_context); its output feeds still
 * prompts; editable text on the node." The words/direction/writer_context are already baked
 * into the node's own params at instantiate time (`SpanSpec.words_text`/`direction_note`/
 * `writer_context` -> `BriefWriteParams`, `routes/enrich.py::span_workflow`) -- Generate just
 * runs the node so its fake-mode worker (`workers/brief_write.py::_fake_brief`) composes the
 * plausible brief from them; the textarea edits `instruction`, the one field the worker
 * always falls back to.
 *
 * "Generating…" while the click's own `run` request is in flight is tracked with a *local*
 * `busy` flag, not the node's own `state`: `state === 'ready'` (which `graphMeta.stateText`
 * also reads as "Generating…") is true for `brief.write` from the moment its workflow is
 * instantiated -- it has no required inputs, so nothing ever leaves it `blocked` -- and it
 * stays `ready` for the run's whole in-flight duration too (`compute_states` only moves a
 * node to `done` once a manifest lands on disk). Disabling on `state==='ready'` alone left
 * this button permanently disabled, unclickable from first paint. */
export function BriefNode({
  instruction, state, onPatchParams, onRunNode,
}: {
  instruction: string
  state: string
  onPatchParams: (params: Record<string, unknown>) => void
  onRunNode: () => Promise<unknown>
}) {
  const [value, setValue] = useState(instruction)
  const [busy, setBusy] = useState(false)
  useEffect(() => setValue(instruction), [instruction])
  // A run that actually completes (or fails and gets retried) eventually changes `state`
  // away from whatever it was when the click fired -- that's the signal a stale `busy` flag
  // (e.g. from a request that errored silently) can still recover from on the next refresh.
  useEffect(() => setBusy(false), [state])

  function generate() {
    if (busy) return
    setBusy(true)
    onRunNode().finally(() => setBusy(false))
  }

  return (
    <div className="graph-node-brief" data-testid="node-brief" onClick={(e) => e.stopPropagation()}>
      <textarea
        data-testid="graph-brief-instruction"
        rows={2}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={() => {
          if (value !== instruction) onPatchParams({ instruction: value })
        }}
      />
      <button type="button" data-testid="graph-brief-generate" disabled={busy} onClick={generate}>
        {busy ? 'Generating…' : 'Generate'}
      </button>
    </div>
  )
}
