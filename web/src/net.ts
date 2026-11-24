import type { ClientMessage, ServerEvent } from './protocol'
import type { Conn } from './store'

export interface Transport {
  send(m: ClientMessage): boolean
  audio(b: ArrayBuffer): void
  setChannels(c: 1 | 2): void
  close(): void
}

interface Handlers {
  conn(c: Conn): void
  event(e: ServerEvent): void
  /** Messages to replay after every (re)connect, e.g. the voice-memory opt-in. */
  onOpen(): ClientMessage[]
}

const MAX_BUFFER_BYTES = 6 * 16000 * 2 * 2 // ~6 s of stereo audio kept while offline

export function createLink(h: Handlers): Transport {
  let ws: WebSocket | null = null
  let closed = false
  let attempt = 0
  let timer = 0
  let channels: 1 | 2 | null = null
  let helloSent = false
  let pending: ArrayBuffer[] = []
  let pendingBytes = 0

  const sendHello = () => {
    if (!ws || ws.readyState !== WebSocket.OPEN || helloSent || !channels) return
    ws.send(JSON.stringify({ type: 'hello', sample_rate: 16000, channels }))
    helloSent = true
    for (const m of h.onOpen()) ws.send(JSON.stringify(m))
    for (const b of pending) ws.send(b)
    pending = []
    pendingBytes = 0
  }

  const connect = () => {
    window.clearTimeout(timer)
    helloSent = false
    h.conn(attempt === 0 ? 'connecting' : 'reconnecting')
    const url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`
    const sock = new WebSocket(url)
    sock.binaryType = 'arraybuffer'
    ws = sock
    sock.onopen = () => { attempt = 0; h.conn('open'); sendHello() }
    sock.onmessage = (m) => {
      if (typeof m.data !== 'string') return
      try { h.event(JSON.parse(m.data) as ServerEvent) } catch { /* ignore malformed frame */ }
    }
    sock.onclose = () => {
      if (ws !== sock || closed) return
      h.conn('reconnecting')
      const delay = Math.min(8000, 500 * 2 ** attempt++) * (0.7 + Math.random() * 0.6)
      timer = window.setTimeout(connect, delay)
    }
    sock.onerror = () => sock.close()
  }

  // Phones suspend sockets in the background: retry straight away when the page is usable again.
  const wake = () => {
    if (closed || document.visibilityState === 'hidden') return
    if (!ws || ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING) { attempt = 0; connect() }
  }
  window.addEventListener('online', wake)
  document.addEventListener('visibilitychange', wake)
  connect()

  return {
    send(m) {
      if (!ws || ws.readyState !== WebSocket.OPEN) return false
      ws.send(JSON.stringify(m))
      return true
    },
    audio(b) {
      if (ws && ws.readyState === WebSocket.OPEN && helloSent) { ws.send(b); return }
      pending.push(b)
      pendingBytes += b.byteLength
      while (pendingBytes > MAX_BUFFER_BYTES && pending.length) pendingBytes -= pending.shift()!.byteLength
    },
    setChannels(c) { channels = c; sendHello() },
    close() {
      closed = true
      window.clearTimeout(timer)
      window.removeEventListener('online', wake)
      document.removeEventListener('visibilitychange', wake)
      ws?.close()
    },
  }
}
