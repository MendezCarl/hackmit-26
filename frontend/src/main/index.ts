import { join } from 'node:path';
import { app, BrowserWindow, ipcMain } from 'electron/main';
import { registerBackendIpc } from './backend_ipc.js';
import {
  DriftRecoveryController,
  parseDriftRecoveryRequest,
  planOverlayAction,
} from './drift_recovery.js';
import { SessionEventsBridge } from './session_events.js';
import { createBloomTray, openMainWindow, updateTrayZoomStatus } from './tray.js';
import {
  OVERLAY_CARD_HEIGHT_PX,
  hideZoomOverlay,
  pauseZoomOverlayAutoClose,
  resizeZoomOverlay,
  sendToZoomOverlay,
  showZoomOverlay,
} from './zoom_overlay_window.js';
import { ZoomProcessMonitor } from './zoom_monitor.js';

type BloomRole = 'professor' | 'student' | null;

let mainWindow: BrowserWindow | null = null;
let currentRole: BloomRole = null;
let isQuitting = false;
let zoomRunning = false;
let zoomMonitor: ZoomProcessMonitor | undefined;
let sessionEvents: SessionEventsBridge | undefined;
let driftRecovery: DriftRecoveryController | undefined;

const sendToMainWindow = (channel: string, payload: unknown): void => {
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send(channel, payload);
};

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
  ipcMain.on('overlay:action', (_event, message: unknown) => {
    const plan = planOverlayAction(message);
    if (plan.kind === 'recover') {
      // Recovery happens inside the overlay; the main window must stay hidden so
      // the student never loses the Zoom window.
      pauseZoomOverlayAutoClose();
      resizeZoomOverlay(OVERLAY_CARD_HEIGHT_PX);
      void driftRecovery?.recover();
      return;
    }
    if (plan.kind === 'open') {
      openMainWindow(createWindow);
      sendToMainWindow('zoom:overlay-open', { view: plan.view });
    }
    hideZoomOverlay();
  });
  ipcMain.on('overlay:show-drift', (_event, rawRequest: unknown) => {
    driftRecovery?.setPending(parseDriftRecoveryRequest(rawRequest));
    showZoomOverlay(currentRole === 'student' ? 'student' : null, 'drift');
  });
  ipcMain.on('session-events:subscribe', (_event, sessionId: unknown) => {
    sessionEvents?.subscribe(typeof sessionId === 'string' && sessionId ? sessionId : null);
  });
};

app.on('before-quit', () => {
  isQuitting = true;
  zoomMonitor?.stop();
  sessionEvents?.stop();
});

void app.whenReady().then(() => {
  const backendClient = registerBackendIpc();
  sessionEvents = new SessionEventsBridge(backendClient, sendToMainWindow);
  driftRecovery = new DriftRecoveryController(backendClient, (state) => {
    sendToZoomOverlay('overlay:recovery-state', state);
    if (state.status === 'ready') {
      sendToMainWindow('recovery:card-created', {
        session_id: state.request.session_id,
        event_id: state.request.event_id,
        card: state.card,
      });
    }
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
