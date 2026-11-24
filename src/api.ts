const defaultApiBaseUrl = import.meta.env.DEV ? 'http://localhost:8000' : ''
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || defaultApiBaseUrl).replace(/\/$/, '')
const API_READ_TOKEN = String(import.meta.env.VITE_API_READ_TOKEN || '').trim()

export type ApiHealth = {
  status: string
  service: string
  database: string
}

export type MarketplaceSource = {
  source_key: string
  name: string
  access_method: string
  permission_status: string
  enabled: boolean
  minimum_interval_seconds: number
  permitted_categories: string[]
  permitted_fields: string[]
  retention_days: number | null
  last_success_at: string | null
  next_run_at: string | null
  permission_reference_present: boolean
  connector_available: boolean
}

export type MarketOverview = {
  as_of: string
  period_days: number
  total_listings: number
  active_listings: number
  median_asking_price_ngn: number | null
  newly_discovered_in_period: number
  enabled_sources: number
  latest_collection_at: string | null
  collection_success_rate_percent: number | null
  price_reductions: number
  price_increases: number
  categories: Array<{
    category: string
    active_listings: number
    median_asking_price_ngn: number | null
  }>
  locations: Array<{
    state: string | null
    city: string | null
    active_listings: number
  }>
  listing_momentum: Array<{
    category: string
    current_7_day_listings: number
    previous_7_day_listings: number
    change_percent: number | null
    signal: string
  }>
  limitations: string[]
}

export type ApiListing = {
  id: number
  source_id: string
  title: string
  category: string
  asking_price: number
  location: string
  source_name: string
  condition: string | null
  last_observed_at: string
  source_url: string | null
  description?: string | null
}

export type PaginatedListings = {
  items: ApiListing[]
  total: number
  offset: number
  limit: number
}

export type AnalysisStatus = {
  configured: boolean
  model: string | null
  local_only: boolean
  daily_limit: number
}

async function get<T>(path: string): Promise<T> {
  const headers: HeadersInit = API_READ_TOKEN
    ? { Authorization: `Bearer ${API_READ_TOKEN}` }
    : {}
  const response = await fetch(`${API_BASE_URL}${path}`, { headers })
  let body: unknown
  try {
    body = await response.json()
  } catch {
    throw new Error(`The MarketPulse API returned an invalid response (${response.status}).`)
  }
  if (!response.ok) {
    const detail = typeof body === 'object' && body !== null && 'detail' in body
      ? String(body.detail)
      : `Request failed (${response.status}).`
    throw new Error(detail)
  }
  return body as T
}

export function getApiHealth(): Promise<ApiHealth> {
  return get<ApiHealth>('/api/health')
}

export function getMarketplaceSources(): Promise<MarketplaceSource[]> {
  return get<MarketplaceSource[]>('/api/sources')
}

export function getMarketOverview(days = 30): Promise<MarketOverview> {
  return get<MarketOverview>(`/api/analytics/overview?days=${days}`)
}

export function getRecentListings(limit = 5): Promise<PaginatedListings> {
  return get<PaginatedListings>(`/api/listings?limit=${limit}&listing_status=active`)
}

export async function getExportListings(): Promise<ApiListing[]> {
  const rows: ApiListing[] = []
  const maxRows = 50_000
  let total = 0
  do {
    const page = await get<PaginatedListings>(`/api/listings?limit=500&offset=${rows.length}&listing_status=active`)
    total = page.total
    if (total > maxRows) throw new Error('This export exceeds 50,000 records. Export a smaller dataset.')
    if (!page.items.length) break
    rows.push(...page.items)
  } while (rows.length < total)
  if (rows.length < total) throw new Error('The dataset changed during export. Please try again.')
  return rows
}

export function getAnalysisStatus(): Promise<AnalysisStatus> {
  return get<AnalysisStatus>('/api/analysis/status')
}

export { API_BASE_URL, API_READ_TOKEN }
