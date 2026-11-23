import { Activity, ArrowUpRight, Bookmark, ExternalLink } from 'lucide-react'
import type { Product } from '../types'
import { money } from '../data'

type ProductCardProps = {
  product: Product
  setSelected: (product: Product) => void
  saved: boolean
  toggleSave: (id: number) => void
}

export function ProductCard({ product, setSelected, saved, toggleSave }: ProductCardProps) {
  const label = product.origin === 'live' ? 'LIVE' : product.verifiedDemo ? 'DEMO' : 'IMPORTED'
  const sourceUrl = product.sourceUrl && /^https?:\/\//i.test(product.sourceUrl) ? product.sourceUrl : undefined

  return (
    <div className="product-card">
      <div className="product-card-art">
        <span>{product.image}</span>
        <span className="demo-chip">{label}</span>
        <button
          aria-label={`${saved ? 'Remove' : 'Add'} ${product.title} ${saved ? 'from' : 'to'} watchlist`}
          className={`card-save ${saved ? 'saved' : ''}`}
          onClick={() => toggleSave(product.id)}
        >
          <Bookmark size={16} fill={saved ? 'currentColor' : 'none'} />
        </button>
      </div>
      <div className="product-card-body">
        <span className="category-overline">{product.category}</span>
        <button className="card-title" onClick={() => setSelected(product)}>{product.title}</button>
        <b className="card-price">{money(product.price)}</b>
        <div className="card-meta"><span>{product.location}</span><span>{product.listed}</span></div>
        <div className="card-stats">
          <span><Activity size={13} />{product.views.toLocaleString()} views</span>
          <span>{product.trend > 0 ? <span className="trend-up"><ArrowUpRight size={13} />{product.trend}%</span> : 'No trend data'}</span>
        </div>
        <button className="view-listing" onClick={() => setSelected(product)}>View details <ArrowUpRight size={14} /></button>
        {sourceUrl && (
          <a className="view-listing source-product-link" href={sourceUrl} target="_blank" rel="noopener noreferrer">
            <ExternalLink size={14} /> Open original listing
          </a>
        )}
      </div>
    </div>
  )
}
