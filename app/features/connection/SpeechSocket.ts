/** The app's single WebSocket to the speech server: connects, says hello, reconnects with backoff. */
import { ClientMessage, isServerMessage, ReadyMessage, ServerMessage } from './protocol';

export type ConnectionStatus = 'unconfigured' | 'connecting' | 'waking' | 'ready' | 'offline' | 'unauthorised';

export type SocketOptions = {
  serverUrl: string;
  token: string;
  /** Builds the hello message, read fresh on every (re)connect so it carries current settings. */
  hello: () => ClientMessage;
};

type Listener = (message: ServerMessage) => void;

const PING_INTERVAL_MS = 15_000;
// After this long without `ready`, the server is probably cold-starting; say so.
const WAKING_AFTER_MS = 1_500;
const BACKOFF_MS = [1_000, 2_000, 4_000, 8_000, 15_000];
// The server closes with this code when the token is wrong; retrying would not help.
const UNAUTHORISED_CLOSE_CODE = 4401;

export class SpeechSocket {
  private ws: WebSocket | null = null;
  private listeners = new Set<Listener>();
  private statusListeners = new Set<(status: ConnectionStatus) => void>();
  private attempt = 0;
  private timers: ReturnType<typeof setTimeout>[] = [];
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  private stopped = false;
  status: ConnectionStatus = 'connecting';
  ready: ReadyMessage | null = null;

  constructor(private options: SocketOptions) {}

  /** Opens the connection, and warms the server over HTTP in parallel. */
  start(): void {
    if (!this.options.serverUrl || !this.options.token) {
      this.setStatus('unconfigured');
      return;
    }
    this.stopped = false;
    void this.wake();
    this.open();
  }

  /** Closes for good; no reconnects follow. */
  stop(): void {
    this.stopped = true;
    this.clearTimers();
    this.ws?.close();
    this.ws = null;
  }

  /** Sends a JSON message; returns false when not connected. */
  send(message: ClientMessage): boolean {
    if (this.ws?.readyState !== WebSocket.OPEN) return false;
    this.ws.send(JSON.stringify(message));
    return true;
  }

  /** Sends one binary audio frame; returns false when not connected. */
  sendAudio(frame: ArrayBuffer): boolean {
    if (this.ws?.readyState !== WebSocket.OPEN) return false;
    this.ws.send(frame);
    return true;
  }

  /** Subscribes to every server message; returns the unsubscribe function. */
  onMessage(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  /** Subscribes to connection status changes; returns the unsubscribe function. */
  onStatus(listener: (status: ConnectionStatus) => void): () => void {
    this.statusListeners.add(listener);
    return () => this.statusListeners.delete(listener);
  }

  private async wake(): Promise<void> {
    try {
      await fetch(`${this.options.serverUrl}/wake`, { method: 'POST', headers: { Authorization: `Bearer ${this.options.token}` } });
    } catch {
      // The WebSocket reports connection problems; the wake call only shortens a cold start.
    }
  }

  private open(): void {
    this.setStatus('connecting');
    const url = `${this.options.serverUrl.replace(/^http/, 'ws')}/ws?token=${encodeURIComponent(this.options.token)}`;
    const ws = new WebSocket(url);
    ws.binaryType = 'arraybuffer';
    this.ws = ws;
    const waking = setTimeout(() => this.status !== 'ready' && this.setStatus('waking'), WAKING_AFTER_MS);
    this.timers.push(waking);

    ws.onopen = () => ws.send(JSON.stringify(this.options.hello()));
    ws.onmessage = (event) => this.receive(event.data);
    ws.onclose = (event) => this.closed(event.code);
    ws.onerror = () => undefined; // onclose follows every error and handles it.
  }

  private receive(data: unknown): void {
    if (typeof data !== 'string') return;
    let parsed: unknown;
    try {
      parsed = JSON.parse(data);
    } catch {
      return;
    }
    if (!isServerMessage(parsed)) return;
    if (parsed.type === 'ready') {
      this.ready = parsed as ReadyMessage;
      this.attempt = 0;
      this.setStatus('ready');
      this.startPing();
    }
    this.listeners.forEach((listener) => listener(parsed as ServerMessage));
  }

  private closed(code: number): void {
    this.clearTimers();
    this.ws = null;
    if (this.stopped) return;
    if (code === UNAUTHORISED_CLOSE_CODE) {
      this.setStatus('unauthorised');
      return;
    }
    this.setStatus('offline');
    const delay = BACKOFF_MS[Math.min(this.attempt, BACKOFF_MS.length - 1)];
    this.attempt += 1;
    this.timers.push(setTimeout(() => this.open(), delay));
  }

  private startPing(): void {
    if (this.pingTimer) clearInterval(this.pingTimer);
    this.pingTimer = setInterval(() => this.send({ type: 'ping' }), PING_INTERVAL_MS);
  }

  private clearTimers(): void {
    this.timers.forEach(clearTimeout);
    this.timers = [];
    if (this.pingTimer) clearInterval(this.pingTimer);
    this.pingTimer = null;
  }

  private setStatus(status: ConnectionStatus): void {
    if (status === this.status) return;
    this.status = status;
    this.statusListeners.forEach((listener) => listener(status));
  }
}
