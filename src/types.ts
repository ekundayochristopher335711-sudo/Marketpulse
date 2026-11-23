export type Product = {
  id: number; title: string; category: string; price: number; previousPrice: number;
  location: string; source: string; condition: string; listed: string; views: number;
  saves: number; trend: number; image: string; description: string; verifiedDemo: boolean;
  origin?: 'live' | 'imported' | 'demo';
  sourceUrl?: string; observedAt?: string;
}
export type Page = 'Overview'|'Products'|'Trending'|'Price intelligence'|'Opportunities'|'Watchlist'|'Data sources'|'Reports'|'Settings'
export type MarketAnalysisPayload = {
  listing_count: number
  median_asking_price_ngn: number
  price_reductions: number
  engagement_records: number
  categories: Array<{
    name: string
    listing_count: number
    median_asking_price_ngn: number
    price_reductions: number
    engagement_records: number
  }>
}

export type WorkspaceSettings = {
  defaultMarket: 'Nigeria' | 'Lagos State' | 'Abuja FCT'
  currency: 'NGN'
  compactMode: boolean
  weeklyDigest: boolean
}
