import { useEffect, useRef } from 'react'
import type { RuntimeEvent } from '../models/types'

interface Props {
  events: RuntimeEvent[]
  paused: boolean
  streamState: string
  onTogglePause: () => void
}

export function LiveEventStream({ events, paused, streamState, onTogglePause }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const streamEvents = [...events].reverse().slice(0, 50)

  useEffect(() => {
    if (!paused) bottomRef.current?.scrollIntoView?.({ behavior: 'smooth' })
  }, [events.length, paused])

  return (
    <section className="panel live-stream">
      <div className="panel-header">
        <h2>Live Event Stream</h2>
        <div className="actions">
          <span className="badge">{streamState}</span>
          <button type="button" className="btn" onClick={onTogglePause}>
            {paused ? 'Resume' : 'Pause'}
          </button>
        </div>
      </div>
      <div className="stream-list">
        {streamEvents.length === 0 && <p className="muted">Waiting for events…</p>}
        {streamEvents.map((e) => (
          <article key={e.event_id} className="stream-item" data-event-id={e.event_id}>
            <header>
              <time>{e.timestamp ?? e.created_at}</time>
              <span className="tag">{e.event_type}</span>
            </header>
            <dl className="kv">
              <div><dt>agent</dt><dd>{e.agent_id?.slice(0, 8)}…</dd></div>
              <div><dt>session</dt><dd>{e.session_id?.slice(0, 8)}…</dd></div>
              <div><dt>experiment</dt><dd>{e.experiment_id?.slice(0, 8) ?? '—'}…</dd></div>
            </dl>
          </article>
        ))}
        <div ref={bottomRef} />
      </div>
    </section>
  )
}
