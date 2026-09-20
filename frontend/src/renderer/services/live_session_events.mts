/**
 * Renderer-side handling of the authenticated session event stream.
 *
 * The main process owns the WebSocket and bearer token; this module decides
 * which session to follow, folds `transcript.chunk.created` envelopes into
 * the transcript state so Zoom realtime transcripts appear without a refresh,
 * and marks the active session ended when the professor closes it.
 */
import {
  getBackendSessionState,
  setActiveSession,
  setLiveEventsConnection,
  upsertTranscriptChunk,
} from './backend_session_state.mjs';

/** Event type emitted by the backend for each accepted transcript chunk. */
export const TRANSCRIPT_CHUNK_CREATED_EVENT = 'transcript.chunk.created';
/** Event type emitted once when the owner ends the session. */
export const SESSION_ENDED_EVENT = 'session.ended';

/** Outcome of applying one live envelope to renderer state. */
export type SessionEventEffect = 'ignored' | 'transcript_changed' | 'session_ended';

const TRANSCRIPT_SOURCES: readonly TranscriptSource[] = [
  'zoom_rtms',
  'local_transcription',
  'external_transcription',
];

let subscribedSessionId: string | null = null;

/**
 * Narrows an event payload to a transcript chunk.
 *
 * @param payload - Envelope payload for a `transcript.chunk.created` event.
 * @returns The typed chunk, or null when required fields are missing.
 */
export function parseTranscriptChunkPayload(
  payload: Record<string, unknown>,
): TranscriptChunk | null {
  const { chunk_id, session_id, start_ms, end_ms, text, speaker_label, source, is_final, revision } =
    payload;
  if (
    typeof chunk_id !== 'string' ||
    typeof session_id !== 'string' ||
    typeof start_ms !== 'number' ||
    typeof end_ms !== 'number' ||
    typeof text !== 'string' ||
    typeof source !== 'string' ||
    !TRANSCRIPT_SOURCES.includes(source as TranscriptSource)
  ) {
    return null;
  }
  return {
    chunk_id,
    session_id,
    start_ms,
    end_ms,
    text,
    speaker_label: typeof speaker_label === 'string' ? speaker_label : null,
    source: source as TranscriptSource,
    is_final: typeof is_final === 'boolean' ? is_final : true,
    revision: typeof revision === 'number' ? revision : 1,
  };
}

/**
 * Applies one envelope from the session event stream to renderer state.
 *
 * Events for sessions other than the active one are ignored so a stale
 * subscription can never leak transcript text into another lecture's view.
 * A `session.ended` envelope flips the active session to `ended` (using the
 * backend's `ended_at` when present) so the UI leaves its live state at once.
 *
 * @param envelope - Envelope forwarded by the main process.
 * @returns What changed, so the caller can repaint or re-route.
 */
export function applySessionEvent(envelope: SessionEventEnvelope): SessionEventEffect {
  const active = getBackendSessionState().activeSession;
  if (!active || envelope.session_id !== active.session_id) return 'ignored';
  if (envelope.event_type === SESSION_ENDED_EVENT) {
    if (active.status === 'ended') return 'ignored';
    const endedAt = envelope.payload.ended_at;
    setActiveSession({
      ...active,
      status: 'ended',
      ended_at: typeof endedAt === 'string' ? endedAt : envelope.occurred_at,
    });
    return 'session_ended';
  }
  if (envelope.event_type !== TRANSCRIPT_CHUNK_CREATED_EVENT) return 'ignored';
  const chunk = parseTranscriptChunkPayload(envelope.payload);
  if (!chunk || chunk.session_id !== active.session_id) return 'ignored';
  return upsertTranscriptChunk(chunk) ? 'transcript_changed' : 'ignored';
}

/**
 * Points the main-process event stream at the active session (or closes it).
 *
 * @param session - Current active lecture session, if any.
 */
export function syncLiveSessionSubscription(session: LectureSession | null): void {
  const nextSessionId = session && session.status !== 'ended' ? session.session_id : null;
  if (nextSessionId === subscribedSessionId) return;
  subscribedSessionId = nextSessionId;
  if (!nextSessionId) setLiveEventsConnection(null);
  window.bloomDesktop.subscribeSessionEvents(nextSessionId);
}

/**
 * Registers the renderer listeners for stream events and connection changes.
 *
 * @param onTranscriptChanged - Called after a live chunk changed the transcript.
 * @param onConnectionChanged - Called after the stream connection state changed.
 * @param onSessionEnded - Called after the active session was marked ended.
 * @returns Disposer removing both listeners.
 */
export function bindLiveSessionEvents(
  onTranscriptChanged: () => void,
  onConnectionChanged: () => void,
  onSessionEnded: () => void,
): () => void {
  const disposeEvents = window.bloomDesktop.onSessionEvent((envelope) => {
    const effect = applySessionEvent(envelope);
    if (effect === 'transcript_changed') onTranscriptChanged();
    else if (effect === 'session_ended') onSessionEnded();
  });
  const disposeConnection = window.bloomDesktop.onSessionEventsConnection((payload) => {
    if (payload.session_id !== subscribedSessionId) return;
    setLiveEventsConnection(payload);
    onConnectionChanged();
  });
  return () => {
    disposeEvents();
    disposeConnection();
  };
}
