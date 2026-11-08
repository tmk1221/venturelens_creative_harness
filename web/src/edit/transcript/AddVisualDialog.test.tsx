import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { AddVisualDialog } from './AddVisualDialog'

vi.mock('../../suggest/api', () => ({
  requestSuggestVisuals: vi.fn().mockResolvedValue([{ id: 's1', brief: 'Show the whiteboard.', rationale: '' }]),
}))

const range = { text: 'Some words here', start: 1, end: 2, count: 3 }

function renderDialog(overrides: Partial<Parameters<typeof AddVisualDialog>[0]> = {}) {
  const onSave = vi.fn().mockResolvedValue(undefined)
  const onOpenGraph = vi.fn().mockResolvedValue(undefined)
  const onCancel = vi.fn()
  const onRemove = vi.fn().mockResolvedValue(undefined)
  render(
    <AddVisualDialog
      range={range} editing={null} editingOverlay={null} suggestCtx={null}
      onCancel={onCancel} onSave={onSave} onRemove={onRemove} onOpenGraph={onOpenGraph}
      {...overrides}
    />,
  )
  return { onSave, onOpenGraph, onCancel, onRemove }
}

describe('AddVisualDialog', () => {
  it('disables Save until a kind and a brief are set', () => {
    renderDialog()
    expect(screen.getByTestId('visual-save')).toBeDisabled()
    fireEvent.click(screen.getByTestId('visual-kind-video'))
    expect(screen.getByTestId('visual-save')).toBeDisabled()
    fireEvent.change(screen.getByTestId('visual-brief'), { target: { value: 'Show the product.' } })
    expect(screen.getByTestId('visual-save')).not.toBeDisabled()
  })

  it('saves the full beat model, including flags and overlay depth/position', async () => {
    const { onSave } = renderDialog()
    fireEvent.click(screen.getByTestId('visual-kind-video'))
    fireEvent.change(screen.getByTestId('visual-brief'), { target: { value: 'Show the product.' } })
    fireEvent.click(screen.getByTestId('visual-flag-must_have_shot'))
    fireEvent.click(screen.getByTestId('visual-overlay-on'))
    fireEvent.change(screen.getByTestId('visual-overlay-depth'), { target: { value: 'in_front' } })
    fireEvent.change(screen.getByTestId('visual-overlay-position'), { target: { value: 'center' } })
    fireEvent.click(screen.getByTestId('visual-save'))
    expect(onSave).toHaveBeenCalledWith({
      pictureKind: 'live_action', brief: 'Show the product.', directionNote: '',
      flags: ['must_have_shot'], overlay: { depth: 'in_front', position: 'center' },
    })
  })

  it('only offers "behind" over A-roll, and blocks save on an illegal combination', () => {
    renderDialog()
    fireEvent.click(screen.getByTestId('visual-kind-video'))
    fireEvent.change(screen.getByTestId('visual-brief'), { target: { value: 'Show it.' } })
    fireEvent.click(screen.getByTestId('visual-overlay-on'))
    fireEvent.change(screen.getByTestId('visual-overlay-depth'), { target: { value: 'behind' } })
    expect(screen.getByTestId('visual-overlay-invalid')).toBeInTheDocument()
    expect(screen.getByTestId('visual-save')).toBeDisabled()
  })

  it('picking the "overlay" radio needs no picture layer', async () => {
    const { onSave } = renderDialog()
    fireEvent.click(screen.getByTestId('visual-kind-overlay'))
    fireEvent.change(screen.getByTestId('visual-brief'), { target: { value: 'A lower-third.' } })
    fireEvent.click(screen.getByTestId('visual-save'))
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ pictureKind: null, overlay: expect.any(Object) }))
  })

  it('"Generate prompt" fills the brief from the suggester', async () => {
    renderDialog({ suggestCtx: { pid: 'p1', cutId: 'c1', syncGroupId: 'sg1', startWordId: 'w1', endWordId: 'w2' } })
    fireEvent.click(screen.getByTestId('visual-kind-anim'))
    fireEvent.click(screen.getByTestId('visual-generate-prompt'))
    expect(await screen.findByDisplayValue('Show the whiteboard.')).toBeInTheDocument()
  })

  it('prefills from an existing picture + overlay span pair and offers Remove', () => {
    const editing = {
      id: 'sp1', schema_version: 1, layer: 'picture' as const, kind: 'live_action', orphaned: false,
      provenance: 'human' as const, note: '', flags: ['must_have_shot' as const], cast_refs: [], direction_note: 'handheld',
      brief: { text: 'Show the box.', provenance: 'human' as const },
      start_anchor: { transcript_id: 't1', word_id: 'w1' }, end_anchor: { transcript_id: 't1', word_id: 'w2' },
    }
    renderDialog({ editing })
    expect(screen.getByTestId('visual-brief')).toHaveValue('Show the box.')
    expect(screen.getByTestId('visual-direction-note')).toHaveValue('handheld')
    expect(screen.getByTestId('visual-flag-must_have_shot')).toBeChecked()
    expect(screen.getByTestId('visual-remove')).toBeInTheDocument()
  })
})
