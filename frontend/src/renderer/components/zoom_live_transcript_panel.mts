import { escapeHtml } from './html_text.mjs';

export type ZoomLiveTranscriptPanelModel = {
  session: LectureSession;
  status: ZoomRtmsStatus | null;
};

const STATUS_LABELS: Record<ZoomRtmsStreamStatus, string> = {
  not_configured: 'Zoom realtime transcripts are not configured on this Bloom service.',
  not_linked: 'Not linked to a Zoom meeting yet.',
  awaiting_stream: 'Linked — waiting for Zoom to start the transcript stream.',
  connecting: 'Connecting to the Zoom transcript stream…',
  streaming: 'Live — Zoom captions are flowing into this lecture.',
  stopped: 'Zoom transcript stream ended.',
  failed: 'Zoom transcript stream failed.',
};

/**
 * Formats the Zoom link state as a short human-readable line.
 *
 * @param status - Latest status from the backend, or null while loading.
 * @returns Sentence describing the stream lifecycle and chunk count.
 */
export function describeZoomRtmsStatus(status: ZoomRtmsStatus | null): string {
  if (!status) return 'Checking Zoom transcript status…';
  const parts = [STATUS_LABELS[status.status]];
  if (status.transcript_chunk_count) {
    parts.push(`${status.transcript_chunk_count} transcript chunk(s) received.`);
  }
  if (status.last_error) parts.push(status.last_error);
  return parts.join(' ');
}

/**
 * Renders the professor control for feeding a Zoom meeting's realtime
 * transcript into an active lecture session.
 *
 * @param model - Active session and its latest Zoom link status.
 * @returns Panel markup with a meeting-id form and live status line.
 */
export function ZoomLiveTranscriptPanel(model: ZoomLiveTranscriptPanelModel): string {
  const status = model.status;
  const isConfigured = status?.status !== 'not_configured';
  const meetingId = status?.zoom_meeting_id ?? model.session.zoom_meeting_id ?? '';
  const statusKey = status?.status ?? 'loading';
  return `
    <section class="panel zoom-live-transcript" data-zoom-live-transcript>
      <div>
        <p class="eyebrow">Zoom realtime transcript</p>
        <p class="zoom-live-transcript__status" data-zoom-rtms-status="${escapeHtml(statusKey)}" aria-live="polite">${escapeHtml(describeZoomRtmsStatus(status))}</p>
      </div>
      ${
        isConfigured
          ? `<form class="zoom-live-transcript__form" data-zoom-rtms-form>
        <label>Zoom meeting id<input type="text" name="zoom_meeting_id" maxlength="128" required value="${escapeHtml(meetingId)}" placeholder="e.g. 123456789" /></label>
        <button class="secondary-button" type="submit">${status?.zoom_meeting_id ? 'Relink meeting' : 'Link meeting'}</button>
        <p class="form-message" data-zoom-rtms-message aria-live="polite"></p>
      </form>`
          : ''
      }
    </section>
  `;
}
