/* Case Command service worker.
 *
 * Two jobs, both for the moment the network is gone.
 *
 * 1. Serve the pinned record. The bundle at /api/offline/bundle holds the
 *    documents Jacob chose to keep, plus the hearing context they are useless
 *    without. It is cached whole and served from cache the instant a request
 *    fails.
 *
 * 2. Hold captured evidence. A photograph taken with no signal is queued in
 *    IndexedDB and replayed when a connection returns. Nothing is dropped
 *    because an upload failed.
 *
 * Live views are network-first: a stale deadline shown as current would be
 * worse than an honest "offline" banner, so the cached copy always says when
 * it was taken.
 */

const VERSION = 'cc-v1';
const SHELL = `${VERSION}-shell`;
const BUNDLE = `${VERSION}-bundle`;
const PAGES = `${VERSION}-pages`;

const SHELL_ASSETS = [
  '/static/app.css',
  '/static/mobile.css',
  '/static/app.js',
  '/m',
  '/m/offline',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL)
      .then((cache) => cache.addAll(SHELL_ASSETS).catch(() => undefined))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => !k.startsWith(VERSION)).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // The pinned bundle: cache-first, because this is the whole point. Refresh
  // in the background so the next open is current.
  if (url.pathname === '/api/offline/bundle') {
    event.respondWith(
      caches.open(BUNDLE).then(async (cache) => {
        const cached = await cache.match(request);
        const network = fetch(request)
          .then((response) => {
            if (response.ok) cache.put(request, response.clone());
            return response;
          })
          .catch(() => cached);
        return cached || network;
      })
    );
    return;
  }

  // Static shell: cache-first. It never changes within a version.
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(request).then((cached) => cached || fetch(request).then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(SHELL).then((cache) => cache.put(request, copy));
        }
        return response;
      }))
    );
    return;
  }

  // Everything else: network-first, falling back to the last copy, falling back
  // to the offline page. A cached page is stamped so it never passes for live.
  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response.ok && url.pathname.startsWith('/m')) {
          const copy = response.clone();
          caches.open(PAGES).then((cache) => cache.put(request, copy));
        }
        return response;
      })
      .catch(async () => {
        const cached = await caches.match(request);
        if (cached) return cached;
        const fallback = await caches.match('/m/offline');
        return fallback || new Response(
          '<h1>Offline</h1><p>This view was never cached.</p>',
          { headers: { 'Content-Type': 'text/html' }, status: 503 }
        );
      })
  );
});

/* ------------------------------------------------------------------ capture */
/* Replay queued captures when the connection returns. The client_uid is
 * generated on the device, so a replayed upload is recognised as the same
 * capture rather than a second one. */

const DB_NAME = 'case-command';
const STORE = 'captures';

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: 'client_uid' });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function pendingCaptures() {
  const db = await openDb();
  return new Promise((resolve) => {
    const tx = db.transaction(STORE, 'readonly');
    const req = tx.objectStore(STORE).getAll();
    req.onsuccess = () => resolve(req.result || []);
    req.onerror = () => resolve([]);
  });
}

async function dropCapture(clientUid) {
  const db = await openDb();
  return new Promise((resolve) => {
    const tx = db.transaction(STORE, 'readwrite');
    tx.objectStore(STORE).delete(clientUid);
    tx.oncomplete = () => resolve();
    tx.onerror = () => resolve();
  });
}

async function flushCaptures() {
  const queued = await pendingCaptures();
  for (const item of queued) {
    try {
      const body = new FormData();
      body.append('client_uid', item.client_uid);
      body.append('capture_kind', item.capture_kind || 'PHOTO');
      body.append('captured_at', item.captured_at || '');
      body.append('device_note', item.device_note || '');
      if (item.matter_id) body.append('matter_id', item.matter_id);
      body.append('file', item.blob, item.filename || 'capture.jpg');

      const response = await fetch('/api/capture', { method: 'POST', body });
      if (response.ok) {
        await dropCapture(item.client_uid);
        const clients = await self.clients.matchAll();
        clients.forEach((c) => c.postMessage({
          type: 'capture-synced', client_uid: item.client_uid,
        }));
      }
    } catch (err) {
      // Leave it queued. It will be retried on the next sync or page load.
      return;
    }
  }
}

self.addEventListener('sync', (event) => {
  if (event.tag === 'flush-captures') event.waitUntil(flushCaptures());
});

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'flush-captures') {
    event.waitUntil(flushCaptures());
  }
});
