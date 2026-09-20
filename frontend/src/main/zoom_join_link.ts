/**
 * Main-process guard for opening Zoom join links.
 *
 * The backend already validates `zoom_join_url`, but the renderer is untrusted
 * so every URL is re-checked here before it reaches `shell.openExternal`.
 */

/** Apex domains Zoom owns; any subdomain of these is accepted. */
export const ZOOM_JOIN_HOSTS: readonly string[] = ['zoom.us', 'zoom.com', 'zoomgov.com'];

const MAX_JOIN_URL_LENGTH = 2048;
const MEETING_PATH = /^\/(?:j|w|s|wc\/join|wc\/\d+\/join)\/(\d{9,11})\/?$/;
const PERSONAL_PATH = /^\/my\/[A-Za-z0-9._-]{1,64}\/?$/;
const PASSCODE = /^[A-Za-z0-9._-]{1,128}$/;

export type ZoomJoinTarget = {
  /** Normalised https link, safe to open in the default browser. */
  webUrl: string;
  /** `zoommtg://` deep link into the Zoom desktop client, when the URL names a meeting. */
  deepLink: string | null;
};

/** Where the link ended up being opened. */
export type ZoomJoinOutcome = 'desktop' | 'browser' | 'rejected';

/**
 * Validates a Zoom join URL and derives the targets Bloom is willing to open.
 *
 * @param raw - Untrusted value received from the renderer.
 * @returns Web and deep-link targets, or null when the URL must not be opened.
 */
export function resolveZoomJoinTarget(raw: unknown): ZoomJoinTarget | null {
  if (typeof raw !== 'string' || !raw || raw.length > MAX_JOIN_URL_LENGTH) return null;
  if (/[\s\u0000-\u001f]/.test(raw)) return null;
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    return null;
  }
  if (url.protocol !== 'https:' || url.username || url.password || url.port) return null;
  const host = url.hostname.toLowerCase();
  const apex = ZOOM_JOIN_HOSTS.find((domain) => host === domain || host.endsWith(`.${domain}`));
  if (!apex) return null;
  const meeting = MEETING_PATH.exec(url.pathname);
  if (!meeting && !PERSONAL_PATH.test(url.pathname)) return null;
  const passcode = url.searchParams.get('pwd');
  if (url.searchParams.getAll('pwd').length > 1) return null;
  if (passcode !== null && !PASSCODE.test(passcode)) return null;

  const query = passcode ? `?pwd=${encodeURIComponent(passcode)}` : '';
  const webUrl = `https://${host}${url.pathname}${query}`;
  const deepLink = meeting
    ? `zoommtg://${apex}/join?action=join&confno=${meeting[1]}${passcode ? `&pwd=${encodeURIComponent(passcode)}` : ''}`
    : null;
  return { webUrl, deepLink };
}

/**
 * Opens a Zoom join link, preferring the desktop client and falling back to the browser.
 *
 * @param raw - Untrusted join URL from the renderer.
 * @param openExternal - `shell.openExternal` or a test double.
 * @returns `desktop` when the deep link opened, `browser` for the https fallback,
 *   `rejected` when the URL failed validation.
 */
export async function openZoomJoinLink(
  raw: unknown,
  openExternal: (url: string) => Promise<void>,
): Promise<ZoomJoinOutcome> {
  const target = resolveZoomJoinTarget(raw);
  if (!target) return 'rejected';
  if (target.deepLink) {
    try {
      await openExternal(target.deepLink);
      return 'desktop';
    } catch {
      // No Zoom client registered for zoommtg:// — fall through to the browser.
    }
  }
  await openExternal(target.webUrl);
  return 'browser';
}
