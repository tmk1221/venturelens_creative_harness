import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { GraphPanel } from './GraphPanel'
import type { NodeStatus, Workflow } from './types'

/** T30d: `focusNodeId?: string` on `GraphPanel` -- "selects and fits that node on open"
 * (tasks/T30.md). Exercised here at the component level rather than through the real
 * Add-visual dialog's "Open in graph" exit: that dialog-exit path has a *separate*, already
 * -diagnosed race (`RawTranscript.tsx::openInGraph` calls `ensureSpanWorkflow` itself, racing
 * the freshly-mounted card's own on-mount instantiate call for the same brand-new span --
 * whichever loses gets a 409 that's silently swallowed, so the graph never actually opens;
 * see `web/e2e/enrich.spec.ts`'s dialog test for the full writeup) -- not something this
 * slice owns or should paper over. This test instead proves `GraphPanel` itself does the
 * right thing with `focusNodeId`, independent of how a caller eventually reaches it. */

// @xyflow/react measures its container via ResizeObserver, which jsdom doesn't implement.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', ResizeObserverStub)
})
afterEach(() => {
  vi.unstubAllGlobals()
})

vi.mock('./api', () => ({
  EnrichApiError: class EnrichApiError extends Error {},
  getNodeRegistry: vi.fn().mockResolvedValue({ node_types: [], handle_types: [], models: [] }),
  getCastList: vi.fn().mockResolvedValue([]),
  getProvidedCatalogue: vi.fn().mockResolvedValue([]),
  patchLayout: vi.fn().mockResolvedValue(undefined),
}))

function workflow(): Workflow {
  return {
    id: 'wf1', schema_version: 1, recipe_id: 'motion_graphic', brand_kit_hash: null,
    nodes: [
      { id: 'span1-brief', type_id: 'brief.write', params: { instruction: '' }, selected: null },
      { id: 'span1-design', type_id: 'animation.design', params: {}, selected: null },
    ],
    edges: [{ id: 'e1', from_node: 'span1-brief', from_output: 'text', to_node: 'span1-design', to_input: 'brief' }],
    layout: {},
  }
}

function nodeStatuses(): NodeStatus[] {
  return [
    { id: 'span1-brief', type_id: 'brief.write', state: 'unresolved', input_hash: null, selected: null, outputs: [], fail_cause: null },
    { id: 'span1-design', type_id: 'animation.design', state: 'unresolved', input_hash: null, selected: null, outputs: [], fail_cause: null },
  ]
}

function renderPanel(focusNodeId?: string) {
  return render(
    <GraphPanel
      pid="p1" workflowId="wf1" nodes={nodeStatuses()} workflow={workflow()}
      onClose={vi.fn()} onChanged={vi.fn()}
      editEdges={vi.fn().mockResolvedValue(undefined)}
      run={vi.fn().mockResolvedValue(undefined)}
      addNode={vi.fn().mockResolvedValue({ node_id: 'new1' })}
      patchNode={vi.fn().mockResolvedValue(undefined)}
      deleteNode={vi.fn().mockResolvedValue(undefined)}
      focusNodeId={focusNodeId}
    />,
  )
}

describe('GraphPanel focusNodeId', () => {
  it('selects the named node on open, showing it in the inspector with no click', async () => {
    renderPanel('span1-brief')
    // No node selected yet -> "Brief" not visible until the focus effect runs.
    await waitFor(() => {
      expect(screen.getByTestId('graph-inspector')).toHaveTextContent('Brief')
    })
  })

  it('leaves nothing selected when focusNodeId is omitted', async () => {
    renderPanel(undefined)
    await waitFor(() => {
      expect(screen.getAllByTestId('graph-node').length).toBeGreaterThan(0)
    })
    expect(screen.getByTestId('graph-inspector')).toHaveTextContent('Click a node to inspect it.')
  })
})
