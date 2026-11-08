import type { Page, Route } from '@playwright/test'
import { longShowWords } from './fixtures/longShow'

/** T34: a 45-minute, two-speaker show (~7,000 words, `fixtures/longShow.ts`) as one cut over
 * one transcript, for the editor's load-time and scroll check. Production always opens a cut
 * in RawTranscript (the pre-lock media view is flag-gated off); this e2e build turns that
 * flag on for the older specs, so the source here is `kind: "virtual"` -- the one switch that
 * routes EditWorkspace to RawTranscript in this build too. RawTranscript never touches media,
 * so a real recording's source would render exactly the same words. Words are served in the
 * real server's pages (`/words`, MAX_PAGE=2000). */
export const pid = 'proj-long'
export const cutId = 'cut-long'
const transcriptId = 'tr-long'
const syncGroupId = 'sg-long'
const sourceId = 'src-long'

export const words = longShowWords()

const shoots = [{
  id: 'shoot-long', schema_version: 1, name: 'default', transcript_ids: [transcriptId],
  sources: [{
    id: sourceId, schema_version: 1, path: null, fps: { num: 25, den: 1 }, start_timecode: '00:00:00:00', role: 'a_roll',
    kind: 'virtual', proxy_path: null, peaks_path: null, audio_proxy_path: null, content_fingerprint: 'virtual:long',
  }],
  sync_groups: [{ id: syncGroupId, schema_version: 1, source_ids: [sourceId], offsets: { [sourceId]: 0 } }],
}]

const cut = {
  id: cutId, schema_version: 1, aspect: { num: 16, den: 9 }, fps: { num: 25, den: 1 }, parent_cut_id: null,
  variant_label: '', sections: [], spans: [],
  passages: [{
    id: 'passage-long', schema_version: 1, sync_group_id: syncGroupId, start_word_id: words[0]!.id,
    end_word_id: words[words.length - 1]!.id, trims: { head: 0, tail: 0 }, angle_source_id: sourceId, framing: null,
  }],
}

export async function mockLongShowApi(page: Page) {
  await page.route('**/api/**', async (route: Route) => {
    const url = new URL(route.request().url())
    const path = url.pathname
    const base = `/api/projects/${pid}`
    if (path === `${base}/shoots`) return route.fulfill({ json: shoots })
    if (path === `${base}/transcripts/${transcriptId}`) {
      return route.fulfill({
        json: { revision: 1, word_count: words.length, transcript: { id: transcriptId, schema_version: 1, sync_group_id: syncGroupId, provider: 'import:json', fingerprint: 'long' } },
      })
    }
    if (path === `${base}/transcripts/${transcriptId}/words`) {
      const offset = Number(url.searchParams.get('offset') ?? '0')
      const limit = Math.min(2000, Number(url.searchParams.get('limit') ?? '500'))
      return route.fulfill({ json: { transcript_id: transcriptId, total: words.length, offset, limit, words: words.slice(offset, offset + limit) } })
    }
    if (path === `${base}/transcripts/${transcriptId}/suggestions`) return route.fulfill({ json: [] })
    if (path === `${base}/cuts/${cutId}`) return route.fulfill({ json: { revision: 1, cut } })
    if (path === `${base}/cuts`) return route.fulfill({ json: [{ id: cutId, aspect: cut.aspect, variant_label: '', parent_cut_id: null, passage_count: 1 }] })
    if (path === `${base}/cuts/${cutId}/timeline`) return route.fulfill({ json: [] })
    if (path === `${base}/cuts/${cutId}/suggested-visuals`) return route.fulfill({ json: { items: [] } })
    if (path === `${base}/cuts/${cutId}/decisions`) {
      return route.fulfill({ json: { rows: [], counts: { pick: 0, approve: 0, failed: 0, waiting_on: 0 } } })
    }
    if (path === base) return route.fulfill({ json: { id: pid, schema_version: 1, name: 'Show #37', root: '/tmp/long', brand_kit: 'show' } })
    if (path === '/api/brand-kits') return route.fulfill({ json: { kits: [] } })
    if (path === '/api/doctor') return route.fulfill({ json: { providers: 'fake' } })
    return route.abort() // events, media: nothing to stream for this check
  })
}
