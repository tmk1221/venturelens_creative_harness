import { useEffect, useState } from 'react'
import type { Project } from '../api/types'
import { getProject, setPictureMode } from '../shell/api'

type Mode = Project['picture_mode']

const OPTIONS: { value: Mode; label: string; hint: string }[] = [
  { value: 'presenter', label: 'Presenter on camera', hint: 'B-roll cuts away from the speaker and comes back.' },
  { value: 'audio_only', label: 'Audio only, full B-roll', hint: 'A voice with no picture of its own: every second needs a visual.' },
]

/** T42: the project's picture mode (`Project.picture_mode`), which steers Suggest visuals --
 * `audio_only` never proposes A-roll and covers every word of the cut with a picture beat.
 * Saved straight away (`PATCH /api/projects/{pid}`); pending proposals change on the next run. */
export function PictureModeSetting({ pid }: { pid: string }) {
  const [mode, setMode] = useState<Mode | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    getProject(pid)
      .then((project) => live && setMode(project.picture_mode ?? 'presenter'))
      .catch(() => live && setError('Could not load the project settings'))
    return () => {
      live = false
    }
  }, [pid])

  async function choose(next: Mode) {
    if (next === mode) return
    setSaving(true)
    setError(null)
    try {
      setMode((await setPictureMode(pid, next)).picture_mode)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not change the picture mode')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section data-testid="picture-mode-setting" className="space-y-2">
      <h2 className="text-sm font-medium">Picture</h2>
      {mode && (
        <div role="radiogroup" aria-label="Picture mode" className="space-y-1">
          {OPTIONS.map((o) => (
            <label key={o.value} className="flex items-start gap-2 text-sm">
              <input
                type="radio" name="picture-mode" value={o.value} data-testid={`picture-mode-${o.value}`}
                checked={mode === o.value} disabled={saving} onChange={() => void choose(o.value)}
                className="mt-1"
              />
              <span>
                {o.label}
                <span className="block text-xs text-neutral-500">{o.hint}</span>
              </span>
            </label>
          ))}
        </div>
      )}
      {error && <p data-testid="picture-mode-error" className="text-sm text-red-600">{error}</p>}
    </section>
  )
}
