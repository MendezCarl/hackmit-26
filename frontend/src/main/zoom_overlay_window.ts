import { join } from 'node:path';
import { BrowserWindow, screen } from 'electron/main';

/** Overlay width in CSS pixels; matches `.overlay-card` sizing. */
export const OVERLAY_WIDTH_PX = 380;
/** Height of the compact prompt (Zoom detected / Drifted?). */
export const OVERLAY_PROMPT_HEIGHT_PX = 170;
/** Height once the overlay shows a recovery card so the student can read it without leaving Zoom. */
export const OVERLAY_CARD_HEIGHT_PX = 520;
/** Idle time before an untouched prompt closes itself. */
const OVERLAY_AUTO_CLOSE_MS = 45_000;
const OVERLAY_MARGIN_PX = 16;

let overlayWindow: BrowserWindow | null = null;
let closeTimer: NodeJS.Timeout | undefined;

/**
 * Shows the compact Zoom detection overlay for the current role.
 *
 * The window is shown inactive on the display under the cursor so the app the
 * student is using (normally Zoom) keeps keyboard focus.
 *
 * @param role - Authenticated role, or null when the user is signed out.
 * @param variant - `zoom` for the Zoom-detected prompt, `drift` for the drift prompt.
 * @returns Nothing; the singleton overlay is managed by this module.
 */
export function showZoomOverlay(
  role: 'professor' | 'student' | null,
  variant: 'zoom' | 'drift' = 'zoom',
): void {
  if (overlayWindow && !overlayWindow.isDestroyed()) {
    resizeZoomOverlay(OVERLAY_PROMPT_HEIGHT_PX);
    void loadOverlay(role, variant);
    overlayWindow.showInactive();
    resetCloseTimer();
    return;
  }

  overlayWindow = new BrowserWindow({
    width: OVERLAY_WIDTH_PX,
    height: OVERLAY_PROMPT_HEIGHT_PX,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    focusable: true,
    show: false,
    webPreferences: {
      preload: join(__dirname, '..', 'preload', 'index.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  overlayWindow.setAlwaysOnTop(true, 'screen-saver');
  overlayWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  positionOverlay(overlayWindow, OVERLAY_PROMPT_HEIGHT_PX);
  overlayWindow.on('closed', () => {
    clearCloseTimer();
    overlayWindow = null;
  });
  void loadOverlay(role, variant);
  overlayWindow.once('ready-to-show', () => overlayWindow?.showInactive());
  resetCloseTimer();
}

/**
 * Hides and destroys the current Zoom overlay window.
 *
 * @returns Nothing.
 */
export function hideZoomOverlay(): void {
  clearCloseTimer();
  if (overlayWindow && !overlayWindow.isDestroyed()) overlayWindow.close();
  overlayWindow = null;
}

/**
 * Sends a message to the overlay renderer if the overlay is open.
 *
 * @param channel - IPC channel name.
 * @param payload - Structured-clone-safe payload.
 * @returns True when a live overlay received the message.
 */
export function sendToZoomOverlay(channel: string, payload: unknown): boolean {
  if (!overlayWindow || overlayWindow.isDestroyed()) return false;
  overlayWindow.webContents.send(channel, payload);
  return true;
}

/**
 * Resizes the overlay in place, keeping its top-right anchor on the same display.
 *
 * @param heightPx - New window height in pixels.
 * @returns Nothing.
 */
export function resizeZoomOverlay(heightPx: number): void {
  if (!overlayWindow || overlayWindow.isDestroyed()) return;
  const [currentWidth, currentHeight] = overlayWindow.getSize();
  if (currentWidth === OVERLAY_WIDTH_PX && currentHeight === heightPx) return;
  overlayWindow.setSize(OVERLAY_WIDTH_PX, heightPx, false);
  positionOverlay(overlayWindow, heightPx);
}

/**
 * Stops the idle auto-close while the student is reading or waiting on a card.
 *
 * @returns Nothing.
 */
export function pauseZoomOverlayAutoClose(): void {
  clearCloseTimer();
}

async function loadOverlay(
  role: 'professor' | 'student' | null,
  variant: 'zoom' | 'drift',
): Promise<void> {
  if (!overlayWindow || overlayWindow.isDestroyed()) return;
  await overlayWindow.loadFile(join(__dirname, '..', 'overlay.html'), {
    search: `?role=${encodeURIComponent(role ?? '')}&variant=${variant}`,
  });
}

function positionOverlay(window: BrowserWindow, heightPx: number): void {
  const display = screen.getDisplayNearestPoint(screen.getCursorScreenPoint());
  const { x, y, width, height } = display.workArea;
  // Keep the card fully on screen when it grows on a short display.
  const top = Math.max(y, Math.min(y + OVERLAY_MARGIN_PX, y + height - heightPx - OVERLAY_MARGIN_PX));
  window.setPosition(x + width - OVERLAY_WIDTH_PX - OVERLAY_MARGIN_PX, top);
}

function resetCloseTimer(): void {
  clearCloseTimer();
  closeTimer = setTimeout(hideZoomOverlay, OVERLAY_AUTO_CLOSE_MS);
}

function clearCloseTimer(): void {
  if (closeTimer) clearTimeout(closeTimer);
  closeTimer = undefined;
}
