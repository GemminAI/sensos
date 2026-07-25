import { useMemo } from 'react'
import type { RuntimeEvent } from '../models/types'

const MAX_NODES = 100

export interface LineageNode {
  id: string
  label: string
  agent_id: string | null
}

export interface LineageEdge {
  from: string
  to: string
}

export function buildLineageGraph(events: RuntimeEvent[]): {
  nodes: LineageNode[]
  edges: LineageEdge[]
  truncated: boolean
} {
  const withParent = events.filter((e) => e.parent_event_id)
  const ids = new Set(events.map((e) => e.event_id))
  const relevant = new Set<string>()
  for (const e of withParent) {
    relevant.add(e.event_id)
    if (e.parent_event_id && ids.has(e.parent_event_id)) relevant.add(e.parent_event_id)
  }
  let nodeIds = [...relevant]
  const truncated = nodeIds.length > MAX_NODES
  if (truncated) nodeIds = nodeIds.slice(0, MAX_NODES)

  const nodes: LineageNode[] = nodeIds.map((id) => {
    const ev = events.find((e) => e.event_id === id)!
    return {
      id,
      label: ev.sep_event_type ?? ev.event_type,
      agent_id: ev.agent_id,
    }
  })
  const nodeSet = new Set(nodeIds)
  const edges: LineageEdge[] = withParent
    .filter((e) => nodeSet.has(e.event_id) && e.parent_event_id && nodeSet.has(e.parent_event_id))
    .map((e) => ({ from: e.parent_event_id!, to: e.event_id }))
  return { nodes, edges, truncated }
}

export function useLineageGraph(events: RuntimeEvent[]) {
  return useMemo(() => buildLineageGraph(events), [events])
}
