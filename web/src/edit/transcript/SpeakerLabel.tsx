import { useEffect, useId, useRef, useState } from 'react'
import { useSpeakersStore } from '../../store/speakersStore'
import { clock } from '../rawTranscript'

interface Props {
  pid: string
  transcriptId: string
  label: string
}

/** T35: the speaker heading over each turn (`SPEAKER_00` until named). Click it to rename that
 * speaker everywhere (stored on the transcript) and to hear who it is: "Play a sample" plays
 * their longest utterance from the recording's audio proxy. */
export function SpeakerLabel({ pid, transcriptId, label }: Props) {
  const speakers = useSpeakersStore((s) => s.byTranscript.get(transcriptId))
  const load = useSpeakersStore((s) => s.load)
  const rename = useSpeakersStore((s) => s.rename)
  const id = useId()
  const open = useSpeakersStore((s) => s.openLabel === id)
  const setOpenLabel = useSpeakersStore((s) => s.setOpenLabel)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [playing, setPlaying] = useState(false)
  const audioRef = useRef<HTMLAudioElement>(null)

  useEffect(() => {
    void load(pid, transcriptId)
  }, [pid, transcriptId, load])

  const info = speakers?.speakers.find((s) => s.label === label)
  const name = info?.name ?? label

  async function save() {
    setSaving(true)
    setError(null)
    try {
      await rename(pid, transcriptId, label, draft.trim())
      setOpenLabel(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not rename the speaker')
    } finally {
      setSaving(false)
    }
  }

  function toggleSample() {
    const audio = audioRef.current
    if (!audio || !info || !speakers?.source_id) return
    if (playing) {
      audio.pause()
      return
    }
    const url = `/api/projects/${pid}/media/${speakers.source_id}/audio`
    const start = () => {
      audio.currentTime = info.sample.start
      void audio.play().catch(() => setPlaying(false))
    }
    setPlaying(true)
    if (audio.src.endsWith(url) && audio.readyState >= 1) start()
    else {
      audio.addEventListener('loadedmetadata', start, { once: true })
      audio.src = url
    }
  }

  return (
    <div className="relative mt-5 -mb-2" data-testid="speaker-turn">
      <button
        type="button"
        data-testid="speaker-label"
        data-speaker={label}
        title={info?.name ? `${label} · click to rename or hear a sample` : 'Who is this? Click to name them or hear a sample'}
        onMouseDown={(e) => e.stopPropagation()}
        onClick={() => {
          setDraft(info?.name ?? '')
          setOpenLabel(open ? null : id) // one popover at a time
        }}
        className="text-[11px] font-semibold uppercase tracking-wider text-[#9fb4cc] hover:text-white"
      >
        {name}
      </button>
      {open && (
        <div
          role="dialog"
          aria-label={`Speaker ${label}`}
          data-testid="speaker-popover"
          onKeyDown={(e) => {
            e.stopPropagation() // typing a name never reaches the transcript's or the editor's shortcuts
            if (e.key === 'Escape') setOpenLabel(null)
          }}
          className="absolute z-30 mt-1 w-80 space-y-2 rounded-lg border border-[#33415a] bg-[#111a27] p-3 text-sm text-[#dfe3eb] shadow-lg"
        >
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void save() }}>
            <input
              data-testid="speaker-name-input"
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={label}
              className="min-w-0 flex-1 rounded border border-[#33415a] bg-transparent px-2 py-1"
            />
            <button type="submit" data-testid="speaker-rename-save" disabled={saving} className="primary small">
              {saving ? 'Saving…' : 'Rename everywhere'}
            </button>
          </form>
          {info && (
            <div className="space-y-1">
              <button type="button" data-testid="speaker-sample-play" className="small" disabled={!speakers?.source_id}
                onClick={toggleSample}>
                {playing ? 'Stop' : 'Play a sample'}
              </button>
              <p className="text-xs text-[#9fb4cc]">
                {info.words.toLocaleString()} words · longest turn {clock(info.sample.start)}–{clock(info.sample.end)}: “{info.sample.text}”
              </p>
            </div>
          )}
          {error && <p data-testid="speaker-error" className="text-xs text-red-400">{error}</p>}
          <audio
            ref={audioRef}
            data-testid="speaker-sample-audio"
            preload="auto"
            onTimeUpdate={(e) => { if (info && e.currentTarget.currentTime >= info.sample.end) e.currentTarget.pause() }}
            onPause={() => setPlaying(false)}
            onEnded={() => setPlaying(false)}
          />
        </div>
      )}
    </div>
  )
}
