import type { RuntimeEvent, Session } from '../models/types'
import { classifyTimelineGroup } from '../services/runtimeClient'

interface Props {
  events: RuntimeEvent[]
  session: Session | null
}

const GROUP_LABELS: Record<string, string> = {
  lifecycle: 'Lifecycle',
  join: 'Join / Leave',
  sep: 'SEP Events',
  error: 'Errors',
  other: 'Other',
}

export function SessionTimeline({ events, session }: Props) {
  const grouped = events.reduce<Record<string, RuntimeEvent[]>>((acc, e) => {
    const g = classifyTimelineGroup(e)
    acc[g] = acc[g] ?? []
    acc[g].push(e)
    return acc
  }, {})

  return (
    <section className="panel timeline">
      <h2>Session Timeline</h2>
      {session && (
        <p className="muted">
          {session.label ?? session.session_id} · {session.status} · {session.participants.length} participants
        </p>
      )}
      <div className="timeline-groups">
        {Object.entries(grouped).map(([group, items]) => (
          <div key={group} className="timeline-group">
            <h3>{GROUP_LABELS[group] ?? group}</h3>
            <ul>
              {items.map((e) => (
                <li key={e.event_id}>
                  <time>{e.created_at}</time>
                  <span className="tag">{e.sep_event_type ?? e.event_type}</span>
                  <span className="muted">agent {e.agent_id?.slice(0, 8)}</span>
                  {e.forward_status && <span className={`fwd ${e.forward_status}`}>{e.forward_status}</span>}
                </li>
              ))}
            </ul>
          </div>
        ))}
        {events.length === 0 && <p className="muted">No events loaded.</p>}
      </div>
    </section>
  )
}
