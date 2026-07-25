import type {
  Agent,
  Capabilities,
  Experiment,
  HealthResponse,
  ReadyResponse,
  RuntimeEvent,
  Session,
} from '../models/types'

const DEFAULT_BASE = '/api/v1'

export class RuntimeClient {
  constructor(private readonly baseUrl: string = DEFAULT_BASE) {}

  private async get<T>(path: string, params?: Record<string, string | number>): Promise<T> {
    const url = new URL(`${this.baseUrl}${path}`, window.location.origin)
    if (params) {
      Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, String(v)))
    }
    const res = await fetch(url.toString())
    if (!res.ok) {
      throw new Error(`GET ${path} failed: ${res.status}`)
    }
    return res.json() as Promise<T>
  }

  health(): Promise<HealthResponse> {
    return fetch('/health').then((r) => {
      if (!r.ok) throw new Error('health check failed')
      return r.json() as Promise<HealthResponse>
    })
  }

  ready(): Promise<ReadyResponse> {
    return fetch('/ready').then((r) => {
      if (!r.ok) throw new Error('ready check failed')
      return r.json() as Promise<ReadyResponse>
    })
  }

  listAgents(): Promise<Agent[]> {
    return this.get<Agent[]>('/agents')
  }

  getSession(sessionId: string): Promise<Session> {
    return this.get<Session>(`/sessions/${sessionId}`)
  }

  getExperiment(experimentId: string): Promise<Experiment> {
    return this.get<Experiment>(`/experiments/${experimentId}`)
  }

  getCapabilities(): Promise<Capabilities> {
    return this.get<Capabilities>('/capabilities')
  }

  async listAllEvents(sessionId: string): Promise<RuntimeEvent[]> {
    const all: RuntimeEvent[] = []
    let offset = 0
    const limit = 1000
    while (true) {
      const page = await this.get<RuntimeEvent[]>(`/sessions/${sessionId}/events`, { limit, offset })
      if (!page.length) break
      all.push(...page)
      if (page.length < limit) break
      offset += limit
    }
    return all
  }

  streamUrl(sessionId: string, replayFrom = '0-0'): string {
    const url = new URL(`${this.baseUrl}/sessions/${sessionId}/stream`, window.location.origin)
    url.searchParams.set('replay_from', replayFrom)
    return url.toString()
  }
}

export function sortEventsByCreatedAt(events: RuntimeEvent[]): RuntimeEvent[] {
  return [...events].sort(
    (a, b) => new Date(a.created_at || a.timestamp || 0).getTime() - new Date(b.created_at || b.timestamp || 0).getTime(),
  )
}

export function mergeEventRecords(sse: Partial<RuntimeEvent>, rest?: RuntimeEvent): RuntimeEvent {
  if (rest) {
    return { ...rest, timestamp: sse.timestamp ?? rest.created_at }
  }
  return {
    event_id: sse.event_id ?? '',
    schema_version: sse.schema_version ?? 'nvs.runtime.event.v1',
    event_type: sse.event_type ?? 'unknown',
    experiment_id: sse.experiment_id ?? null,
    session_id: sse.session_id ?? '',
    agent_id: sse.agent_id ?? null,
    source_provider: sse.source_provider ?? null,
    source_model: sse.source_model ?? null,
    parent_event_id: sse.parent_event_id ?? null,
    sequence_id: sse.sequence_id ?? 0,
    sep_event_type: sse.sep_event_type ?? null,
    payload: sse.payload ?? {},
    forward_status: sse.forward_status ?? 'unknown',
    kernel_run_id: sse.kernel_run_id ?? null,
    created_at: sse.created_at ?? sse.timestamp ?? new Date().toISOString(),
    timestamp: sse.timestamp,
  }
}

export function classifyTimelineGroup(event: RuntimeEvent): import('../models/types').TimelineGroup {
  if (event.forward_status === 'failed') return 'error'
  const t = event.event_type
  if (t === 'session.join' || t === 'session.leave') return 'join'
  if (t.startsWith('sep.')) return 'sep'
  if (t.includes('error') || t.includes('validation')) return 'error'
  return 'other'
}

export function deriveAgentPresence(
  agent: Agent,
  lastEventAt: string | null,
  onlineThresholdMs = 5 * 60 * 1000,
): import('../models/types').AgentPresence {
  if (agent.status === 'deregistered' || agent.status === 'suspended') return 'OFFLINE'
  const seen = lastEventAt ?? agent.last_seen_at
  if (!seen) return 'UNKNOWN'
  const age = Date.now() - new Date(seen).getTime()
  return age <= onlineThresholdMs ? 'ONLINE' : 'UNKNOWN'
}
