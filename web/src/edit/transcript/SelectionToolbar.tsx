import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import type { Shoot, SwapCandidate } from '../../api/types'
import { isFlagEnabled } from '../../settings'
import { useCutStore } from '../../store/cutStore'

interface Props {
  pid: string
  syncGroupId: string
  startWordId: string
  endWordId: string
  hasDeletedWordsInRange: boolean
  shoots: Shoot[]
  /** Distinct passage ids the current selection touches, in transcript order -- what
   * "derive short from selection" sends as `passage_ids` (derive operates on whole
   * passages, not partial words). */
  passageIds: string[]
}

const ASPECTS = ['16:9', '9:16'] as const

export function SelectionToolbar({ pid, syncGroupId, startWordId, endWordId, hasDeletedWordsInRange, shoots, passageIds }: Props) {
  const applyOp = useCutStore((s) => s.applyOp)
  const cutId = useCutStore((s) => s.cutId)
  const navigate = useNavigate()
  const [showAngles, setShowAngles] = useState(false)
  const [showSwap, setShowSwap] = useState(false)
  const [showDerive, setShowDerive] = useState(false)
  const [deriving, setDeriving] = useState(false)
  const [candidates, setCandidates] = useState<SwapCandidate[]>([])

  useEffect(() => {
    setShowAngles(false)
    setShowSwap(false)
    setShowDerive(false)
  }, [startWordId, endWordId])

  async function derive(aspect: string) {
    if (!cutId || passageIds.length === 0 || deriving) return
    setDeriving(true)
    const { data } = await api.POST('/api/projects/{pid}/cuts/derive', {
      params: { path: { pid } },
      body: { parent: cutId, passage_ids: passageIds, aspect },
    })
    setDeriving(false)
    setShowDerive(false)
    const newCutId = (data as { cut_id?: string } | undefined)?.cut_id
    if (newCutId) navigate(`/p/${pid}/edit/${newCutId}`)
  }

  const angles = shoots.flatMap((s) => s.sources)
  const showSetAngle = isFlagEnabled('post:showSetAngle')

  async function loadCandidates() {
    if (!cutId) return
    const { data } = await api.GET('/api/projects/{pid}/cuts/{cut_id}/swap-candidates', {
      params: { path: { pid, cut_id: cutId }, query: { sync_group_id: syncGroupId, start_word_id: startWordId, end_word_id: endWordId } },
    })
    setCandidates(data ?? [])
  }

  return (
    <div data-testid="selection-toolbar" className="relative z-20 flex gap-1 rounded border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 shadow px-1 py-1 w-fit">
      <button
        type="button"
        data-testid="action-delete"
        className="px-2 py-0.5 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded"
        onClick={() => void applyOp('delete_words', { sync_group_id: syncGroupId, start_word_id: startWordId, end_word_id: endWordId })}
      >
        Delete
      </button>
      {hasDeletedWordsInRange && (
        <button
          type="button"
          data-testid="action-restore"
          className="px-2 py-0.5 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded"
          onClick={() =>
            void applyOp('restore_words', {
              sync_group_id: syncGroupId, angle_source_id: angles[0]?.id ?? '', start_word_id: startWordId, end_word_id: endWordId, at: 0,
            })
          }
        >
          Restore
        </button>
      )}
      {showSetAngle && (
        <div className="relative">
          <button
            type="button"
            data-testid="action-set-angle"
            className="px-2 py-0.5 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded"
            onClick={() => setShowAngles((v) => !v)}
          >
            Set angle ▸
          </button>
          {showAngles && (
            <div className="absolute z-20 top-full left-0 bg-white dark:bg-neutral-900 border border-neutral-300 dark:border-neutral-700 rounded shadow min-w-24">
              {angles.map((a) => (
                <button
                  key={a.id}
                  type="button"
                  data-testid="angle-option"
                  className="block w-full text-left px-2 py-1 hover:bg-neutral-100 dark:hover:bg-neutral-800"
                  onClick={() =>
                    void applyOp('set_angle', {
                      sync_group_id: syncGroupId, start_word_id: startWordId, end_word_id: endWordId, new_angle_source_id: a.id,
                    })
                  }
                >
                  {a.role} · {(a.id ?? '').slice(0, 6)}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      <div className="relative">
        <button
          type="button"
          data-testid="action-swap-take"
          className="px-2 py-0.5 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded"
          onClick={() => {
            setShowSwap((v) => !v)
            if (!showSwap) void loadCandidates()
          }}
        >
          Swap take ▸
        </button>
        {showSwap && (
          <div className="absolute z-20 top-full left-0 bg-white dark:bg-neutral-900 border border-neutral-300 dark:border-neutral-700 rounded shadow min-w-48 max-h-48 overflow-y-auto">
            {candidates.length === 0 && <div className="px-2 py-1 text-neutral-500">No similar takes found</div>}
            {candidates.map((c) => (
              <button
                key={`${c.sync_group_id}-${c.start_word_id}`}
                type="button"
                data-testid="swap-candidate"
                className="block w-full text-left px-2 py-1 hover:bg-neutral-100 dark:hover:bg-neutral-800"
                onClick={() =>
                  void applyOp('replace_range_with', {
                    sync_group_id: syncGroupId, start_word_id: startWordId, end_word_id: endWordId,
                    other_sync_group_id: c.sync_group_id, other_start_word_id: c.start_word_id,
                    other_end_word_id: c.end_word_id, other_angle_source_id: angles[0]?.id ?? '',
                  })
                }
              >
                <span className="text-neutral-400">{Math.round(c.score * 100)}%</span> {c.text}
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="relative">
        <button
          type="button"
          data-testid="action-derive"
          disabled={passageIds.length === 0}
          className="px-2 py-0.5 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded disabled:opacity-40 disabled:cursor-not-allowed"
          onClick={() => setShowDerive((v) => !v)}
        >
          Derive short ▸
        </button>
        {showDerive && (
          <div className="absolute z-20 top-full left-0 bg-white dark:bg-neutral-900 border border-neutral-300 dark:border-neutral-700 rounded shadow min-w-24">
            {ASPECTS.map((aspect) => (
              <button
                key={aspect}
                type="button"
                data-testid="derive-aspect-option"
                disabled={deriving}
                className="block w-full text-left px-2 py-1 hover:bg-neutral-100 dark:hover:bg-neutral-800 disabled:opacity-50"
                onClick={() => void derive(aspect)}
              >
                {aspect}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
