import type { SseEventEnvelope } from '../models/types'

export interface ParsedSseMessage {
  id: string
  event: string
  data: SseEventEnvelope
}

export function parseSseChunk(buffer: string): { messages: ParsedSseMessage[]; remainder: string } {
  const messages: ParsedSseMessage[] = []
  const blocks = buffer.split('\n\n')
  const remainder = blocks.pop() ?? ''

  for (const block of blocks) {
    if (!block.trim()) continue
    let id = ''
    let event = 'message'
    let dataLine = ''
    for (const line of block.split('\n')) {
      if (line.startsWith('id:')) id = line.slice(3).trim()
      else if (line.startsWith('event:')) event = line.slice(6).trim()
      else if (line.startsWith('data:')) dataLine += line.slice(5).trim()
    }
    if (!dataLine) continue
    try {
      messages.push({ id, event, data: JSON.parse(dataLine) as SseEventEnvelope })
    } catch {
      // skip malformed
    }
  }
  return { messages, remainder }
}

export type SseConnectionState = 'connecting' | 'open' | 'paused' | 'closed' | 'error'

export interface SseStreamOptions {
  url: string
  onMessage: (msg: ParsedSseMessage) => void
  onStateChange?: (state: SseConnectionState) => void
  reconnectDelayMs?: number
}

export class SseStreamClient {
  private abort: AbortController | null = null
  private paused = false
  private closed = false
  private lastEventId = '0-0'
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null

  constructor(private readonly options: SseStreamOptions) {}

  start(): void {
    this.closed = false
    this.paused = false
    this.connect()
  }

  pause(): void {
    this.paused = true
    this.options.onStateChange?.('paused')
    this.disconnect()
  }

  resume(): void {
    if (this.closed) return
    this.paused = false
    this.connect()
  }

  stop(): void {
    this.closed = true
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    this.disconnect()
    this.options.onStateChange?.('closed')
  }

  getLastEventId(): string {
    return this.lastEventId
  }

  private disconnect(): void {
    this.abort?.abort()
    this.abort = null
  }

  private connect(): void {
    if (this.closed || this.paused) return
    this.disconnect()
    this.options.onStateChange?.('connecting')
    this.abort = new AbortController()

    const url = new URL(this.options.url)
    if (this.lastEventId !== '0-0') {
      url.searchParams.set('replay_from', this.lastEventId)
    }

    fetch(url.toString(), { signal: this.abort.signal, headers: { Accept: 'text/event-stream' } })
      .then(async (res) => {
        if (!res.ok || !res.body) throw new Error(`SSE ${res.status}`)
        this.options.onStateChange?.('open')
        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const { messages, remainder } = parseSseChunk(buffer)
          buffer = remainder
          for (const msg of messages) {
            if (msg.id) this.lastEventId = msg.id
            this.options.onMessage(msg)
          }
        }
        if (!this.closed && !this.paused) this.scheduleReconnect()
      })
      .catch((err) => {
        if (this.abort?.signal.aborted) return
        this.options.onStateChange?.('error')
        if (!this.closed && !this.paused) this.scheduleReconnect()
        console.warn('SSE error', err)
      })
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    const delay = this.options.reconnectDelayMs ?? 2000
    this.reconnectTimer = setTimeout(() => this.connect(), delay)
  }
}
