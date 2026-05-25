'use strict';

const { app, BrowserWindow, Menu, shell, ipcMain, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');
const fs = require('fs');

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let mainWindow = null;
let backendProcess = null;
let backendReady = false;

const BACKEND_PORT = parseInt(process.env.GHOSTMESH_PORT ?? '8080', 10);
const FRONTEND_DEV_URL = 'http://localhost:5173';
const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;

// ---------------------------------------------------------------------------
// Backend management
// ---------------------------------------------------------------------------

function resolveBackendDir() {
  if (isDev) {
    return path.join(__dirname, '..', 'backend');
  }
  return path.join(process.resourcesPath, 'backend');
}

function resolvePython(backendDir) {
  if (isDev) {
    // prefer venv if present, else fall through to system python3
    const venvPy = path.join(backendDir, 'venv', 'bin', 'python3');
    if (fs.existsSync(venvPy)) return venvPy;
    return 'python3';
  }
  // Packaged: we bundle a venv inside the backend resource
  const venvPy = path.join(backendDir, 'venv', 'bin', 'python3');
  if (fs.existsSync(venvPy)) return venvPy;
  return 'python3';
}

function startBackend() {
  const backendDir = resolveBackendDir();
  const python = resolvePython(backendDir);
  const mainPy = path.join(backendDir, 'main.py');

  if (!fs.existsSync(mainPy)) {
    console.warn('[backend] main.py not found at', mainPy, '— skipping backend launch');
    return;
  }

  const envFile = path.join(backendDir, '.env');
  const env = { ...process.env };

  // Load .env into environment if present
  if (fs.existsSync(envFile)) {
    const lines = fs.readFileSync(envFile, 'utf8').split('\n');
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const eqIdx = trimmed.indexOf('=');
      if (eqIdx < 1) continue;
      const key = trimmed.slice(0, eqIdx).trim();
      const val = trimmed.slice(eqIdx + 1).trim().replace(/^["']|["']$/g, '');
      if (key && !(key in env)) env[key] = val;
    }
  }

  console.log('[backend] starting', python, 'in', backendDir);

  backendProcess = spawn(
    python,
    ['-m', 'uvicorn', 'main:app', '--port', String(BACKEND_PORT), '--host', '127.0.0.1', '--log-level', 'warning'],
    {
      cwd: backendDir,
      env,
      stdio: ['ignore', 'pipe', 'pipe'],
    }
  );

  backendProcess.stdout.on('data', (d) => process.stdout.write('[backend] ' + d));
  backendProcess.stderr.on('data', (d) => process.stderr.write('[backend] ' + d));
  backendProcess.on('error', (err) => console.error('[backend] spawn error:', err.message));
  backendProcess.on('exit', (code, signal) => {
    console.log(`[backend] exited — code=${code} signal=${signal}`);
    backendProcess = null;
  });
}

function stopBackend() {
  if (!backendProcess) return;
  console.log('[backend] terminating...');
  backendProcess.kill('SIGTERM');
  // escalate to SIGKILL after 3 s
  setTimeout(() => {
    if (backendProcess) {
      backendProcess.kill('SIGKILL');
      backendProcess = null;
    }
  }, 3000);
}

/**
 * Poll /api/health until it responds 200 or we give up.
 * @param {(ok: boolean) => void} cb
 * @param {number} maxAttempts
 */
function waitForBackend(cb, maxAttempts = 40) {
  let attempts = 0;

  function attempt() {
    attempts++;
    const req = http.get(`http://127.0.0.1:${BACKEND_PORT}/api/health`, (res) => {
      if (res.statusCode === 200) {
        backendReady = true;
        cb(true);
      } else if (attempts < maxAttempts) {
        setTimeout(attempt, 500);
      } else {
        cb(false);
      }
      // drain response body
      res.resume();
    });
    req.on('error', () => {
      if (attempts < maxAttempts) {
        setTimeout(attempt, 500);
      } else {
        cb(false);
      }
    });
    req.setTimeout(1000, () => req.destroy());
  }

  attempt();
}

// ---------------------------------------------------------------------------
// Window
// ---------------------------------------------------------------------------

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 900,
    minHeight: 600,
    titleBarStyle: 'hiddenInset',
    trafficLightPosition: { x: 16, y: 16 },
    backgroundColor: '#0d1117',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      webSecurity: true,
    },
  });

  // Show window gracefully once content is ready
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    if (isDev) mainWindow.webContents.openDevTools({ mode: 'detach' });
  });

  if (isDev) {
    mainWindow.loadURL(FRONTEND_DEV_URL);
  } else {
    const indexPath = path.join(process.resourcesPath, 'frontend-dist', 'index.html');
    mainWindow.loadFile(indexPath);
  }

  // Open <a target="_blank"> links in the system browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// ---------------------------------------------------------------------------
// App menu
// ---------------------------------------------------------------------------

function buildAppMenu() {
  const template = [
    {
      label: 'JarvisOS',
      submenu: [
        { role: 'about', label: 'About JarvisOS GhostMesh' },
        { type: 'separator' },
        {
          label: 'Preferences…',
          accelerator: 'CmdOrCtrl+,',
          click() {
            if (mainWindow) mainWindow.webContents.send('navigate', '/settings');
          },
        },
        { type: 'separator' },
        { role: 'hide', label: 'Hide JarvisOS' },
        { role: 'hideOthers' },
        { role: 'unhide' },
        { type: 'separator' },
        { role: 'quit', label: 'Quit JarvisOS' },
      ],
    },
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' },
        { role: 'pasteAndMatchStyle' },
        { role: 'delete' },
        { role: 'selectAll' },
      ],
    },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'forceReload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' },
      ],
    },
    {
      label: 'Navigate',
      submenu: [
        {
          label: 'Module Hub',
          accelerator: 'CmdOrCtrl+Shift+H',
          click() { if (mainWindow) mainWindow.webContents.send('navigate', '/modules'); },
        },
        {
          label: 'GhostMesh Overview',
          accelerator: 'CmdOrCtrl+Shift+O',
          click() { if (mainWindow) mainWindow.webContents.send('navigate', '/'); },
        },
        {
          label: 'Search',
          accelerator: 'CmdOrCtrl+K',
          click() { if (mainWindow) mainWindow.webContents.send('navigate', '/search'); },
        },
        {
          label: 'People Finder',
          accelerator: 'CmdOrCtrl+Shift+P',
          click() { if (mainWindow) mainWindow.webContents.send('navigate', '/entities/people'); },
        },
        {
          label: 'Image Search',
          accelerator: 'CmdOrCtrl+Shift+I',
          click() { if (mainWindow) mainWindow.webContents.send('navigate', '/entities/images'); },
        },
      ],
    },
    {
      label: 'Window',
      submenu: [
        { role: 'minimize' },
        { role: 'zoom' },
        { type: 'separator' },
        { role: 'front' },
      ],
    },
    {
      label: 'Help',
      role: 'help',
      submenu: [
        {
          label: 'Backend Status',
          click() {
            const status = backendReady ? 'online' : 'offline';
            dialog.showMessageBox(mainWindow, {
              title: 'Backend Status',
              message: `GhostMesh API: ${status}`,
              detail: `Port: ${BACKEND_PORT}\nURL: http://127.0.0.1:${BACKEND_PORT}/api/health`,
              type: 'info',
              buttons: ['OK'],
            });
          },
        },
      ],
    },
  ];

  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

// ---------------------------------------------------------------------------
// IPC handlers
// ---------------------------------------------------------------------------

ipcMain.handle('app:version', () => app.getVersion());
ipcMain.handle('app:platform', () => process.platform);
ipcMain.handle('app:backend-ready', () => backendReady);
ipcMain.handle('app:backend-port', () => BACKEND_PORT);

// ---------------------------------------------------------------------------
// App lifecycle
// ---------------------------------------------------------------------------

app.whenReady().then(() => {
  buildAppMenu();
  startBackend();

  // Wait up to 20 s for backend before showing the window
  waitForBackend((ready) => {
    if (!ready) {
      console.warn('[app] Backend did not become ready in time — loading frontend anyway');
    }
    createWindow();
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    stopBackend();
    app.quit();
  }
});

app.on('before-quit', () => {
  stopBackend();
});
