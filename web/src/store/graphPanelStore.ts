import { create } from 'zustand'

interface GraphPanelState {
  openSpanId: string | null
  focusNodeId?: string
  openGraph: (spanId: string, focusNodeId?: string) => void
  closeGraph: () => void
}

/** T30e (owner click-through): "which span's graph is open" used to live as CardBody's own
 * `showGraph` useState, nested inside `VisualsRail`'s per-card render tree -- rendering the
 * `GraphPanel` there made the open graph's lifetime tied to that one card's own render
 * lifecycle, so a refresh triggered from WITHIN the open graph (a node run/patch calling
 * `wf.refresh()`, or any other re-render of the rail) could flash the graph closed and back
 * open, briefly exposing the transcript underneath. Lifting "which span's graph is open (+
 * optional focusNodeId)" here and rendering exactly one `GraphPanel` at the workspace level
 * (`enrich/WorkspaceGraphPanel.tsx`), outside the rail entirely, makes the open graph
 * structurally independent of any one card. Settable from anywhere: a card's own "Graph
 * view" toggle, the dialog's "Open in graph" exit, or a Decisions row. */
export const useGraphPanelStore = create<GraphPanelState>((set) => ({
  openSpanId: null,
  focusNodeId: undefined,
  openGraph: (spanId, focusNodeId) => set({ openSpanId: spanId, focusNodeId }),
  closeGraph: () => set({ openSpanId: null, focusNodeId: undefined }),
}))
