import { WS_URL } from '../api'

type Handler = (message: any) => void

export class GameSocket {
  private ws: WebSocket | null = null
  private timer: number | null = null
  private attempts = 0
  private closedByUser = false

  constructor(
    private code: string,
    private token: string,
    private onMessage: Handler,
    private onStatus: (connected: boolean) => void,
  ) {}

  connect() {
    this.closedByUser = false
    const url = `${WS_URL}/ws?code=${encodeURIComponent(this.code)}&token=${encodeURIComponent(this.token)}`
    const ws = new WebSocket(url)
    this.ws = ws
    ws.onopen = () => {
      this.attempts = 0
      this.onStatus(true)
    }
    ws.onmessage = event => {
      try { this.onMessage(JSON.parse(event.data)) } catch { /* ignore malformed */ }
    }
    ws.onclose = () => {
      this.onStatus(false)
      if (!this.closedByUser) this.scheduleReconnect()
    }
    ws.onerror = () => ws.close()
  }

  private scheduleReconnect() {
    if (this.timer) return
    const delay = Math.min(1000 * Math.pow(1.6, this.attempts), 8000)
    this.attempts++
    this.timer = window.setTimeout(() => {
      this.timer = null
      this.connect()
    }, delay)
  }

  send(action: string, payload: Record<string, unknown> = {}) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action, ...payload }))
      return true
    }
    return false
  }

  close() {
    this.closedByUser = true
    if (this.timer) window.clearTimeout(this.timer)
    this.ws?.close()
  }
}
