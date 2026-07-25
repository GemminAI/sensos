export interface Agent {
  agent_id: string
  display_name: string | null
  provider: string
  model: string
  transport: string
  capabilities: string[]
  status: string
  metadata: Record<string, unknown>
  registered_at: string
  last_seen_at: string | null
}

export interface SessionParticipant {
  agent_id: string
  role?: string
  joined_at?: string
}

export interface Session {
  session_id: string
  label: string | null
  status: string
  kernel_run_ids: Record<string, unknown>
  options: Record<string, unknown>
  created_at: string
  closed_at: string | null
  participants: SessionParticipant[]
}

export interface Experiment {
  experiment_id: string
  session_id: string
  experiment_type: string
  label: string | null
  status: string
  metadata: Record<string, unknown>
  started_at: string
  ended_at: string | null
}

export interface SseEventEnvelope {
  schema_version?: string
  event_id: string
  event_type: string
  experiment_id?: string | null
  session_id: string
  agent_id: string
  source_provider?: string
  source_model?: string | null
  parent_event_id?: string | null
  timestamp: string
  sequence_id?: number
  correlation_id?: string | null
  payload?: Record<string, unknown>
}

export interface RuntimeEvent {
  event_id: string
  schema_version: string
  event_type: string
  experiment_id: string | null
  session_id: string
  agent_id: string | null
  source_provider: string | null
  source_model: string | null
  parent_event_id: string | null
  sequence_id: number
  sep_event_type: string | null
  payload: Record<string, unknown>
  forward_status: string
  kernel_run_id: string | null
  created_at: string
  /** SSE timestamp when not yet hydrated from REST */
  timestamp?: string
}

export interface Capabilities {
  service: string
  version: string
  rfc: string
  features: string[]
  mcp_tools: string[]
  layer3_stubs: string[]
}

export type AgentPresence = 'ONLINE' | 'OFFLINE' | 'UNKNOWN'

export type TimelineGroup = 'lifecycle' | 'join' | 'sep' | 'error' | 'other'

export interface ConnectionConfig {
  sessionId: string
  experimentId: string
}

export interface HealthResponse {
  status: string
  service?: string
}

export interface ReadyResponse {
  status: string
  checks: Record<string, boolean>
}
