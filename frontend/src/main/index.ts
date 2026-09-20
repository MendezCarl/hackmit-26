import { join } from 'node:path';
import { app, BrowserWindow } from 'electron/main';

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
 * @returns Nothing; the created window is managed by Electron.
 */
const createWindow = (): void => {
  const mainWindow = new BrowserWindow({
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
};

void app.whenReady().then(() => {
  if (process.platform === 'darwin') {
    app.dock?.setIcon(getWindowIconPath());
  }

  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
