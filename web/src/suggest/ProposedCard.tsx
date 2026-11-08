import { useEffect, useState } from 'react'
import { clock } from '../edit/rawTranscript'
import type { SuggestionEdits } from './api'
import { kindLabel, MEDIUM_OPTIONS, overlayLabel, variantLabel, type SuggestionWithWords } from './wordRange'

interface Props {
  item: SuggestionWithWords
  focused: boolean
  dimmed: boolean
  onHover: (hovering: boolean) => void
  onFocus: () => void
  onSave: (edits: SuggestionEdits) => Promise<void>
  /** T42: switch to another of the proposal's ideas for the same words. */
  onSwitchVariant?: (index: number) => Promise<void>
  onAccept: () => Promise<void>
  onDismiss: () => void
}

const FLAG_LABELS: Record<string, string> = {
  must_have_shot: 'Must-have shot',
  presenter_stays_on_camera: 'Presenter stays on camera',
  picture_must_match_words: 'Picture must match words',
}

/** T40: one pending "Suggest visuals" proposal as a card in the Visuals rail -- dashed, labelled
 * "Proposed", numbered to match its dashed passage. Brief, direction note and medium are edited
 * here and saved on the suggestion (blur / change); Accept saves any unsaved edit first, so the
 * real card it becomes carries them. T42: when the agent offered more than one idea for the
 * words, "Variant A / Variant B" switches between them (unsaved edits are saved first). */
export function ProposedCard({ item, focused, dimmed, onHover, onFocus, onSave, onSwitchVariant, onAccept, onDismiss }: Props) {
  const s = item.suggestion
  const [brief, setBrief] = useState(s.brief)
  const [note, setNote] = useState(s.direction_note ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => setBrief(s.brief), [s.brief])
  useEffect(() => setNote(s.direction_note ?? ''), [s.direction_note])

  function pendingEdits(): SuggestionEdits {
    const edits: SuggestionEdits = {}
    if (brief !== s.brief) edits.brief = brief
    if (note !== (s.direction_note ?? '')) edits.direction_note = note
    return edits
  }

  async function save(edits: SuggestionEdits): Promise<boolean> {
    if (Object.keys(edits).length === 0) return true
    setError(null)
    try {
      await onSave(edits)
      return true
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      return false
    }
  }

  async function accept() {
    setBusy(true)
    try {
      if (await save(pendingEdits())) await onAccept()
    } finally {
      setBusy(false)
    }
  }

  async function switchTo(index: number) {
    if (!onSwitchVariant || index === (s.active_variant ?? 0)) return
    setBusy(true)
    setError(null)
    try {
      if (await save(pendingEdits())) await onSwitchVariant(index)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const variants = s.variants ?? []
  const overlay = overlayLabel(s.overlay_depth, s.overlay_position)
  return (
    <article
      data-testid="proposed-card"
      data-suggestion-card-id={s.id}
      className={['visual-rail-card', 'suggestion-card', 'proposed-card', focused ? 'is-focused' : '', dimmed ? 'is-dimmed' : '']
        .filter(Boolean)
        .join(' ')}
      onMouseEnter={() => onHover(true)}
      onMouseLeave={() => onHover(false)}
      onClick={(e) => {
        if ((e.target as HTMLElement).closest('button, a, input, textarea, select, summary')) return
        onFocus()
      }}
    >
      <div className="suggestion-card-heading">
        <span className="proposed-heading">
          <span className="suggest-badge" data-testid="proposed-card-badge">{item.n}</span>
          <b>Proposed</b>
          {s.medium && <span className="proposed-chip" data-testid="proposed-medium-chip">{kindLabel(s.medium)}</span>}
          {overlay && <span className="proposed-chip">{overlay}</span>}
        </span>
        <time>
          {clock(item.start)}–{clock(item.end)}
        </time>
      </div>
      <blockquote>“{item.text}”</blockquote>
      {variants.length > 1 && (
        <div className="proposed-variants" role="group" aria-label="Ideas for these words" data-testid="proposed-variants">
          {variants.map((v, i) => (
            <button
              key={i} type="button" data-testid="proposed-variant" title={v.brief} disabled={busy}
              aria-pressed={i === (s.active_variant ?? 0)}
              onClick={() => void switchTo(i)}
            >
              {variantLabel(i)}
            </button>
          ))}
        </div>
      )}
      <label className="proposed-field">
        <span>Brief</span>
        <textarea
          data-testid="proposed-brief" rows={2} value={brief}
          onChange={(e) => setBrief(e.target.value)}
          onBlur={() => void save(brief !== s.brief ? { brief } : {})}
        />
      </label>
      <label className="proposed-field">
        <span>Direction note</span>
        <textarea
          data-testid="proposed-direction" rows={1} value={note} placeholder="Camera, pace, framing…"
          onChange={(e) => setNote(e.target.value)}
          onBlur={() => void save(note !== (s.direction_note ?? '') ? { direction_note: note } : {})}
        />
      </label>
      <label className="proposed-field">
        <span>Medium</span>
        <select
          data-testid="proposed-medium" value={s.medium ?? ''}
          onChange={(e) => void save({ medium: (e.target.value || null) as SuggestionEdits['medium'] })}
        >
          {MEDIUM_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
          {s.overlay_depth && <option value="">Overlay only</option>}
        </select>
      </label>
      {(s.flags ?? []).length > 0 && (
        <p className="proposed-flags">
          {(s.flags ?? []).map((f) => (
            <span key={f} className="proposed-chip">{FLAG_LABELS[f] ?? f}</span>
          ))}
        </p>
      )}
      {s.rationale && (
        <details className="proposed-rationale">
          <summary>Why</summary>
          <p>{s.rationale}</p>
        </details>
      )}
      {error && <p className="suggest-error" role="alert" data-testid="proposed-error">{error}</p>}
      <div className="suggestion-actions">
        <button type="button" className="small primary" data-testid="proposed-accept" disabled={busy} onClick={() => void accept()}>
          Accept
        </button>
        <button type="button" className="small ghost" data-testid="proposed-dismiss" disabled={busy} onClick={onDismiss}>
          Dismiss
        </button>
      </div>
    </article>
  )
}
