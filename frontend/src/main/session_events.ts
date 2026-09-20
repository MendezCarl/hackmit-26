import type { BackendClient } from './backend_client.js';

/** Renderer channel carrying decoded session event envelopes. */
export const SESSION_EVENT_CHANNEL = 'session:event';
/** Renderer channel carrying the event stream's connection state. */
export const SESSION_EVENTS_CONNECTION_CHANNEL = 'session:events-connection';
/** Backend close code meaning the token or membership was rejected. */
const WS_UNAUTHORIZED_CLOSE_CODE = 4401;
const INITIAL_RECONNECT_DELAY_MS = 1_000;
const MAX_RECONNECT_DELAY_MS = 30_000;
const HEARTBEAT_INTERVAL_MS = 15_000;

type RendererEmitter = (channel: string, payload: unknown) => void;

/**
 * Narrows a decoded WebSocket frame to the shared session event envelope.
 *
 * @param value - Parsed JSON frame from the backend.
 * @returns The envelope when every required field is present, otherwise null.
 */
export function parseSessionEventEnvelope(value: unknown): SessionEventEnvelope | null {
  if (typeof value !== 'object' || value === null) return null;
  const candidate = value as Record<string, unknown>;
  if (
    typeof candidate.event_id !== 'string' ||
    typeof candidate.event_type !== 'string' ||
    typeof candidate.session_id !== 'string' ||
    typeof candidate.occurred_at !== 'string' ||
    typeof candidate.sequence_number !== 'number' ||
    typeof candidate.payload !== 'object' ||
    candidate.payload === null
  ) {
    return null;
  }
  return {
    event_id: candidate.event_id,
    event_type: candidate.event_type,
    schema_version:
      typeof candidate.schema_version === 'string' ? candidate.schema_version : undefined,
    session_id: candidate.session_id,
    occurred_at: candidate.occurred_at,
    sequence_number: candidate.sequence_number,
    payload: candidate.payload as Record<string, unknown>,
  };
}

/**
 * Keeps one authenticated WebSocket open to `/ws/v1/sessions/{session_id}` and
 * forwards typed envelopes to the renderer.
 *
 * The bearer token never leaves the main process. Transient disconnects are
 * retried with exponential backoff; an unauthorized close stops retrying until
 * the renderer subscribes again.
 */
export class SessionEventsBridge {
  private socket: WebSocket | null = null;
  private sessionId: string | null = null;
  private reconnectDelayMs = INITIAL_RECONNECT_DELAY_MS;
  private reconnectTimer: NodeJS.Timeout | null = null;
  private heartbeatTimer: NodeJS.Timeout | null = null;

  /**
   * @param client - Backend client holding the current bearer token.
   * @param emit - Sends a payload on a renderer channel.
   */
  constructor(
    private readonly client: BackendClient,
    private readonly emit: RendererEmitter,
  ) {}

  /**
   * Subscribes to one session's events, replacing any previous subscription.
   *
   * @param sessionId - Session to follow, or null to close the stream.
   */
  subscribe(sessionId: string | null): void {
    if (sessionId === this.sessionId && this.socket) return;
    this.closeSocket();
    this.sessionId = sessionId;
    this.reconnectDelayMs = INITIAL_RECONNECT_DELAY_MS;
    if (sessionId) this.connect(sessionId);
  }

  /** Closes the stream and cancels pending reconnects. */
  stop(): void {
    this.sessionId = null;
    this.closeSocket();
  }

  private connect(sessionId: string): void {
    const url = this.client.buildSessionEventsUrl(sessionId);
    if (!url) {
      this.publishConnection(sessionId, 'unauthorized');
      return;
    }
    this.publishConnection(sessionId, 'connecting');
    let socket: WebSocket;
    try {
      socket = new WebSocket(url);
    } catch {
      this.scheduleReconnect(sessionId);
      return;
    }
    this.socket = socket;
    socket.addEventListener('open', () => {
      if (this.socket !== socket) return;
      this.reconnectDelayMs = INITIAL_RECONNECT_DELAY_MS;
      this.publishConnection(sessionId, 'connected');
      this.heartbeatTimer = setInterval(() => {
        if (socket.readyState === WebSocket.OPEN) socket.send('{"type":"client.heartbeat"}');
      }, HEARTBEAT_INTERVAL_MS);
    });
    socket.addEventListener('message', (event) => {
      if (this.socket !== socket) return;
      this.forwardFrame(sessionId, event.data);
    });
    socket.addEventListener('close', (event) => {
      if (this.socket !== socket) return;
      this.clearTimers();
      this.socket = null;
      if (event.code === WS_UNAUTHORIZED_CLOSE_CODE) {
        this.publishConnection(sessionId, 'unauthorized');
        return;
      }
      this.publishConnection(sessionId, 'disconnected');
      this.scheduleReconnect(sessionId);
    });
    socket.addEventListener('error', () => {
      // The matching close event drives reconnect handling.
    });
  }

  private forwardFrame(sessionId: string, frame: unknown): void {
    if (typeof frame !== 'string') return;
    let decoded: unknown;
    try {
      decoded = JSON.parse(frame);
    } catch {
      return;
    }
    const envelope = parseSessionEventEnvelope(decoded);
    if (!envelope || envelope.session_id !== sessionId) return;
    this.emit(SESSION_EVENT_CHANNEL, envelope);
  }

  private scheduleReconnect(sessionId: string): void {
    if (this.sessionId !== sessionId) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (this.sessionId === sessionId) this.connect(sessionId);
    }, this.reconnectDelayMs);
    this.reconnectDelayMs = Math.min(this.reconnectDelayMs * 2, MAX_RECONNECT_DELAY_MS);
  }

  private publishConnection(sessionId: string, state: SessionEventsConnectionState): void {
    const payload: SessionEventsConnectionPayload = { session_id: sessionId, state };
    this.emit(SESSION_EVENTS_CONNECTION_CHANNEL, payload);
  }

  private clearTimers(): void {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.heartbeatTimer) clearInterval(this.heartbeatTimer);
    this.reconnectTimer = null;
    this.heartbeatTimer = null;
  }

  private closeSocket(): void {
    this.clearTimers();
    const socket = this.socket;
    this.socket = null;
    if (socket && socket.readyState !== WebSocket.CLOSED) socket.close();
  }
}
