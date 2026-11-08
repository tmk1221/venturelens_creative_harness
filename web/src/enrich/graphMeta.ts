import type { NodeRegistry, NodeTypeInfo, WorkflowState } from './types'

/** T28: plain-word names/icons/colours for the graph view, kept separate from GraphPanel/
 * GraphNode so those stay small. Nothing here talks to the network. */

export const NODE_HUMAN_NAME: Record<string, string> = {
  'brief.write': 'Brief',
  'still.generate': 'Start frames',
  'human.pick': 'Pick a frame',
  'motion.from_frame': 'Motion prompt',
  'endframe.generate': 'End frame',
  'video.generate': 'Video',
  'animation.design': 'Animation design',
  'animation.draft_render': 'Draft render',
  'animation.render': 'Render',
  'overlay.measure': 'Overlay measurement',
  'overlay.cutout': 'Overlay cutout',
  'provided.clip': 'Provided clip',
  'asset.verify': 'Verify',
  'human.approve': 'Approve',
  'source.file': 'Reference image',
  'text.prompt': 'Text prompt',
}

export function humanNodeName(typeId: string): string {
  return NODE_HUMAN_NAME[typeId] ?? typeId
}

/** State pill text, in plain words (spec: "Waiting for a pick / Generating… / Ready to
 * approve / Approved / Out of date / Failed: <cause>"). `human.approve`'s own `done`/`stale`
 * really mean "approved" (see CardBody's onApprove docstring for why `done` is the approved
 * state); every other node type's `done` just means "built". */
export function stateText(typeId: string, state: WorkflowState, failCause?: string | null): string {
  if (state === 'failed') return failCause ? `Failed: ${failCause}` : 'Failed'
  if (state === 'needs_pick') return 'Waiting for a pick'
  if (state === 'needs_approval') return 'Ready to approve'
  if (state === 'ready') return 'Generating…'
  if (state === 'stale') return typeId === 'human.approve' ? 'Approval out of date' : 'Out of date'
  if (state === 'done') return typeId === 'human.approve' ? 'Approved' : 'Done'
  if (state === 'blocked') return 'Waiting on another node'
  return 'Not planned'
}

/** First output handle type of a node type, used to colour its source handle and choose an
 * icon glyph. Falls back to the first input's type for pass-through/sink node types
 * (`human.approve` has no outputs). */
export function handleCategory(typeId: string, registry: NodeRegistry | null): string {
  const t = registry?.node_types.find((nt) => nt.id === typeId)
  const out = t?.outputs?.[0] as { type?: string } | undefined
  const inp = t?.inputs?.[0] as { type?: string } | undefined
  return out?.type ?? inp?.type ?? 'any'
}

export const HANDLE_COLOR: Record<string, string> = {
  image: '#5aa9e6',
  video: '#c77dff',
  prompt: '#e0b64d',
  text: '#e0b64d',
  words: '#e0b64d',
  audio: '#4dd6c0',
  character: '#ff8bcb',
  brand: '#ffd166',
  any: '#7b8698',
}

export function handleColor(category: string): string {
  return HANDLE_COLOR[category] ?? HANDLE_COLOR.any!
}

/** Small inline glyph per coarse handle category -- no icon font/asset, just a single
 * character that reads at 11px in a dark card header. */
export const TYPE_ICON: Record<string, string> = {
  image: '▣', // ▣
  video: '▶', // ▶
  prompt: '✎', // ✎
  text: '✎',
  words: '✎',
  audio: '♫', // ♫
  character: '◉', // ◉
  brand: '✦', // ✦
  any: '◇', // ◇
}

export function typeIcon(category: string): string {
  return TYPE_ICON[category] ?? TYPE_ICON.any!
}

// ---- T29: named handles (multi-input/output nodes), palette, isValidConnection --------

export interface HandleSpec {
  name: string
  type: string
  required?: boolean
  many?: boolean
}

/** A node type's declared inputs, straight off the registry. */
export function nodeInputs(typeId: string, registry: NodeRegistry | null): HandleSpec[] {
  const t = registry?.node_types.find((nt) => nt.id === typeId)
  return (t?.inputs ?? []) as unknown as HandleSpec[]
}

/** A node type's outputs, with `source.file`'s single "file" output's type swapped for its
 * instance's own `handle_type` param -- mirrors `graph.workflow.validate`'s identical
 * override server-side (a `source.file` node stands in for any handle type; its NodeType-
 * level declaration only exists to give un-parameterised instances a default). */
export function nodeOutputs(
  typeId: string, params: Record<string, unknown> | undefined, registry: NodeRegistry | null,
): HandleSpec[] {
  const t = registry?.node_types.find((nt) => nt.id === typeId)
  const outs = (t?.outputs ?? []) as unknown as HandleSpec[]
  if (typeId === 'source.file' && outs.length > 0) {
    const handleType = (params?.handle_type as string | undefined) ?? outs[0]!.type
    return [{ ...outs[0]!, type: handleType }]
  }
  return outs
}

/** Mirrors `graph.types.types_compatible`: equal, or either side is the "any" pseudo-type
 * (`human.pick`/`human.approve`'s pass-through handles). */
export function typesCompatible(a: string, b: string): boolean {
  return a === b || a === 'any' || b === 'any'
}

// T30d: node types whose "model" param picks from the registry's fixture-priced options --
// shared between the in-node picker (`nodes/ModelPicker.tsx`) and `GraphInspector`'s own
// model select, so the two never disagree about which registry `kind` a node type draws
// from. Mirrors `post_api`'s own `routes/enrich.py::MODEL_OPTIONS` grouping.
export const MODEL_KIND: Record<string, string> = {
  'still.generate': 'image', 'endframe.generate': 'image', 'video.generate': 'video',
}

/** One fixture pricing dict (`ModelOption.pricing`) -> a short label, e.g. "2.5 cr/call" or
 * "1.75 cr/s". Shared by the in-node picker and the inspector's model select. */
export function priceLabel(pricing: Record<string, unknown>): string {
  if (typeof pricing.credits_per_call === 'number') return `${pricing.credits_per_call} cr/call`
  if (typeof pricing.credits_per_second === 'number') return `${pricing.credits_per_second} cr/s`
  return '—'
}

export interface PaletteItem {
  typeId: string
  label: string
  /** Overrides `defaultParamsFor`'s output for this specific palette button -- lets two
   * buttons share one node type (e.g. "Reference image" vs "Character", both `source.file`)
   * with different starting params. */
  paramOverrides?: Record<string, unknown>
  /** `data-testid` suffix (after `graph-add-`). Defaults to the type id's dashed form
   * (pre-T30d behaviour, e.g. `source.file` -> `source-file`) when omitted -- only the
   * second button sharing a type id (Character) needs its own. */
  testId?: string
}

/** Frontend-only marker on a `source.file` node's `path` param: "this is a character
 * reference, picked from the cast registry" (see `PALETTE`'s "Character" entry docstring).
 * `nodes/CharacterNode.tsx` renders whenever a node's path starts with this. */
export const CHARACTER_PATH_PREFIX = 'cast/'

/** T29 graph palette: a curated, ordered subset of the node registry -- every node type a
 * user might reasonably drop onto a beat's graph by hand, in plain words (not the jargon
 * `humanNodeName` uses for the recipe's own built-in nodes, e.g. `human.pick` reads "Pick a
 * frame" on its recipe-built card but just "Pick" as a palette button). `GraphPanel` filters
 * this against the live registry, so a registry missing one of these ids just omits it. */
export const PALETTE: PaletteItem[] = [
  { typeId: 'source.file', label: 'Reference image' },
  // T30d: same `source.file` node type as "Reference image" (an image-typed source node,
  // wire-compatible with `still.generate`'s "continuity" input) -- `CHARACTER_PATH_PREFIX`
  // above is the frontend-only convention that tells `nodes/CharacterNode` to render the
  // cast picker instead of a raw path field (see that file's docstring for why: cast
  // membership is UI metadata, not a new wire type -- `HandleType` already has a "character"
  // value but using it here would make the node's output incompatible with continuity's
  // "image" input).
  {
    typeId: 'source.file', label: 'Character', testId: 'character',
    paramOverrides: { path: CHARACTER_PATH_PREFIX, handle_type: 'image' },
  },
  { typeId: 'text.prompt', label: 'Text prompt' },
  { typeId: 'still.generate', label: 'Start frames' },
  { typeId: 'video.generate', label: 'Video' },
  { typeId: 'endframe.generate', label: 'End frame' },
  { typeId: 'human.pick', label: 'Pick' },
  { typeId: 'human.approve', label: 'Approve' },
]

/** Minimal valid params for a freshly palette-added node: every *required* field (per the
 * node type's own JSON schema, as `NodeTypeOut.params_schema` carries it) filled with a
 * type-appropriate zero value, so `POST .../nodes` validates -- the user fills in real
 * values afterwards through the typed inspector. `source.file` gets a unique placeholder
 * path plus an "image" handle type (the common hand-added case); `video.generate`'s
 * `duration` gets a small positive default instead of 0 (a zero-second clip is a degenerate
 * request downstream). */
export function defaultParamsFor(nodeType: NodeTypeInfo): Record<string, unknown> {
  const schema = nodeType.params_schema as { properties?: Record<string, Record<string, unknown>>; required?: string[] }
  const out: Record<string, unknown> = {}
  for (const name of schema.required ?? []) {
    const prop = schema.properties?.[name] ?? {}
    const jsonType = (prop.type as string | undefined) ??
      (Array.isArray(prop.anyOf) ? (prop.anyOf as { type?: string }[]).find((s) => s.type)?.type : undefined)
    out[name] = jsonType === 'integer' || jsonType === 'number' ? 0 : jsonType === 'boolean' ? false : ''
  }
  if (nodeType.id === 'source.file') {
    out.path = `reference-${Date.now().toString(36)}.png`
    out.handle_type = 'image'
  }
  if (nodeType.id === 'video.generate') out.duration = 4
  return out
}
