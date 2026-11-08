import { Outlet, useParams } from 'react-router-dom'
import { BrandKitPicker } from './BrandKitPicker'
import { DecisionsBar } from './DecisionsBar'
import { JobsDrawer } from './JobsDrawer'
import { LeftNav } from './LeftNav'
import { SpendConfirmDialog } from './SpendConfirmDialog'
import { useProvidersMode } from './useProvidersMode'

export function Shell() {
  const { pid } = useParams<{ pid: string }>()
  useProvidersMode()
  if (!pid) return null
  return (
    <div className="flex h-full w-full flex-col">
      <div className="flex items-center">
        <div className="flex-1 min-w-0">
          <DecisionsBar pid={pid} />
        </div>
        <div className="self-stretch flex items-center gap-3 px-3 border-b border-neutral-200 dark:border-neutral-800">
          <BrandKitPicker pid={pid} />
        </div>
      </div>
      <div className="flex flex-1 min-h-0">
        <LeftNav />
        <main className="flex-1 min-w-0 flex flex-col">
          <Outlet />
        </main>
        <JobsDrawer pid={pid} />
      </div>
      <SpendConfirmDialog />
    </div>
  )
}
