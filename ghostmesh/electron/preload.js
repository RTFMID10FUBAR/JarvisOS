'use strict';

const { contextBridge, ipcRenderer } = require('electron');

// Expose a safe, minimal API to the renderer process.
// No direct Node.js or Electron APIs — only whitelisted IPC calls.
contextBridge.exposeInMainWorld('jarvisOS', {
  /** True when running inside Electron */
  isElectron: true,

  /** Electron app version string */
  getVersion: () => ipcRenderer.invoke('app:version'),

  /** Host platform ('darwin' | 'win32' | 'linux') */
  getPlatform: () => ipcRenderer.invoke('app:platform'),

  /** Whether the GhostMesh API backend is responding */
  isBackendReady: () => ipcRenderer.invoke('app:backend-ready'),

  /** Port the backend is listening on */
  getBackendPort: () => ipcRenderer.invoke('app:backend-port'),

  /**
   * Listen for navigate events sent from the main process menu items.
   * @param {(route: string) => void} handler
   * @returns {() => void} unsubscribe function
   */
  onNavigate: (handler) => {
    const listener = (_event, route) => handler(route);
    ipcRenderer.on('navigate', listener);
    return () => ipcRenderer.removeListener('navigate', listener);
  },
});
