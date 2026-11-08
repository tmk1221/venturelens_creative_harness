import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import type { BrandKit, Company } from '../api/types'
import { listBrandKits } from '../shell/api'
import { createProject, getLibrary } from './api'

const INPUT = 'w-full rounded border border-neutral-300 dark:border-neutral-700 bg-transparent px-2 py-1'
const NEW_COMPANY = '__new__'

function slug(name: string): string {
  return name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'project'
}

/** T34/T39: `/new` -- a project from local recordings. By default it goes in the media library
 * as `<library>/<Company>/<Project>/` (pick a company or type a new one; the project name is
 * the DaVinci Resolve project's name), with the recordings referenced read-only or copied into
 * `Video/source`. "Another folder" keeps T34's free-standing project folder. The server refuses
 * a bad folder in plain words before writing anything. Submitting starts the ingest job and
 * opens the project's Ingest page to follow it. */
export function NewProjectPage() {
  const navigate = useNavigate()
  const [inLibrary, setInLibrary] = useState(true)
  const [libraryRoot, setLibraryRoot] = useState('')
  const [companies, setCompanies] = useState<Company[]>([])
  const [company, setCompany] = useState('')
  const [newCompany, setNewCompany] = useState('')
  const [name, setName] = useState('')
  const [root, setRoot] = useState('')
  const [sources, setSources] = useState('')
  const [copy, setCopy] = useState(false)
  const [kit, setKit] = useState('')
  const [kits, setKits] = useState<BrandKit[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listBrandKits().then(setKits).catch(() => setKits([]))
    getLibrary()
      .then((lib) => {
        setLibraryRoot(lib.root)
        setCompanies(lib.companies)
      })
      .catch(() => setCompanies([]))
  }, [])

  const companyName = (company === NEW_COMPANY ? newCompany : company).trim()
  const rootValue = root.trim() || (name.trim() ? `~/Post/${slug(name)}` : '')
  const paths = sources.split('\n').map((s) => s.trim()).filter(Boolean)
  const ready = !!name.trim() && paths.length > 0 && (!inLibrary || !!companyName)
  const picked = companies.find((c) => c.name === company)

  async function submit() {
    setBusy(true)
    setError(null)
    const where = inLibrary ? { company: companyName, copy_sources: copy } : { root: rootValue, copy_sources: false }
    try {
      const out = await createProject({ name: name.trim(), ...where, sources: paths, transcripts: [], brand_kit: kit || null })
      navigate(`/p/${out.project.id}/ingest`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create the project')
      setBusy(false)
    }
  }

  return (
    <div className="p-6 max-w-2xl mx-auto w-full">
      <p className="mb-2 text-sm"><Link to="/" className="text-neutral-500 hover:underline">← Projects</Link></p>
      <h1 className="text-lg font-medium mb-4">New project from a recording</h1>
      <form data-testid="new-project-form" className="space-y-4" onSubmit={(e) => { e.preventDefault(); void submit() }}>
        <div className="flex gap-4 text-sm">
          <label><input type="radio" data-testid="np-where-library" checked={inLibrary} onChange={() => setInLibrary(true)} /> Media library</label>
          <label><input type="radio" data-testid="np-where-folder" checked={!inLibrary} onChange={() => setInLibrary(false)} /> Another folder</label>
        </div>
        {inLibrary && (
          <label className="block space-y-1">
            <span className="text-sm font-medium">Company</span>
            <select data-testid="np-company" value={company} onChange={(e) => setCompany(e.target.value)} className={INPUT}>
              <option value="">Pick a company…</option>
              {companies.map((c) => (
                <option key={c.name} value={c.name}>{c.name}{c.has_brand ? ' (brand kit)' : ''}</option>
              ))}
              <option value={NEW_COMPANY}>New company…</option>
            </select>
            {company === NEW_COMPANY && (
              <input data-testid="np-new-company" value={newCompany} onChange={(e) => setNewCompany(e.target.value)}
                className={INPUT} placeholder="Company name" />
            )}
            {picked && picked.projects.length > 0 && (
              <span className="block text-xs text-neutral-500">Projects: {picked.projects.join(', ')}</span>
            )}
          </label>
        )}
        <label className="block space-y-1">
          <span className="text-sm font-medium">{inLibrary ? 'Project (the Resolve project name)' : 'Name'}</span>
          <input data-testid="np-name" value={name} onChange={(e) => setName(e.target.value)} className={INPUT}
            placeholder="Show37 Your Agent Has a Computer" />
          {inLibrary && companyName && name.trim() && (
            <span data-testid="np-library-path" className="block text-xs text-neutral-500 font-mono">
              {libraryRoot}/{companyName}/{name.trim()}/
            </span>
          )}
        </label>
        {!inLibrary && (
          <label className="block space-y-1">
            <span className="text-sm font-medium">Project folder</span>
            <input data-testid="np-root" value={root} onChange={(e) => setRoot(e.target.value)} className={INPUT}
              placeholder={name.trim() ? `~/Post/${slug(name)}` : '~/Post/my-project'} />
            <span className="block text-xs text-neutral-500">Where Post keeps its files. Not the folder the footage is in.</span>
          </label>
        )}
        <label className="block space-y-1">
          <span className="text-sm font-medium">Recordings</span>
          <textarea data-testid="np-sources" value={sources} onChange={(e) => setSources(e.target.value)} rows={3}
            className={`${INPUT} font-mono text-xs`} placeholder="/Volumes/MediaDrive/Company/Project/Video/source/episode.mp4" />
          <span className="block text-xs text-neutral-500">One full file path per line. Post only reads them.</span>
        </label>
        {inLibrary && (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" data-testid="np-copy" checked={copy} onChange={(e) => setCopy(e.target.checked)} />
            Copy recordings from elsewhere into the project's Video/source
          </label>
        )}
        <label className="block space-y-1">
          <span className="text-sm font-medium">Brand kit</span>
          <select data-testid="np-kit" value={kit} onChange={(e) => setKit(e.target.value)} className={INPUT}>
            <option value="">{inLibrary ? "Default (the company's kit, if it has one)" : 'Default'}</option>
            {kits.map((k) => (
              <option key={k.id} value={k.id}>{k.name}{k.status === 'guessed' ? ' (guessed — review)' : ''}</option>
            ))}
          </select>
        </label>
        {error && <p data-testid="np-error" className="text-sm text-red-600">{error}</p>}
        <button type="submit" data-testid="np-submit" disabled={busy || !ready}
          className="rounded bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900 px-3 py-1.5 text-sm font-medium disabled:opacity-50">
          {busy ? 'Starting…' : 'Create project'}
        </button>
      </form>
    </div>
  )
}
