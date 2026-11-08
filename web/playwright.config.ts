import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  // enrich.spec.ts needs a real post_api (POST3_FAKE_PROVIDERS=1) and its own fixture file
  // -- run only via `npm run e2e:enrich` (playwright.enrich.config.ts), not here alongside
  // the route-mocked suite.
  testIgnore: ['enrich.spec.ts'],
  timeout: 30_000,
  fullyParallel: true,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:4173',
  },
  webServer: {
    // T30e (owner click-through, item b): the pre-lock media-backed editor (TranscriptView)
    // is gated behind `VITE_PRE_LOCK_TOOLS=1` in production so it can never appear by
    // accident -- `transcript.spec.ts`/`boundary.spec.ts`/`perf.spec.ts` deliberately exercise
    // that layout against real media fixtures, so this build turns the flag on. The
    // RawTranscript-only suites (`rawTranscript.spec.ts`, `suggest.spec.ts`) are unaffected
    // either way -- their fixture's source is `kind: "virtual"` (no media), which already
    // renders RawTranscript regardless of this flag.
    command: 'npm run build && npm run preview -- --port 4173 --host 127.0.0.1',
    port: 4173,
    reuseExistingServer: false,
    timeout: 60_000,
    env: { VITE_PRE_LOCK_TOOLS: '1' },
  },
})
