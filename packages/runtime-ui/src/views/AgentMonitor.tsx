import type { Agent, RuntimeEvent } from '../models/types'
import { deriveAgentPresence } from '../services/runtimeClient'

interface Props {
  agents: Agent[]
  events: RuntimeEvent[]
}

const PRESENCE_CLASS: Record<string, string> = {
  ONLINE: 'presence-online',
  OFFLINE: 'presence-offline',
  UNKNOWN: 'presence-unknown',
}

export function AgentMonitor({ agents, events }: Props) {
  const lastByAgent = events.reduce<Record<string, string>>((acc, e) => {
    if (!e.agent_id) return acc
    const t = e.created_at
    if (!acc[e.agent_id] || t > acc[e.agent_id]) acc[e.agent_id] = t
    return acc
  }, {})

  return (
    <section className="panel agent-monitor">
      <h2>Agent Monitor</h2>
      <ul className="agent-list">
        {agents.map((a) => {
          const presence = deriveAgentPresence(a, lastByAgent[a.agent_id] ?? null)
          return (
            <li key={a.agent_id} className="agent-card">
              <div className="agent-header">
                <strong>{a.display_name ?? a.agent_id.slice(0, 8)}</strong>
                <span className={`presence ${PRESENCE_CLASS[presence]}`}>{presence}</span>
              </div>
              <dl className="kv compact">
                <div><dt>id</dt><dd title={a.agent_id}>{a.agent_id.slice(0, 12)}…</dd></div>
                <div><dt>provider</dt><dd>{a.provider}</dd></div>
                <div><dt>model</dt><dd>{a.model}</dd></div>
                <div><dt>status</dt><dd>{a.status}</dd></div>
                <div><dt>last_seen</dt><dd>{a.last_seen_at ?? lastByAgent[a.agent_id] ?? '—'}</dd></div>
              </dl>
            </li>
          )
        })}
        {agents.length === 0 && <p className="muted">No agents.</p>}
      </ul>
    </section>
  )
}
