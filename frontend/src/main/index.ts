import { join } from 'node:path';
import { shell } from 'electron/common';
import { app, BrowserWindow, ipcMain } from 'electron/main';
import { registerBackendIpc } from './backend_ipc.js';
import { SessionEventsBridge } from './session_events.js';
import { createBloomTray, openMainWindow, updateTrayZoomStatus } from './tray.js';
import { hideZoomOverlay, showZoomOverlay } from './zoom_overlay_window.js';
import { openZoomJoinLink } from './zoom_join_link.js';
import { ZoomProcessMonitor } from './zoom_monitor.js';

type BloomRole = 'professor' | 'student' | null;

let mainWindow: BrowserWindow | null = null;
let currentRole: BloomRole = null;
let isQuitting = false;
let zoomRunning = false;
let zoomMonitor: ZoomProcessMonitor | undefined;
let sessionEvents: SessionEventsBridge | undefined;

/**
 * Resolves the Bloom window icon for development or packaged execution.
 *
 * @returns Absolute path to the platform-neutral PNG window icon.
 */
const getWindowIconPath = (): string => {
  if (app.isPackaged) {
    return join(process.resourcesPath, 'icons', 'bloom-icon-512x512.png');
  }

  return join(app.getAppPath(), 'build', 'icons', 'bloom-icon-512x512.png');
};

/**
 * Creates Bloom's primary desktop window with an isolated renderer context.
 *
 * @returns The created or existing primary window.
 */
const createWindow = (): BrowserWindow => {
  if (mainWindow && !mainWindow.isDestroyed()) return mainWindow;
  mainWindow = new BrowserWindow({
    width: 1100,
    height: 720,
    minWidth: 760,
    minHeight: 520,
    icon: getWindowIconPath(),
    webPreferences: {
      preload: join(__dirname, '..', 'preload', 'index.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  void mainWindow.loadFile(join(__dirname, '..', 'index.html'));
  mainWindow.webContents.on('did-finish-load', () => {
    mainWindow?.webContents.send('zoom:detected', { running: zoomRunning });
  });
  mainWindow.on('close', (event) => {
    if (!isQuitting && process.platform !== 'darwin') {
      event.preventDefault();
      mainWindow?.hide();
    }
  });
  mainWindow.on('closed', () => {
    mainWindow = null;
  });
  return mainWindow;
};

const registerDesktopIpc = (): void => {
  ipcMain.on('app:set-role', (_event, role: BloomRole) => {
    if (role !== null && role !== 'professor' && role !== 'student') return;
    const roleChanged = role !== currentRole;
    currentRole = role;
    if (zoomRunning && roleChanged && role !== null) showZoomOverlay(currentRole);
  });
  ipcMain.on('overlay:action', (_event, action: { action?: string }) => {
    if (action?.action === 'open') {
      openMainWindow(createWindow);
      mainWindow?.webContents.send('zoom:overlay-open');
    }
    hideZoomOverlay();
  });
  ipcMain.on('overlay:show-drift', () => {
    showZoomOverlay(currentRole === 'student' ? 'student' : null, 'drift');
  });
  ipcMain.on('session-events:subscribe', (_event, sessionId: unknown) => {
    sessionEvents?.subscribe(typeof sessionId === 'string' && sessionId ? sessionId : null);
  });
  ipcMain.handle('zoom:open-join', (_event, joinUrl: unknown) =>
    openZoomJoinLink(joinUrl, (url) => shell.openExternal(url)),
  );
};

app.on('before-quit', () => {
  isQuitting = true;
  zoomMonitor?.stop();
  sessionEvents?.stop();
});

void app.whenReady().then(() => {
  const backendClient = registerBackendIpc();
  sessionEvents = new SessionEventsBridge(backendClient, (channel, payload) => {
    if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send(channel, payload);
  });
  registerDesktopIpc();
  if (process.platform === 'darwin') {
    app.dock?.setIcon(getWindowIconPath());
  }

  createBloomTray(createWindow, () => {
    isQuitting = true;
    app.quit();
  });
  createWindow();
  zoomMonitor = new ZoomProcessMonitor();
  zoomMonitor.on('change', (running) => {
    zoomRunning = running;
    updateTrayZoomStatus(running);
    if (running) {
      showZoomOverlay(currentRole);
      mainWindow?.webContents.send('zoom:detected', { running: true });
    } else {
      hideZoomOverlay();
      mainWindow?.webContents.send('zoom:detected', { running: false });
    }
  });
  zoomMonitor.start();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    } else {
      openMainWindow(createWindow);
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
