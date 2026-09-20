import { join } from 'node:path';
import { BrowserWindow, screen } from 'electron/main';

let overlayWindow: BrowserWindow | null = null;
let closeTimer: NodeJS.Timeout | undefined;

/**
 * Shows the compact Zoom detection overlay for the current role.
 *
 * @param role - Authenticated role, or null when the user is signed out.
 * @returns Nothing; the singleton overlay is managed by this module.
 */
export function showZoomOverlay(role: 'professor' | 'student' | null): void {
  if (overlayWindow && !overlayWindow.isDestroyed()) {
    void loadOverlay(role);
    overlayWindow.showInactive();
    resetCloseTimer();
    return;
  }

  overlayWindow = new BrowserWindow({
    width: 380,
    height: 170,
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
  positionOverlay(overlayWindow);
  overlayWindow.on('closed', () => {
    clearCloseTimer();
    overlayWindow = null;
  });
  void loadOverlay(role);
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

async function loadOverlay(role: 'professor' | 'student' | null): Promise<void> {
  if (!overlayWindow || overlayWindow.isDestroyed()) return;
  await overlayWindow.loadFile(join(__dirname, '..', 'overlay.html'), {
    search: `?role=${encodeURIComponent(role ?? '')}`,
  });
}

function positionOverlay(window: BrowserWindow): void {
  const display = screen.getPrimaryDisplay();
  const { x, y, width, height } = display.workArea;
  const margin = 16;
  window.setPosition(x + width - 380 - margin, y + margin);
}

function resetCloseTimer(): void {
  clearCloseTimer();
  closeTimer = setTimeout(hideZoomOverlay, 45_000);
}

function clearCloseTimer(): void {
  if (closeTimer) clearTimeout(closeTimer);
  closeTimer = undefined;
}
