import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useRef } from 'react'
import { describe, expect, it, vi } from 'vitest'
import type { VisualSuggestion } from '../api/types'
import type { FlatWord } from '../edit/blocks'
import type { SpanCard } from '../edit/rawTranscript'
import { fetchPendingSuggestions, patchSuggestion } from './api'
import { ProposedCard } from './ProposedCard'
import { useSuggestRail } from './useSuggestRail'
import { suggestionsWithWords } from './wordRange'

/** T40: a pending proposal as an editable card in the Visuals rail, numbered like its passage. */
vi.mock('./api', () => ({
  fetchPendingSuggestions: vi.fn(),
  requestSuggestVisuals: vi.fn(),
  acceptSuggestion: vi.fn().mockResolvedValue({ cut_id: 'c1', revision: 2, span_id: 'sp' }),
  dismissSuggestion: vi.fn().mockResolvedValue(undefined),
  acceptAllSuggestions: vi.fn(),
  patchSuggestion: vi.fn(),
}))

function w(id: string, text: string): FlatWord {
  return { wordId: id, text, syncGroupId: 'sg1', blockIndex: 0, deleted: false, passageId: 'p1', angleSourceId: 'src1', isBlockStart: false, start: 0, end: 1 }
}
const words = [w('a', 'Launch'), w('b', 'day'), w('c', 'is'), w('d', 'Friday')]

function suggestion(id: string, start: string, end: string, extra: Partial<VisualSuggestion> = {}): VisualSuggestion {
  return {
    id, transcript_id: 't1', start_word_id: start, end_word_id: end, medium: 'live_action',
    brief: 'A calendar page turning.', rationale: 'Names a date.', direction_note: 'Slow', flags: ['must_have_shot'], cast_refs: [], variants: [], active_variant: 0,
    ...extra,
  }
}

function renderCard(s = suggestion('s1', 'a', 'b')) {
  const item = suggestionsWithWords(words, [s])[0]!
  const props = {
    onHover: vi.fn(), onFocus: vi.fn(), onDismiss: vi.fn(), onSwitchVariant: vi.fn().mockResolvedValue(undefined),
    onSave: vi.fn().mockResolvedValue(undefined), onAccept: vi.fn().mockResolvedValue(undefined),
  }
  render(<ProposedCard item={item} focused={false} dimmed={false} {...props} />)
  return props
}

describe('ProposedCard', () => {
  it('shows the proposed state: label, medium chip, quoted words, brief, note, collapsed rationale, flags', () => {
    renderCard()
    const card = screen.getByTestId('proposed-card')
    expect(card).toHaveTextContent('Proposed')
    expect(screen.getByTestId('proposed-medium-chip')).toHaveTextContent('Live action')
    expect(card).toHaveTextContent('“Launch day”')
    expect(screen.getByTestId('proposed-brief')).toHaveValue('A calendar page turning.')
    expect(screen.getByTestId('proposed-direction')).toHaveValue('Slow')
    expect(card.querySelector('details')).not.toHaveAttribute('open')
    expect(card).toHaveTextContent('Must-have shot')
    expect(screen.getByTestId('proposed-card-badge')).toHaveTextContent('1')
  })

  it('saves an edited brief on blur and a new medium on change', async () => {
    const { onSave } = renderCard()
    fireEvent.change(screen.getByTestId('proposed-brief'), { target: { value: 'A red circle on Friday.' } })
    fireEvent.blur(screen.getByTestId('proposed-brief'))
    expect(onSave).toHaveBeenCalledWith({ brief: 'A red circle on Friday.' })
    fireEvent.change(screen.getByTestId('proposed-medium'), { target: { value: 'motion_graphic' } })
    expect(onSave).toHaveBeenLastCalledWith({ medium: 'motion_graphic' })
  })

  it('Accept saves unsaved edits first, then accepts', async () => {
    const order: string[] = []
    const { onSave, onAccept } = renderCard()
    onSave.mockImplementation(async () => void order.push('save'))
    onAccept.mockImplementation(async () => void order.push('accept'))
    fireEvent.change(screen.getByTestId('proposed-direction'), { target: { value: 'Hold on the date' } })
    await act(async () => fireEvent.click(screen.getByTestId('proposed-accept')))
    expect(onSave).toHaveBeenCalledWith({ direction_note: 'Hold on the date' })
    expect(order).toEqual(['save', 'accept'])
  })

  it('a refused edit shows why and does not accept', async () => {
    const { onSave, onAccept } = renderCard()
    onSave.mockRejectedValue(new Error('overlay position invalid'))
    fireEvent.change(screen.getByTestId('proposed-brief'), { target: { value: 'x' } })
    await act(async () => fireEvent.click(screen.getByTestId('proposed-accept')))
    expect(screen.getByTestId('proposed-error')).toHaveTextContent('overlay position invalid')
    expect(onAccept).not.toHaveBeenCalled()
  })

  it('T42: no variant switch with a single idea', () => {
    renderCard()
    expect(screen.queryByTestId('proposed-variants')).toBeNull()
  })

  it('T42: two ideas for the same words show Variant A / B; picking B switches to it', async () => {
    const variants = [
      { medium: 'live_action', brief: 'A calendar page turning.', rationale: 'a', direction_note: '', flags: [], cast_refs: [] },
      { medium: 'motion_graphic', brief: 'A countdown to Friday.', rationale: 'b', direction_note: '', flags: [], cast_refs: [] },
    ]
    const { onSwitchVariant, onSave } = renderCard(suggestion('s1', 'a', 'b', { variants, active_variant: 0 }))
    const buttons = screen.getAllByTestId('proposed-variant')
    expect(buttons.map((b) => b.textContent)).toEqual(['Variant A', 'Variant B'])
    expect(buttons[0]).toHaveAttribute('aria-pressed', 'true')
    await act(async () => fireEvent.click(buttons[0]!))
    expect(onSwitchVariant).not.toHaveBeenCalled()
    fireEvent.change(screen.getByTestId('proposed-brief'), { target: { value: 'Edited first' } })
    await act(async () => fireEvent.click(buttons[1]!))
    expect(onSave).toHaveBeenCalledWith({ brief: 'Edited first' })
    expect(onSwitchVariant).toHaveBeenCalledWith(1)
  })

  it('Dismiss calls onDismiss', () => {
    const { onDismiss } = renderCard()
    fireEvent.click(screen.getByTestId('proposed-dismiss'))
    expect(onDismiss).toHaveBeenCalled()
  })
})

const NO_CARDS: SpanCard[] = []

function Harness() {
  const ref = useRef<HTMLDivElement>(null)
  const { overlay, rail } = useSuggestRail({
    pid: 'p1', cutId: 'c1', words, cards: NO_CARDS, onSavedFocus: () => {}, containerRef: ref, selection: null, onCutChanged: () => {}, onAdjust: () => {},
  })
  return (
    <div>
      <div ref={ref}>
        {words.map((x) => <span key={x.wordId} data-word-id={x.wordId}>{x.text} </span>)}
      </div>
      {overlay}
      <section data-testid="rail">{rail.proposed.map((item) => rail.renderProposed(item))}</section>
    </div>
  )
}

describe('proposed card <-> passage pairing', () => {
  it('numbers card and passage alike in transcript order, links them both ways, and persists an edit', async () => {
    // Server order is reversed: badges still follow the transcript.
    vi.mocked(fetchPendingSuggestions).mockResolvedValue([suggestion('late', 'd', 'd'), suggestion('early', 'a', 'b')])
    vi.mocked(patchSuggestion).mockImplementation(async (_p, _c, id, edits) => ({ ...suggestion(id, 'a', 'b'), ...edits }) as VisualSuggestion)
    render(<Harness />)
    await waitFor(() => expect(screen.getAllByTestId('proposed-card')).toHaveLength(2))

    const cards = screen.getAllByTestId('proposed-card')
    expect(cards.map((c) => c.getAttribute('data-suggestion-card-id'))).toEqual(['early', 'late'])
    const passages = screen.getAllByTestId('suggestion-decoration')
    for (const p of passages) {
      const id = p.getAttribute('data-suggestion-id')!
      const card = cards.find((c) => c.getAttribute('data-suggestion-card-id') === id)!
      expect(p.querySelector('[data-testid="suggestion-badge"]')!.textContent)
        .toBe(card.querySelector('[data-testid="proposed-card-badge"]')!.textContent)
    }

    // Passage badge -> card focus (T41: only the badge takes the pointer).
    const late = passages.find((p) => p.getAttribute('data-suggestion-id') === 'late')!
    fireEvent.click(late.querySelector('[data-testid="suggestion-badge"]')!)
    await waitFor(() => expect(cards[1]).toHaveClass('is-focused'))
    expect(cards[0]).toHaveClass('is-dimmed')
    expect(late).toHaveClass('is-active')

    // Card hover -> its passage lights up.
    const early = passages.find((p) => p.getAttribute('data-suggestion-id') === 'early')!
    fireEvent.mouseEnter(cards[0]!)
    expect(early).toHaveClass('is-active')
    fireEvent.mouseLeave(cards[0]!)
    expect(early).not.toHaveClass('is-active')

    // Edit the brief, it persists on the suggestion.
    const brief = screen.getAllByTestId('proposed-brief')[0]!
    fireEvent.change(brief, { target: { value: 'Edited brief' } })
    await act(async () => fireEvent.blur(brief))
    expect(patchSuggestion).toHaveBeenCalledWith('p1', 'c1', 'early', { brief: 'Edited brief' })
  })
})
