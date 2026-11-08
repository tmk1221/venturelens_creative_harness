import { useCallback, useEffect, useState } from 'react'
import type { BrandPage } from '../api/types'
import { getBrandPage } from './api'

const POLL_MS = 4000

/** T41: the project's brand kit as a live style guide -- the kit's design-system page (logo,
 * colours with their names, type, the approved look), rendered by the API from the kit's own
 * files and shown in a sandboxed iframe (no script). Live: the kit's signature is polled and
 * the page reloads when a kit file changes; "Refresh" forces it. Read-only: editing the kit
 * happens outside the app. */
export function BrandPanel({ pid }: { pid: string }) {
  const [info, setInfo] = useState<BrandPage | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [nonce, setNonce] = useState(0)

  const load = useCallback(() => {
    getBrandPage(pid)
      .then((next) => {
        setInfo((prev) => (prev && prev.signature === next.signature && prev.kit_id === next.kit_id ? prev : next))
        setError(null)
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Could not load the brand kit'))
  }, [pid])

  useEffect(() => {
    load()
    const t = window.setInterval(() => {
      if (document.visibilityState === 'visible') load()
    }, POLL_MS)
    return () => window.clearInterval(t)
  }, [load])

  const src = info ? `${info.page_url}?v=${info.signature}-${nonce}` : null
  return (
    <section data-testid="brand-panel" className="space-y-2">
      <div className="flex items-center gap-3">
        <h2 className="text-sm font-medium">Brand</h2>
        {info && <span data-testid="brand-panel-kit" className="text-xs text-neutral-500">{info.kit_id}</span>}
        <button
          type="button"
          data-testid="brand-panel-refresh"
          onClick={() => {
            setNonce((n) => n + 1)
            load()
          }}
          className="ml-auto rounded border border-neutral-300 dark:border-neutral-700 px-2 py-0.5 text-xs"
        >
          Refresh
        </button>
      </div>
      {error && <p data-testid="brand-panel-error" className="text-sm text-neutral-500">{error}</p>}
      {src && (
        <iframe
          key={src}
          data-testid="brand-panel-frame"
          title="Brand style guide"
          src={src}
          sandbox=""
          className="w-full h-[640px] rounded border border-neutral-200 dark:border-neutral-800 bg-white"
        />
      )}
    </section>
  )
}
