/**
 * Returns the base URL for API calls.
 *
 * - In Electron (file:// origin): talks directly to the local backend.
 * - In the Vite dev server or a hosted deployment: uses the /api proxy,
 *   so no CORS headers are needed and the backend port is not exposed.
 */
export function apiBase(): string {
  // window.jarvisOS is injected by the Electron preload script
  const electron = (window as unknown as { jarvisOS?: { isElectron?: boolean; getBackendPort?: () => Promise<number> } }).jarvisOS;
  if (electron?.isElectron) {
    // Electron: direct localhost call, no proxy
    return 'http://127.0.0.1:8000';
  }
  // Browser / dev server: use the Vite proxy prefix
  return '';
}

/**
 * Resolves a full API URL for the given path (e.g. '/api/health').
 */
export function apiUrl(path: string): string {
  return `${apiBase()}${path}`;
}
