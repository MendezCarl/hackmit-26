import { escapeHtml } from './html_text.mjs';
import { ZoomJoinButton } from './zoom_join_button.mjs';

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
 * Splits the professor's single "Zoom meeting" field into the RTMS request body.
 *
 * A pasted https link is sent as `zoom_join_url` so the backend validates it and
 * derives the meeting number; anything else is treated as a bare meeting id.
 *
 * @param value - Raw text from the Zoom meeting input.
 * @returns Request carrying exactly one of the two meeting references.
 */
export function buildZoomMeetingLinkRequest(value: string): StartZoomRtmsRequest {
  const trimmed = value.trim();
  return /^https?:\/\//i.test(trimmed)
    ? { zoom_join_url: trimmed }
    : { zoom_meeting_id: trimmed };
}

/**
 * Renders the professor control for feeding a Zoom meeting's realtime
 * transcript into an active lecture session.
 *
 * @param model - Active session and its latest Zoom link status.
 * @returns Panel markup with a join-link/meeting-id form, live status line and,
 *   once a join link is stored, a Join Zoom meeting button.
 */
export function ZoomLiveTranscriptPanel(model: ZoomLiveTranscriptPanelModel): string {
  const status = model.status;
  const isConfigured = status?.status !== 'not_configured';
  const meetingReference =
    model.session.zoom_join_url ?? status?.zoom_meeting_id ?? model.session.zoom_meeting_id ?? '';
  const statusKey = status?.status ?? 'loading';
  return `
    <section class="panel zoom-live-transcript" data-zoom-live-transcript>
      <div>
        <p class="eyebrow">Zoom realtime transcript</p>
        <p class="zoom-live-transcript__status" data-zoom-rtms-status="${escapeHtml(statusKey)}" aria-live="polite">${escapeHtml(describeZoomRtmsStatus(status))}</p>
        ${ZoomJoinButton({ session: model.session, variant: 'secondary' })}
      </div>
      ${
        isConfigured
          ? `<form class="zoom-live-transcript__form" data-zoom-rtms-form>
        <label>Zoom join link or meeting id<input type="text" name="zoom_meeting_reference" maxlength="2048" required value="${escapeHtml(meetingReference)}" placeholder="https://zoom.us/j/123456789?pwd=…" /></label>
        <button class="secondary-button" type="submit">${status?.zoom_meeting_id ? 'Relink meeting' : 'Link meeting'}</button>
        <p class="form-message" data-zoom-rtms-message aria-live="polite"></p>
      </form>`
          : ''
      }
    </section>
  `;
}
