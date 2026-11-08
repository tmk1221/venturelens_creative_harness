import { useCallback, useState } from 'react'
import { clock, visualLabel, type SpanCard } from '../rawTranscript'
import { CardBody } from '../../enrich/CardBody'
import type { SuggestRailProps } from '../../suggest/useSuggestRail'
import { railItems } from '../../suggest/wordRange'
import type { FlatWord } from '../blocks'

interface Props {
  cards: SpanCard[]
  focusedSpanId: string | null
  onFocus: (card: SpanCard) => void
  onClear: () => void
  onEdit: (card: SpanCard) => void
  onDelete: (card: SpanCard) => void
  /** T40: words (for transcript order) and the suggest pass -- controls in the header, proposed
   * cards merged in among the saved ones, a placeholder while a run is going. */
  words?: FlatWord[]
  suggest?: SuggestRailProps
}

/** T24/T25 right rail: saved visual choices, in transcript order, ported verbatim (much
 * reduced -- no suggestions, no accept/dismiss) from
 * `~/cc/post-transcript-first/frontend/src/VisualRail.jsx`; classes come from
 * `web/src/legacy-look.css`. */
export function VisualsRail({ cards, focusedSpanId, onFocus, onClear, onEdit, onDelete, words = [], suggest }: Props) {
  // span id -> whether it has generated output (from CardBody's workflow state); only
  // consulted to decide whether Delete needs a confirm.
  const [hasOutputBySpan, setHasOutputBySpan] = useState<Map<string, boolean>>(new Map())
  const setHasOutput = useCallback((spanId: string, hasOutput: boolean) => {
    setHasOutputBySpan((prev) => {
      if (prev.get(spanId) === hasOutput) return prev
      const next = new Map(prev)
      next.set(spanId, hasOutput)
      return next
    })
  }, [])

  return (
    <section className="visual-rail" aria-label="Visual cards" data-testid="visuals-rail">
      <header className="visual-rail-heading">
        <div>
          <h4>Visuals</h4>
          <p>{focusedSpanId ? 'Linked to the highlighted words' : 'Click a marked passage to focus its card'}</p>
        </div>
        {focusedSpanId && (
          <button type="button" className="small ghost" onClick={onClear}>
            Clear focus
          </button>
        )}
      </header>
      {suggest?.headerControls && <div className="visual-rail-suggest">{suggest.headerControls}</div>}
      <div className="visual-card-list">
        {suggest?.running && (
          <div className="visual-rail-card suggestion-card suggest-placeholder" data-testid="suggest-placeholder" aria-live="polite">
            <span className="suggest-spinner" aria-hidden="true" /> Reading the transcript for moments that want a visual…
          </div>
        )}
        {suggest?.error && !suggest.running && (
          <p className="suggest-error suggest-rail-error" data-testid="suggest-rail-error" role="alert">
            Suggest visuals failed: {suggest.error}
          </p>
        )}
        {cards.length === 0 && !suggest?.proposed.length ? (
          suggest?.running ? null : (
            <p className="visual-rail-empty">
              Your words stay on the left. Select words and choose “Add visual” to plan what the viewer sees.
            </p>
          )
        ) : (
          railItems(words, cards, suggest?.proposed ?? []).map((entry) => {
            if (entry.kind === 'proposed') return suggest!.renderProposed(entry.item)
            const card = entry.card
            const id = card.span.id ?? ''
            const focused = id === focusedSpanId
            const n = suggest?.savedNumbers.get(id)
            const overlay = card.span.layer === 'overlay'
            return (
              <article
                key={id}
                data-testid="visual-card"
                data-card-key={id}
                data-span-id={id}
                className={[
                  'visual-rail-card',
                  'saved-visual-card',
                  card.beatTone !== null ? `beat-tone-${card.beatTone} has-beat-accent` : '',
                  focused ? 'is-focused' : '',
                  focusedSpanId && !focused ? 'is-dimmed' : '',
                ]
                  .filter(Boolean)
                  .join(' ')}
                onClick={(e) => {
                  if ((e.target as HTMLElement).closest('button, a, input, textarea')) return
                  onFocus(card)
                }}
              >
                <button
                  type="button"
                  className="visual-card-focus"
                  aria-pressed={focused}
                  aria-label={`Focus saved ${visualLabel(card.span.kind)} passage`}
                  onClick={() => onFocus(card)}
                >
                  <span>
                    {n !== undefined && (
                      <span className="suggest-badge is-saved saved-card-badge" data-testid="saved-card-badge">{n}</span>
                    )}
                    Saved plan · {visualLabel(card.span.kind)}
                    {overlay ? ' (overlay)' : ''}
                  </span>
                  <time>
                    {clock(card.start)}–{clock(card.end)}
                  </time>
                </button>
                <blockquote>“{card.text}”</blockquote>
                {card.span.brief?.text && (
                  <p className="visual-card-brief" data-testid="visual-card-brief">{card.span.brief.text}</p>
                )}
                {card.span.note && <p>{card.span.note.length > 240 ? `${card.span.note.slice(0, 240)}…` : card.span.note}</p>}
                <div className="suggestion-actions">
                  <button
                    type="button"
                    data-testid="visual-card-edit"
                    className={`small visual-chip ${overlay ? 'overlay' : ''}`}
                    onClick={() => onEdit(card)}
                  >
                    Edit {visualLabel(card.span.kind)}
                  </button>
                  <button
                    type="button"
                    data-testid="visual-card-delete"
                    className="small ghost"
                    onClick={() => {
                      const hasOutput = hasOutputBySpan.get(id) ?? false
                      if (hasOutput && !window.confirm('This span has generated output. Delete it anyway?')) return
                      onDelete(card)
                    }}
                  >
                    Delete
                  </button>
                </div>
                <CardBody
                  card={card}
                  onHasOutput={(hasOutput) => setHasOutput(id, hasOutput)}
                />
              </article>
            )
          })
        )}
      </div>
    </section>
  )
}
