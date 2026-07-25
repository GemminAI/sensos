import { useLineageGraph } from '../hooks/useLineageGraph'
import type { RuntimeEvent } from '../models/types'

interface Props {
  events: RuntimeEvent[]
}

export function LineageGraph({ events }: Props) {
  const { nodes, edges, truncated } = useLineageGraph(events)
  if (nodes.length === 0) return null

  return (
    <section className="panel lineage">
      <h2>Event Lineage (RC-1)</h2>
      {truncated && <p className="warn-text">Showing first 100 nodes only.</p>}
      <div className="lineage-graph">
        <svg viewBox="0 0 400 200" className="lineage-svg">
          {edges.map((e, i) => {
            const fromIdx = nodes.findIndex((n) => n.id === e.from)
            const toIdx = nodes.findIndex((n) => n.id === e.to)
            const x1 = 40 + (fromIdx % 10) * 36
            const y1 = 30 + Math.floor(fromIdx / 10) * 40
            const x2 = 40 + (toIdx % 10) * 36
            const y2 = 30 + Math.floor(toIdx / 10) * 40
            return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke="#4ade80" strokeWidth="1" opacity="0.6" />
          })}
          {nodes.map((n, i) => {
            const x = 40 + (i % 10) * 36
            const y = 30 + Math.floor(i / 10) * 40
            return <circle key={n.id} cx={x} cy={y} r="4" fill="#22c55e" />
          })}
        </svg>
      </div>
      <p className="muted small">{nodes.length} nodes · {edges.length} edges</p>
    </section>
  )
}
