import type { MarketAnalysisPayload, Product } from './types'

const MAX_IMPORT_ROWS = 50_000
const MAX_TITLE_LENGTH = 500

function parseCsvRows(csv: string): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let cell = ''
  let quoted = false

  for (let index = 0; index < csv.length; index += 1) {
    const character = csv[index]

    if (quoted) {
      if (character === '"' && csv[index + 1] === '"') {
        cell += '"'
        index += 1
      } else if (character === '"') {
        quoted = false
      } else {
        cell += character
      }
    } else if (character === '"' && cell.length === 0) {
      quoted = true
    } else if (character === ',') {
      row.push(cell.trim())
      cell = ''
    } else if (character === '\n' || character === '\r') {
      if (character === '\r' && csv[index + 1] === '\n') index += 1
      row.push(cell.trim())
      if (row.some(value => value.length > 0)) rows.push(row)
      row = []
      cell = ''
    } else {
      cell += character
    }
  }

  if (quoted) throw new Error('The CSV has an unclosed quoted field.')
  row.push(cell.trim())
  if (row.some(value => value.length > 0)) rows.push(row)
  return rows
}

function numberField(value: string | undefined, field: string, fallback?: number): number {
  if (value === undefined || value.trim() === '') {
    if (fallback !== undefined) return fallback
    throw new Error(`Missing required "${field}" value.`)
  }

  const number = Number(value.replace(/[₦,\s]/g, ''))
  if (!Number.isSafeInteger(number) || number < 0) {
    throw new Error(`"${field}" must be a non-negative whole number.`)
  }
  return number
}

function imageForCategory(category: string): string {
  const name = category.toLowerCase()
  if (name.includes('phone') || name.includes('tablet')) return '📱'
  if (name.includes('computer') || name.includes('laptop')) return '💻'
  if (name.includes('game')) return '🎮'
  if (name.includes('camera')) return '📷'
  if (name.includes('home')) return '🏠'
  return '📦'
}

function stableCsvMarker(category: string): string {
  const name = category.toLowerCase()
  if (name.includes('phone') || name.includes('tablet')) return 'PH'
  if (name.includes('computer') || name.includes('laptop')) return 'PC'
  if (name.includes('game')) return 'GM'
  if (name.includes('camera')) return 'CA'
  if (name.includes('home')) return 'HM'
  return name.match(/[a-z0-9]/g)?.slice(0, 2).join('').toUpperCase() || 'IT'
}

export function parseListingsCsv(csv: string): Product[] {
  const rows = parseCsvRows(csv.replace(/^\uFEFF/, ''))
  if (rows.length < 2) throw new Error('The CSV must include a header and at least one listing.')
  if (rows.length - 1 > MAX_IMPORT_ROWS) {
    throw new Error(`The CSV contains too many rows. Import up to ${MAX_IMPORT_ROWS.toLocaleString()} listings at a time.`)
  }

  const headers = rows[0].map(header => header.toLowerCase().replace(/[\s-]+/g, '_'))
  if (new Set(headers).size !== headers.length) throw new Error('The CSV contains duplicate column names.')
  const expectedWidth = headers.length
  const malformedRow = rows.slice(1).findIndex(row => row.length !== expectedWidth)
  if (malformedRow !== -1) throw new Error(`Row ${malformedRow + 2}: the number of columns does not match the header.`)
  const headerIndex = new Map(headers.map((header, index) => [header, index]))
  const value = (row: string[], ...names: string[]) => {
    for (const name of names) {
      const index = headerIndex.get(name)
      if (index !== undefined) return row[index] ?? ''
    }
    return undefined
  }

  const requiredColumns: Array<[string, string[]]> = [
    ['title', ['title']],
    ['category', ['category']],
    ['location', ['location']],
    ['source', ['source', 'source_name']],
    ['price', ['price', 'asking_price']],
  ]
  for (const [label, aliases] of requiredColumns) {
    if (!aliases.some(alias => headerIndex.has(alias))) {
      throw new Error(`The CSV is missing the required "${label}" column.`)
    }
  }

  return rows.slice(1).map((row, index) => {
    const rowNumber = index + 2
    try {
      const title = value(row, 'title')?.trim()
      const category = value(row, 'category')?.trim()
      const location = value(row, 'location')?.trim()
      const source = value(row, 'source', 'source_name')?.trim()
      if (!title || !category || !location || !source) {
        throw new Error('title, category, location, and source cannot be blank.')
      }
      if (title.length > MAX_TITLE_LENGTH) throw new Error(`title cannot exceed ${MAX_TITLE_LENGTH} characters.`)

      const price = numberField(value(row, 'price', 'asking_price'), 'price')
      if (price === 0) throw new Error('"price" must be greater than zero.')
      const previousPrice = numberField(value(row, 'previous_price'), 'previous_price', price)
      const views = numberField(value(row, 'views'), 'views', 0)
      const saves = numberField(value(row, 'saves'), 'saves', 0)
      const trend = numberField(value(row, 'trend'), 'trend', 0)
      const observedAt = value(row, 'observed_at', 'listed')?.trim()

      return {
        id: Date.now() + index,
        title,
        category,
        price,
        previousPrice,
        location,
        source,
        condition: value(row, 'condition')?.trim() || 'Not provided',
        listed: observedAt || 'Imported',
        views,
        saves,
        trend,
        image: stableCsvMarker(category),
        description: value(row, 'description')?.trim() || 'Imported listing. Verify the source record and listing status before relying on it.',
        verifiedDemo: false,
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Invalid listing data.'
      throw new Error(`Row ${rowNumber}: ${message}`)
    }
  })
}

export function buildLocalAnalysis(products: Product[]): { text: string; model: string } {
  if (!products.length) return { text: 'There are no listings to analyze yet.', model: 'Local analysis' }

  const grouped = products.reduce<Record<string, Product[]>>((groups, product) => {
    (groups[product.category] ??= []).push(product)
    return groups
  }, {})
  const categorySummaries = Object.entries(grouped)
    .sort(([, left], [, right]) => right.length - left.length)
    .slice(0, 8)
    .map(([category, items]) => {
      const categoryMedian = median(items.map(item => item.price))
      const reductions = items.filter(item => item.previousPrice > item.price).length
      return `- ${category}: ${items.length} records; median asking price NGN ${categoryMedian.toLocaleString('en-NG')}; ${reductions} observed reduction${reductions === 1 ? '' : 's'}.`
    })
  const reductions = products
    .filter(product => product.previousPrice > product.price)
    .sort((left, right) => (right.previousPrice - right.price) - (left.previousPrice - left.price))
    .slice(0, 5)
  const engagementCoverage = products.filter(product => product.views > 0 || product.saves > 0).length

  return {
    model: 'Local analysis',
    text: [
      `Observed ${products.length.toLocaleString()} listing records.`,
      `Overall median asking price: NGN ${median(products.map(product => product.price)).toLocaleString('en-NG')}.`,
      `${engagementCoverage.toLocaleString()} records include at least one reported view or save. This is coverage, not verified demand.`,
      '',
      'Category evidence:',
      ...categorySummaries,
      '',
      'Largest observed asking-price changes:',
      ...(reductions.length
        ? reductions.map(product => `- ${product.title} [record ${product.id}]: NGN ${product.previousPrice.toLocaleString('en-NG')} → NGN ${product.price.toLocaleString('en-NG')}.`)
        : ['- No lower current asking prices were supplied.']),
      '',
      'Limitations: asking prices are not completed-sale prices; imported records are not independently verified; listing activity does not prove buyer demand or profit.'
    ].join('\n')
  }
}

export function median(values: number[]): number {
  if (values.length === 0) return 0
  const sorted = [...values].sort((a, b) => a - b)
  const middle = Math.floor(sorted.length / 2)
  return sorted.length % 2 === 0
    ? Math.round((sorted[middle - 1] + sorted[middle]) / 2)
    : sorted[middle]
}

export function buildAnalysisPayload(products: Product[]): MarketAnalysisPayload {
  const grouped = products.reduce<Record<string, Product[]>>((groups, product) => {
    (groups[product.category] ??= []).push(product)
    return groups
  }, {})
  const summarize = (items: Product[]) => ({
    listing_count: items.length,
    median_asking_price_ngn: median(items.map(product => product.price)),
    price_reductions: items.filter(product => product.previousPrice > product.price).length,
    engagement_records: items.filter(product => product.views > 0 || product.saves > 0).length,
  })

  return {
    ...summarize(products),
    categories: Object.entries(grouped).map(([name, items]) => ({ name, ...summarize(items) })),
  }
}

export function toCsv(products: Product[]): string {
  const headers = ['title', 'category', 'price', 'previous_price', 'location', 'source', 'condition', 'listed', 'views', 'saves', 'trend', 'description', 'data_type']
  const escape = (value: string | number) => `"${String(value).replace(/"/g, '""')}"`
  return [
    headers.join(','),
    ...products.map(product => [
      product.title, product.category, product.price, product.previousPrice, product.location,
      product.source, product.condition, product.listed, product.views, product.saves,
      product.trend, product.description, product.origin === 'live' ? 'live' : product.verifiedDemo ? 'demo' : 'imported',
    ].map(escape).join(',')),
  ].join('\r\n')
}

export function buildMarketReport(products: Product[], datasetLabel: string): string {
  const categoryCounts = products.reduce<Record<string, number>>((counts, product) => {
    counts[product.category] = (counts[product.category] ?? 0) + 1
    return counts
  }, {})
  const categories = Object.entries(categoryCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([category, count]) => `- ${category}: ${count} listing${count === 1 ? '' : 's'}`)
  const reductions = products.filter(product => product.previousPrice > product.price).length

  return [
    'MarketPulse Nigeria — Market snapshot',
    `Generated: ${new Date().toISOString()}`,
    `Dataset: ${datasetLabel}`,
    `Listings analyzed: ${products.length}`,
    `Median asking price: ${products.length ? `NGN ${median(products.map(product => product.price)).toLocaleString('en-NG')}` : 'N/A'}`,
    `Rows with a lower current ask than previous price: ${reductions}`,
    '',
    'Listings by category:',
    ...(categories.length ? categories : ['- No listings']),
    '',
    'Caveats:',
    '- Asking prices are not verified transaction prices or guaranteed resale values.',
    '- Listing volume and price reductions alone do not establish buyer demand.',
    '- Verify listing condition, source, recency, and costs before making decisions.',
  ].join('\r\n')
}
