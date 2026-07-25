import type { ConnectionConfig } from '../models/types'

interface Props {
  config: ConnectionConfig
  health: string
  streamState: string
  error: string | null
  onChange: (config: ConnectionConfig) => void
  onConnect: () => void
}

export function ConnectionPanel({ config, health, streamState, error, onChange, onConnect }: Props) {
  return (
    <section className="panel connection-panel">
      <h2>Sessions</h2>
      <label>
        Session ID
        <input
          value={config.sessionId}
          onChange={(e) => onChange({ ...config, sessionId: e.target.value.trim() })}
          placeholder="uuid"
        />
      </label>
      <h2>Experiments</h2>
      <label>
        Experiment ID
        <input
          value={config.experimentId}
          onChange={(e) => onChange({ ...config, experimentId: e.target.value.trim() })}
          placeholder="uuid (optional)"
        />
      </label>
      <button type="button" className="btn primary" onClick={onConnect}>
        Connect
      </button>
      <div className="status-row">
        <span className={`badge ${health === 'ok' ? 'ok' : 'warn'}`}>Runtime: {health}</span>
        <span className="badge">SSE: {streamState}</span>
      </div>
      {error && <p className="error-text">{error}</p>}
    </section>
  )
}
