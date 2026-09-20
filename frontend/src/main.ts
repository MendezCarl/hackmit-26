import { join } from 'node:path';
import { app, BrowserWindow } from 'electron/main';

const getWindowIconPath = (): string => {
  if (app.isPackaged) {
    return join(process.resourcesPath, 'icons', 'bloom-icon-512x512.png');
  }

  return join(app.getAppPath(), 'build', 'icons', 'bloom-icon-512x512.png');
};

const createWindow = (): void => {
  const mainWindow = new BrowserWindow({
    width: 1100,
    height: 720,
    minWidth: 760,
    minHeight: 520,
    icon: getWindowIconPath(),
    webPreferences: {
      preload: join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  void mainWindow.loadFile(join(__dirname, 'index.html'));
};

void app.whenReady().then(() => {
  if (process.platform === 'darwin') {
    app.dock.setIcon(getWindowIconPath());
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
