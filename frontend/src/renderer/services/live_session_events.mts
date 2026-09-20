/**
 * Renderer-side handling of the authenticated session event stream.
 *
 * The main process owns the WebSocket and bearer token; this module decides
 * which session to follow and folds `transcript.chunk.created` envelopes into
 * the transcript state so Zoom realtime transcripts appear without a refresh.
 */
import {
  getBackendSessionState,
  setLiveEventsConnection,
  upsertTranscriptChunk,
} from './backend_session_state.mjs';

/** Event type emitted by the backend for each accepted transcript chunk. */
export const TRANSCRIPT_CHUNK_CREATED_EVENT = 'transcript.chunk.created';

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
 *
 * @param envelope - Envelope forwarded by the main process.
 * @returns True when the transcript changed and the page should repaint.
 */
export function applySessionEvent(envelope: SessionEventEnvelope): boolean {
  const activeSessionId = getBackendSessionState().activeSession?.session_id;
  if (envelope.session_id !== activeSessionId) return false;
  if (envelope.event_type !== TRANSCRIPT_CHUNK_CREATED_EVENT) return false;
  const chunk = parseTranscriptChunkPayload(envelope.payload);
  if (!chunk || chunk.session_id !== activeSessionId) return false;
  return upsertTranscriptChunk(chunk);
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
 * @returns Disposer removing both listeners.
 */
export function bindLiveSessionEvents(
  onTranscriptChanged: () => void,
  onConnectionChanged: () => void,
): () => void {
  const disposeEvents = window.bloomDesktop.onSessionEvent((envelope) => {
    if (applySessionEvent(envelope)) onTranscriptChanged();
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
