import { useEffect, useState } from 'react'
import type { BrandKit } from '../api/types'
import { getProject, listBrandKits, setProjectKit } from './api'

/** T33: which brand kit this project's pictures are built with (`Project.brand_kit`), picked
 * from every kit `GET /api/brand-kits` lists. T41: no status chip -- "guessed" is the normal
 * state and the kit loads by itself; only a kit that does not load says so. Switching kits
 * marks the project's branded nodes stale server-side; nothing regenerates by itself. */
export function BrandKitPicker({ pid }: { pid: string }) {
  const [kits, setKits] = useState<BrandKit[]>([])
  const [current, setCurrent] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    Promise.all([getProject(pid), listBrandKits(pid)])
      .then(([project, list]) => {
        if (!live) return
        setCurrent(project.brand_kit ?? null)
        setKits(list)
      })
      .catch(() => live && setError('Brand kits unavailable'))
    return () => {
      live = false
    }
  }, [pid])

  async function choose(kitId: string) {
    if (kitId === current) return
    setSaving(true)
    setError(null)
    try {
      const project = await setProjectKit(pid, kitId)
      setCurrent(project.brand_kit)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not change the brand kit')
    } finally {
      setSaving(false)
    }
  }

  if (current === null) {
    return error ? <span data-testid="brand-kit-error" className="text-[11px] text-neutral-500">{error}</span> : null
  }
  const kit = kits.find((k) => k.id === current)
  return (
    <div data-testid="brand-kit-picker" className="flex items-center gap-1.5 text-[12px]">
      <label htmlFor="brand-kit-select" className="text-neutral-500">Brand</label>
      <select
        id="brand-kit-select"
        data-testid="brand-kit-select"
        value={current}
        disabled={saving}
        onChange={(e) => void choose(e.target.value)}
        className="max-w-48 truncate rounded border border-neutral-300 dark:border-neutral-700 bg-transparent px-1 py-0.5"
      >
        {!kit && <option value={current}>{current}</option>}
        {kits.map((k) => (
          <option key={k.id} value={k.id}>{k.name}</option>
        ))}
      </select>
      {kit?.status === 'broken' && (
        <span data-testid="brand-kit-broken" className="text-[11px] text-red-600">{kit.error ?? 'This kit does not load'}</span>
      )}
      {error && <span data-testid="brand-kit-error" className="text-[11px] text-red-600">{error}</span>}
    </div>
  )
}
