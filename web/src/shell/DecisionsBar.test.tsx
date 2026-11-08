import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DecisionsBar } from './DecisionsBar'
import { useCutStore } from '../store/cutStore'
import { useFocusRequestStore } from '../store/focusRequestStore'
import { useGraphPanelStore } from '../store/graphPanelStore'
import { getDecisions } from './api'

/** T30e: the top-bar Decisions view -- renamed from the old app's "Needs you". Rows come from
 * `getDecisions` (mocked here); clicking one requests focus on that beat's card
 * (`useFocusRequestStore`, consumed by `RawTranscript` elsewhere in the tree -- not re-tested
 * here) and, for a node-level decision, opens its graph directly on `graphPanelStore`. */
vi.mock('./api', () => ({
  getDecisions: vi.fn(),
}))

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => mockNavigate }
})

beforeEach(() => {
  mockNavigate.mockClear()
  useCutStore.setState({ cutId: 'cut-1' })
  useFocusRequestStore.setState({ request: null })
  useGraphPanelStore.setState({ openSpanId: null, focusNodeId: undefined })
  vi.mocked(getDecisions).mockResolvedValue({
    rows: [
      { kind: 'pick', span_id: 'span-1', node_id: 'span-1-pick', cause: 'pick a variant', link: 'span:span-1/node:span-1-pick' },
      { kind: 'waiting_on', span_id: 'span-2', node_id: null, cause: "cast 'Dana' has no approved anchor yet", link: 'span:span-2' },
    ],
    counts: { pick: 1, approve: 0, failed: 0, waiting_on: 1 },
  })
})

function renderBar() {
  return render(
    <MemoryRouter>
      <DecisionsBar pid="p1" />
    </MemoryRouter>,
  )
}

describe('DecisionsBar', () => {
  it('shows the total count and opens a panel listing every row', async () => {
    renderBar()
    await waitFor(() => expect(screen.getByTestId('decisions-count')).toHaveTextContent('2'))
    fireEvent.click(screen.getByTestId('decisions-toggle'))
    expect(screen.getAllByTestId('decision-row')).toHaveLength(2)
  })

  it('a node-level row focuses the card, opens its graph, and navigates to the cut', async () => {
    renderBar()
    await waitFor(() => screen.getByTestId('decisions-toggle'))
    fireEvent.click(screen.getByTestId('decisions-toggle'))
    const rows = screen.getAllByTestId('decision-row')
    fireEvent.click(rows[0]!) // the "pick" row, span-1/span-1-pick
    expect(mockNavigate).toHaveBeenCalledWith('/p/p1/edit/cut-1')
    expect(useFocusRequestStore.getState().request).toEqual({ spanId: 'span-1' })
    expect(useGraphPanelStore.getState().openSpanId).toBe('span-1')
    expect(useGraphPanelStore.getState().focusNodeId).toBe('span-1-pick')
  })

  it('a waiting_on row (no node) requests a plain card focus, no graph', async () => {
    renderBar()
    await waitFor(() => screen.getByTestId('decisions-toggle'))
    fireEvent.click(screen.getByTestId('decisions-toggle'))
    const rows = screen.getAllByTestId('decision-row')
    fireEvent.click(rows[1]!) // the "waiting_on" row, span-2, no node
    expect(useFocusRequestStore.getState().request).toEqual({ spanId: 'span-2' })
    expect(useGraphPanelStore.getState().openSpanId).toBeNull()
  })
})
