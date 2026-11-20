import type { LucideIcon } from 'lucide-react'

type MetricProps = {
  label: string
  value: string
  note: string
  icon: LucideIcon
  tone: string
}

export function Metric({ label, value, note, icon: Icon, tone }: MetricProps) {
  return <div className="metric-card"><div className="metric-top"><span>{label}</span><div className={`metric-icon ${tone}`}><Icon size={17}/></div></div><div className="metric-value">{value}</div><div className="metric-bottom"><span>{note}</span></div></div>
}
