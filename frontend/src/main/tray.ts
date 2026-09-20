import { join } from 'node:path';
import { app, BrowserWindow, Menu, Tray } from 'electron/main';
import { nativeImage } from 'electron';

let bloomTray: Tray | null = null;
let zoomRunning = false;
let refreshTrayMenu: (() => void) | null = null;

/**
 * Creates Bloom's persistent tray icon and context menu.
 *
 * @param getMainWindow - Returns or creates the primary window.
 * @param quit - Marks application shutdown and quits Bloom.
 * @returns The tray instance retained by this module.
 */
export function createBloomTray(
  getMainWindow: () => BrowserWindow,
  quit: () => void = () => app.quit(),
): Tray {
  const iconPath = app.isPackaged
    ? join(process.resourcesPath, 'icons', 'bloom-icon-512x512.png')
    : join(app.getAppPath(), 'build', 'icons', 'bloom-icon-512x512.png');
  const icon = nativeImage.createFromPath(iconPath).resize({ width: 16, height: 16 });
  bloomTray = new Tray(icon);
  if (process.platform === 'darwin') icon.setTemplateImage(false);
  bloomTray.setToolTip('Bloom');
  bloomTray.on('click', () => openMainWindow(getMainWindow));
  refreshTrayMenu = () => updateTrayMenu(getMainWindow, quit);
  refreshTrayMenu();
  return bloomTray;
}

/**
 * Updates the tray status item and preserves the existing tray instance.
 *
 * @param running - Whether Zoom is currently detected.
 * @returns Nothing.
 */
export function updateTrayZoomStatus(running: boolean): void {
  zoomRunning = running;
  refreshTrayMenu?.();
}

/**
 * Opens or focuses Bloom's primary window from tray actions.
 *
 * @param getMainWindow - Returns or creates the primary window.
 * @returns Nothing.
 */
export function openMainWindow(getMainWindow: () => BrowserWindow): void {
  const window = getMainWindow();
  if (window.isMinimized()) window.restore();
  window.show();
  window.focus();
}

function updateTrayMenu(getMainWindow: () => BrowserWindow, quit: () => void): void {
  bloomTray?.setContextMenu(
    Menu.buildFromTemplate([
      { label: 'Open Bloom', click: () => openMainWindow(getMainWindow) },
      { type: 'separator' },
      { label: zoomRunning ? 'Zoom: running' : 'Zoom: not detected', enabled: false },
      { type: 'separator' },
      { label: 'Quit', click: quit },
    ]),
  );
}
