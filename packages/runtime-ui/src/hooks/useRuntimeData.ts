import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ConnectionConfig, RuntimeEvent } from '../models/types'
import { RuntimeClient, mergeEventRecords, sortEventsByCreatedAt } from '../services/runtimeClient'
import { SseStreamClient, type SseConnectionState } from '../services/sseClient'

export function useRuntimeData(config: ConnectionConfig) {
  const client = useMemo(() => new RuntimeClient(), [])
  const [health, setHealth] = useState<string>('unknown')
  const [agents, setAgents] = useState<Awaited<ReturnType<RuntimeClient['listAgents']>>>([])
  const [session, setSession] = useState<Awaited<ReturnType<RuntimeClient['getSession']>> | null>(null)
  const [experiment, setExperiment] = useState<Awaited<ReturnType<RuntimeClient['getExperiment']>> | null>(null)
  const [capabilities, setCapabilities] = useState<Awaited<ReturnType<RuntimeClient['getCapabilities']>> | null>(null)
  const [events, setEvents] = useState<RuntimeEvent[]>([])
  const [streamState, setStreamState] = useState<SseConnectionState>('closed')
  const [paused, setPaused] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const streamRef = useRef<SseStreamClient | null>(null)
  const eventsMapRef = useRef<Map<string, RuntimeEvent>>(new Map())

  const hydrate = useCallback(async () => {
    if (!config.sessionId) return
    setError(null)
    try {
      const [h, a, s, c, ev] = await Promise.all([
        client.health(),
        client.listAgents(),
        client.getSession(config.sessionId),
        client.getCapabilities(),
        client.listAllEvents(config.sessionId),
      ])
      setHealth(h.status)
      setAgents(a)
      setSession(s)
      setCapabilities(c)
      const map = new Map<string, RuntimeEvent>()
      ev.forEach((e) => map.set(e.event_id, e))
      eventsMapRef.current = map
      setEvents(sortEventsByCreatedAt([...map.values()]))
      if (config.experimentId) {
        const exp = await client.getExperiment(config.experimentId)
        setExperiment(exp)
      } else {
        setExperiment(null)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Connection failed')
    }
  }, [client, config.sessionId, config.experimentId])

  const onStreamMessage = useCallback((data: import('../services/sseClient').ParsedSseMessage) => {
    const existing = eventsMapRef.current.get(data.data.event_id)
    const merged = mergeEventRecords(
      {
        event_id: data.data.event_id,
        event_type: data.data.event_type,
        experiment_id: data.data.experiment_id ?? null,
        session_id: data.data.session_id,
        agent_id: data.data.agent_id,
        parent_event_id: data.data.parent_event_id ?? null,
        timestamp: data.data.timestamp,
        sequence_id: data.data.sequence_id,
        payload: data.data.payload,
      },
      existing,
    )
    eventsMapRef.current.set(merged.event_id, merged)
    setEvents(sortEventsByCreatedAt([...eventsMapRef.current.values()]))
  }, [])

  useEffect(() => {
    hydrate()
  }, [hydrate])

  useEffect(() => {
    if (!config.sessionId || paused) {
      streamRef.current?.stop()
      return
    }
    const stream = new SseStreamClient({
      url: client.streamUrl(config.sessionId, '0-0'),
      onMessage: onStreamMessage,
      onStateChange: setStreamState,
    })
    streamRef.current = stream
    stream.start()
    return () => stream.stop()
  }, [client, config.sessionId, paused, onStreamMessage])

  const togglePause = useCallback(() => {
    setPaused((p) => {
      const next = !p
      if (next) streamRef.current?.pause()
      else streamRef.current?.resume()
      return next
    })
  }, [])

  const filteredEvents = useMemo(() => {
    if (!config.experimentId) return events
    return events.filter((e) => e.experiment_id === config.experimentId)
  }, [events, config.experimentId])

  return {
    health,
    agents,
    session,
    experiment,
    capabilities,
    events: filteredEvents,
    allEvents: events,
    streamState,
    paused,
    error,
    togglePause,
    refresh: hydrate,
  }
}
