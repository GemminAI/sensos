import type { Experiment, RuntimeEvent, Session } from '../models/types'

interface Props {
  experiment: Experiment | null
  session: Session | null
  events: RuntimeEvent[]
  experimentId: string
}

export function ExperimentExplorer({ experiment, session, events, experimentId }: Props) {
  const scoped = experimentId
    ? events.filter((e) => e.experiment_id === experimentId)
    : events
  const participantIds = new Set(scoped.map((e) => e.agent_id).filter(Boolean))

  return (
    <section className="panel experiment-explorer">
      <h2>Experiment Explorer</h2>
      {!experimentId && <p className="muted">Enter an Experiment ID in the left panel.</p>}
      {experiment && (
        <dl className="kv">
          <div><dt>experiment_id</dt><dd className="mono">{experiment.experiment_id}</dd></div>
          <div><dt>status</dt><dd>{experiment.status}</dd></div>
          <div><dt>type</dt><dd>{experiment.experiment_type}</dd></div>
          <div><dt>label</dt><dd>{experiment.label ?? '—'}</dd></div>
          <div><dt>session_id</dt><dd className="mono">{experiment.session_id}</dd></div>
        </dl>
      )}
      <div className="stats">
        <div className="stat">
          <span className="stat-value">{participantIds.size || session?.participants.length || 0}</span>
          <span className="stat-label">participants</span>
        </div>
        <div className="stat">
          <span className="stat-value">{scoped.length}</span>
          <span className="stat-label">events</span>
        </div>
      </div>
    </section>
  )
}
