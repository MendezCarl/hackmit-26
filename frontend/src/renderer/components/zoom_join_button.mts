import { escapeHtml } from './html_text.mjs';

export type ZoomJoinButtonModel = {
  session: Pick<LectureSession, 'session_id' | 'zoom_join_url' | 'status'>;
  variant?: 'primary' | 'secondary';
};

/**
 * Decides whether a session currently offers a Zoom meeting to join.
 *
 * @param session - Session whose owner may have shared a validated join link.
 * @returns True when the session is active and carries a join URL.
 */
export function hasZoomJoinLink(
  session: Pick<LectureSession, 'zoom_join_url' | 'status'> | null | undefined,
): boolean {
  return Boolean(session && session.status === 'active' && session.zoom_join_url);
}

/**
 * Renders the "Join Zoom meeting" control for an active session.
 *
 * Only the session id is embedded in the markup; the renderer resolves the
 * validated URL from state and the main process re-validates it before opening.
 *
 * @param model - Session plus optional button style.
 * @returns Button markup, or an empty string when the session has no join link.
 */
export function ZoomJoinButton(model: ZoomJoinButtonModel): string {
  if (!hasZoomJoinLink(model.session)) return '';
  const className = model.variant === 'secondary' ? 'secondary-button' : 'primary-button';
  return `<button class="${className} zoom-join-button" type="button" data-zoom-join="${escapeHtml(model.session.session_id)}">Join Zoom meeting</button>`;
}
