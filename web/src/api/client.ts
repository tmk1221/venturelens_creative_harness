import createClient from 'openapi-fetch'
import type { paths } from './schema'

// One typed client for the whole app. Base URL is empty so requests go through Vite's
// dev proxy (`/api` -> post_api) in dev, and are same-origin in production.
export const api = createClient<paths>({ baseUrl: '' })

export type { components } from './schema'
