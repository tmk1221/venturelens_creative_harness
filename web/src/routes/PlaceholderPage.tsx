interface Props {
  label: string
}

export function PlaceholderPage({ label }: Props) {
  return <div className="p-6 text-neutral-500">{label} — not built yet.</div>
}
