import { defineConfig } from '@playwright/test'

// T26 acceptance flow: a real post_api process (POST3_FAKE_PROVIDERS=1, no network, no paid
// calls) instead of the mocked-fixture config (playwright.config.ts) the rest of web/e2e
// uses -- the node graph's state machine (plan/run/pick/approve/stale propagation) lives
// server-side and isn't worth re-implementing in a route mock. See
// scripts/enrich_e2e_up.sh for what the webServer command builds and tears down.
export default defineConfig({
  testDir: './e2e',
  testMatch: ['enrich.spec.ts'],
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:5183',
    viewport: { width: 1600, height: 1000 },
  },
  webServer: {
    command: 'bash ../scripts/enrich_e2e_up.sh',
    port: 5183,
    reuseExistingServer: false,
    timeout: 120_000,
  },
})
