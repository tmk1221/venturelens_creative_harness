import { useState } from 'react'
import type { Span } from '../../api/types'
import { requestSuggestVisuals } from '../../suggest/api'
import {
  BEAT_FLAGS, VISUALS, clock, swapPositionForDepthChange, validOverlayPositions,
  type OverlayDepth, type OverlayPosition, type VisualKind,
} from '../rawTranscript'

/** What the dialog hands back to `RawTranscript.tsx` on Save/Open in graph -- the full T30
 * beat model, not just a kind+note pair. `pictureKind === null` means "overlay only, no
 * picture layer" (the old 5th 'overlay' radio choice). */
export interface BeatDraft {
  pictureKind: 'aroll' | 'provided' | 'live_action' | 'motion_graphic' | null
  brief: string
  directionNote: string
  flags: string[]
  overlay: { depth: OverlayDepth; position: OverlayPosition } | null
}

const PICTURE_KIND_FOR: Record<Exclude<VisualKind, 'overlay'>, BeatDraft['pictureKind']> = {
  aroll: 'aroll', provided: 'provided', video: 'live_action', anim: 'motion_graphic',
}
// Reverse map, for prefilling `kind` from an existing Span (`editing.kind` is already the
// server's `PictureKind`, not a `VisualKind`).
const VISUAL_KIND_FOR: Record<string, VisualKind> = { aroll: 'aroll', provided: 'provided', live_action: 'video', motion_graphic: 'anim' }

interface Props {
  range: { text: string; start: number; end: number; count: number }
  editing: Span | null
  editingOverlay: Span | null
  /** For "Generate prompt": which selection to ask the suggester about. Null (e.g. the
   * project has no transcripts loaded yet) just hides the button. */
  suggestCtx: { pid: string; cutId: string; syncGroupId: string; startWordId: string; endWordId: string } | null
  onCancel: () => void
  onSave: (beat: BeatDraft) => Promise<void>
  onRemove: () => Promise<void>
  onOpenGraph: (beat: BeatDraft) => Promise<void>
}

/** "What should we see here?" -- T24's dialog, extended for T30's full beat model: the same
 * 5 picture choices + direction, plus an independent overlay toggle (depth+position, matrix
 * enforced inline), flags, "Generate prompt", and two exits (Save / Open in graph). */
export function AddVisualDialog({ range, editing, editingOverlay, suggestCtx, onCancel, onSave, onRemove, onOpenGraph }: Props) {
  const initialKind: VisualKind | '' = editing
    ? (VISUAL_KIND_FOR[editing.kind] ?? '')
    : editingOverlay
      ? 'overlay'
      : ''
  const [kind, setKind] = useState<VisualKind | ''>(initialKind)
  const [brief, setBrief] = useState((editing ?? editingOverlay)?.brief?.text ?? '')
  const [directionNote, setDirectionNote] = useState(editing?.direction_note ?? '')
  const [flags, setFlags] = useState<string[]>(editing?.flags ?? [])
  const [overlayOn, setOverlayOn] = useState(editingOverlay != null)
  const [depth, setDepth] = useState<OverlayDepth>(editingOverlay?.overlay_depth ?? 'in_front')
  const [position, setPosition] = useState<OverlayPosition>((editingOverlay?.overlay_position as OverlayPosition) ?? 'lower-band')
  const [saving, setSaving] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState('')
  const [genNote, setGenNote] = useState('')

  const pictureKindForMatrix = kind === '' ? 'aroll' : kind === 'overlay' ? 'aroll' : kind
  const positions = validOverlayPositions(pictureKindForMatrix, depth)

  function setDepthChecked(next: OverlayDepth) {
    setDepth(next)
    setPosition((p) => {
      const swapped = swapPositionForDepthChange(p, pictureKindForMatrix)
      const legal = validOverlayPositions(pictureKindForMatrix, next)
      return legal.includes(swapped) ? swapped : (legal[0] ?? p)
    })
  }

  function draft(): BeatDraft {
    const pictureKind = kind === '' || kind === 'overlay' ? null : PICTURE_KIND_FOR[kind]
    const wantsOverlay = kind === 'overlay' || overlayOn
    return {
      pictureKind,
      brief,
      directionNote,
      flags,
      overlay: wantsOverlay ? { depth, position } : null,
    }
  }

  async function act(fn: () => Promise<void>) {
    setSaving(true)
    setError('')
    try {
      await fn()
    } catch {
      setError('Save failed. Try again.')
    } finally {
      setSaving(false)
    }
  }

  async function generatePrompt() {
    if (!suggestCtx) return
    setGenerating(true)
    setGenNote('')
    try {
      const items = await requestSuggestVisuals(suggestCtx.pid, suggestCtx.cutId, {
        kind: 'selection', syncGroupId: suggestCtx.syncGroupId,
        startWordId: suggestCtx.startWordId, endWordId: suggestCtx.endWordId,
      })
      const hit = items.find((i) => i.brief?.trim())
      if (hit) setBrief(hit.brief)
      else setGenNote('No suggestion for this passage -- write one directly.')
    } catch {
      setGenNote('Could not generate a prompt. Try again.')
    } finally {
      setGenerating(false)
    }
  }

  const canSave = kind !== '' && brief.trim().length > 0

  return (
    <div
      role="dialog" aria-modal="false" aria-labelledby="visual-dialog-title" data-testid="visual-dialog"
      className="fixed z-40 inset-0 flex items-start justify-center pt-24" style={{ background: '#060b12a6' }}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !saving) onCancel()
      }}
    >
      <div className="visual-dialog">
        <header>
          <div>
            <div className="transcript-eyebrow">THIS PASSAGE</div>
            <h3 id="visual-dialog-title">What should we see here?</h3>
          </div>
          <button type="button" className="ghost" aria-label="Close visual choice" disabled={saving} onClick={onCancel}>×</button>
        </header>
        <blockquote>“{range.text}”</blockquote>
        <div className="visual-range">
          {clock(range.start)}–{clock(range.end)} · {(range.end - range.start).toFixed(1)} seconds · {range.count} words
        </div>
        <fieldset className="visual-options" disabled={saving}>
          <legend className="sr-only">Visual type</legend>
          {VISUALS.map((v) => (
            <label key={v.id} className={kind === v.id ? 'chosen' : ''}>
              <input type="radio" name="visual-kind" value={v.id} checked={kind === v.id} onChange={() => setKind(v.id)} data-testid={`visual-kind-${v.id}`} />
              <span className="visual-icon" aria-hidden="true">{v.icon}</span>
              <span><b>{v.title}</b><small>{v.detail}</small></span>
            </label>
          ))}
        </fieldset>

        <label className="visual-note">
          {kind === 'provided' ? 'Which footage do you have in mind?' : 'What should it show?'} <span>Brief</span>
          <textarea
            data-testid="visual-brief" value={brief} maxLength={4000} rows={3} disabled={saving}
            placeholder="A detail, a reference, or an idea you don’t want to lose…"
            onChange={(e) => setBrief(e.target.value)}
          />
        </label>
        {suggestCtx && (
          <div className="visual-generate-row">
            <button type="button" data-testid="visual-generate-prompt" className="small" disabled={saving || generating} onClick={() => void generatePrompt()}>
              {generating ? 'Generating…' : 'Generate prompt'}
            </button>
            {genNote && <small data-testid="visual-generate-note">{genNote}</small>}
          </div>
        )}
        <label className="visual-note">
          Direction note <span>Optional, for the editor/agent</span>
          <textarea
            data-testid="visual-direction-note" value={directionNote} maxLength={4000} rows={2} disabled={saving}
            placeholder="Camera, pacing, a reference…"
            onChange={(e) => setDirectionNote(e.target.value)}
          />
        </label>

        <fieldset className="visual-flags" disabled={saving}>
          <legend>Flags</legend>
          {BEAT_FLAGS.map((f) => (
            <label key={f.id}>
              <input
                type="checkbox" data-testid={`visual-flag-${f.id}`} checked={flags.includes(f.id)}
                onChange={(e) => setFlags((prev) => (e.target.checked ? [...prev, f.id] : prev.filter((x) => x !== f.id)))}
              />
              {f.label}
            </label>
          ))}
        </fieldset>

        {kind !== 'overlay' && kind !== '' && (
          <fieldset className="visual-overlay-toggle" disabled={saving}>
            <label>
              <input type="checkbox" data-testid="visual-overlay-on" checked={overlayOn} onChange={(e) => setOverlayOn(e.target.checked)} />
              Add an overlay
            </label>
          </fieldset>
        )}
        {(kind === 'overlay' || overlayOn) && (
          <fieldset className="visual-overlay-matrix" disabled={saving} data-testid="visual-overlay-matrix">
            <legend>Overlay placement</legend>
            <div className="visual-overlay-row">
              <label>
                Depth
                <select data-testid="visual-overlay-depth" value={depth} onChange={(e) => setDepthChecked(e.target.value as OverlayDepth)}>
                  <option value="in_front">In front</option>
                  <option value="behind">Behind (needs a subject to cut out -- A-roll only)</option>
                </select>
              </label>
              <label>
                Position
                <select data-testid="visual-overlay-position" value={position} onChange={(e) => setPosition(e.target.value as OverlayPosition)} disabled={positions.length === 0}>
                  {positions.length === 0 && <option value="">not valid for this picture</option>}
                  {positions.map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </label>
            </div>
            {positions.length === 0 && (
              <p role="alert" className="transcript-alert" data-testid="visual-overlay-invalid">
                'behind' is only valid over "Keep A-roll" -- choose 'in front', or pick A-roll as the picture.
              </p>
            )}
          </fieldset>
        )}

        {error && <div role="alert" className="transcript-alert">{error}</div>}
        <p className="visual-save-note">Saves a visual plan only. Your A-roll, existing beats and renders stay unchanged.</p>
        <footer>
          {(editing || editingOverlay) && (
            <button type="button" data-testid="visual-remove" className="ghost" disabled={saving} onClick={() => void act(onRemove)}>Remove choice</button>
          )}
          <div className="grow" />
          <button type="button" disabled={saving} onClick={onCancel}>Cancel</button>
          <button
            type="button" data-testid="visual-open-graph" disabled={saving || !canSave || positions.length === 0}
            onClick={() => canSave && void act(() => onOpenGraph(draft()))}
          >
            Open in graph
          </button>
          <button
            type="button" data-testid="visual-save" className="primary" disabled={saving || !canSave || positions.length === 0}
            onClick={() => canSave && void act(() => onSave(draft()))}
          >
            {saving ? 'Saving…' : editing || editingOverlay ? 'Save changes' : 'Save visual choice'}
          </button>
        </footer>
      </div>
    </div>
  )
}
