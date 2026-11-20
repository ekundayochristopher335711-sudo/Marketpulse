import { useEffect, useState } from 'react'
import { Bookmark, CircleHelp, X } from 'lucide-react'
import type { Product } from '../types'
import { money } from '../data'

type ProductModalProps = {
  product: Product
  saved: boolean
  alertThreshold: number | null
  onSave: () => void
  onSetAlert: (threshold: number | null) => void
  onClose: () => void
}

export function ProductModal({ product: p, saved, alertThreshold, onSave, onSetAlert, onClose }: ProductModalProps) {
  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onClose])
  const [alertInput, setAlertInput] = useState(alertThreshold ? String(alertThreshold) : '')

  return <div className="modal-backdrop" role="presentation" onClick={onClose}><div className="product-modal" role="dialog" aria-modal="true" aria-labelledby="listing-dialog-title" onClick={event => event.stopPropagation()}><div className="modal-head"><span className="eyebrow">LISTING DETAIL · {p.verifiedDemo ? 'DEMO' : 'IMPORTED'}</span><button aria-label="Close listing details" className="icon-btn" onClick={onClose}><X/></button></div><div className="modal-art"><span>{p.image}</span><i>{p.verifiedDemo ? 'DEMONSTRATION LISTING' : 'USER-IMPORTED RECORD'}</i></div><div className="modal-content"><span className="category-overline">{p.category}</span><h2 id="listing-dialog-title">{p.title}</h2><div className="modal-price">{money(p.price)}</div><div className="modal-tags"><span>{p.condition}</span><span>{p.location}</span><span>{p.listed}</span></div><p>{p.description}</p><div className="modal-stats"><div><small>Reported views</small><b>{p.views.toLocaleString()}</b></div><div><small>Reported saves</small><b>{p.saves}</b></div><div><small>Trend field</small><b>{p.trend ? `+${p.trend}%` : 'Not provided'}</b></div></div><div className="modal-source"><span>Source</span><b>{p.source}</b></div><div className="modal-warning"><CircleHelp size={16}/>{p.verifiedDemo ? 'Demonstration data only. No seller contact or live listing is available.' : 'Imported data is not independently verified. Confirm the source record before relying on it.'}</div><button className="btn btn-primary full-btn" onClick={onSave}><Bookmark size={15} fill={saved ? 'currentColor' : 'none'}/>{saved ? 'Remove from watchlist' : 'Add to watchlist'}</button><div className="price-alert-box"><label htmlFor="price-alert">Alert me when asking price is at or below</label><div><input id="price-alert" type="number" min="1" step="1000" value={alertInput} onChange={event => setAlertInput(event.target.value)} placeholder="e.g. 400000"/><button className="btn btn-secondary" onClick={() => { const threshold = Number(alertInput); if (Number.isFinite(threshold) && threshold > 0) onSetAlert(threshold) }}>Set alert</button>{alertThreshold && <button className="text-btn" onClick={() => { setAlertInput(''); onSetAlert(null) }}>Clear</button>}</div><small>Alerts are saved locally and compare against the next imported or collected dataset.</small></div></div></div></div>
}
