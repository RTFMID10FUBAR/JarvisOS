const BACKEND_URL_KEY = 'gm-backend-url';

/**
 * Returns the base URL for API calls, resolved in priority order:
 *
 * 1. User-configured URL stored in localStorage (works on all platforms)
 * 2. Electron (file:// origin) → direct http://127.0.0.1:8000
 * 3. Capacitor native shell (Android / iOS) → http://10.0.2.2:8000 default
 *    (10.0.2.2 = Android emulator loopback to host; configure via Settings on real devices)
 * 4. Browser / Vite dev server → empty string (uses /api proxy)
 */
export function apiBase(): string {
  // 1. User-configured URL always wins
  try {
    const saved = localStorage.getItem(BACKEND_URL_KEY);
    if (saved && saved.trim()) return saved.trim().replace(/\/$/, '');
  } catch { /* private browsing / localStorage blocked */ }

  // 2. Electron — preload script injects window.jarvisOS
  const w = window as unknown as {
    jarvisOS?: { isElectron?: boolean };
    Capacitor?: { isNativePlatform?: () => boolean };
  };
  if (w.jarvisOS?.isElectron) {
    return 'http://127.0.0.1:8000';
  }

  // 3. Capacitor native shell (Android / iOS)
  if (w.Capacitor?.isNativePlatform?.()) {
    // On emulator 10.0.2.2 → host machine; on real device user must configure in Settings
    return 'http://10.0.2.2:8000';
  }

  // 4. Browser dev server / hosted — use the Vite /api proxy
  return '';
}

/**
 * Resolves a full API URL for the given path (e.g. '/api/health').
 */
export function apiUrl(path: string): string {
  return `${apiBase()}${path}`;
}

/** Save a custom backend URL to localStorage (empty string to clear). */
export function setBackendUrl(url: string): void {
  try {
    if (url.trim()) {
      localStorage.setItem(BACKEND_URL_KEY, url.trim());
    } else {
      localStorage.removeItem(BACKEND_URL_KEY);
    }
  } catch { /* ignore */ }
}

/** Read the saved custom backend URL (or empty string if not set). */
export function getBackendUrl(): string {
  try {
    return localStorage.getItem(BACKEND_URL_KEY) ?? '';
  } catch {
    return '';
  }
}
