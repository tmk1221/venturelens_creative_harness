import { NavLink } from 'react-router-dom'

const ITEMS = [
  { to: 'ingest', label: 'Ingest' },
  { to: 'edit', label: 'Edit' },
  { to: 'deliver', label: 'Deliver' },
]

export function LeftNav() {
  return (
    <nav className="w-40 shrink-0 border-r border-neutral-200 dark:border-neutral-800 flex flex-col py-2">
      {ITEMS.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          className={({ isActive }) =>
            `px-3 py-1.5 text-left ${
              isActive
                ? 'bg-neutral-100 dark:bg-neutral-800 font-medium'
                : 'text-neutral-500 hover:bg-neutral-50 dark:hover:bg-neutral-900'
            }`
          }
        >
          {item.label}
        </NavLink>
      ))}
    </nav>
  )
}
