import { ArrowUpRight, Bookmark } from 'lucide-react'
import type { Product } from '../types'
import { money } from '../data'

type ProductTableProps = {
  items: Product[]
  setSelected: (product: Product) => void
  saved: number[]
  toggleSave: (id: number) => void
}

export function ProductTable({ items, setSelected, saved, toggleSave }: ProductTableProps) {
  return <div className="table-scroll"><table><thead><tr><th>PRODUCT</th><th>CATEGORY</th><th>ASKING PRICE</th><th>LOCATION</th><th>ACTIVITY</th><th>TREND</th><th></th></tr></thead><tbody>{items.map(product => <tr key={product.id}><td><button className="product-cell" onClick={() => setSelected(product)}><span className="product-emoji">{product.image}</span><span><b>{product.title}</b><small>{product.source} · {product.listed}</small></span></button></td><td><span className="category-chip">{product.category}</span></td><td className="price-cell">{money(product.price)}</td><td>{product.location}</td><td><b>{product.views.toLocaleString()}</b><small className="sub-cell">views · {product.saves} saves</small></td><td>{product.trend > 0 ? <span className="trend-up"><ArrowUpRight size={13}/>{product.trend}%</span> : '—'}</td><td><button aria-label={`${saved.includes(product.id) ? 'Remove' : 'Add'} ${product.title} ${saved.includes(product.id) ? 'from' : 'to'} watchlist`} className={`save-btn ${saved.includes(product.id) ? 'saved' : ''}`} onClick={() => toggleSave(product.id)}><Bookmark size={16} fill={saved.includes(product.id) ? 'currentColor' : 'none'}/></button></td></tr>)}</tbody></table></div>
}
