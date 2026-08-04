/* Case Command phone client.
 *
 * Registers the service worker, queues captured evidence in IndexedDB when the
 * network is gone, and reads the pinned bundle straight from cache so the
 * record opens with no connection at all.
 *
 * The connection state is always shown. A page that silently serves stale data
 * during a hearing would be worse than one that says it is offline.
 */

(function () {
  'use strict';

  const DB_NAME = 'case-command';
  const STORE = 'captures';

  /* ------------------------------------------------------- service worker */
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/static/sw.js', { scope: '/' })
        .then(() => flushQueue())
        .catch((err) => console.warn('service worker registration failed', err));
    });

    navigator.serviceWorker.addEventListener('message', (event) => {
      if (event.data && event.data.type === 'capture-synced') {
        renderQueue();
        toast('Capture uploaded.');
      }
    });
  }

  /* ---------------------------------------------------------- connection */
  function setOnlineState() {
    const online = navigator.onLine;
    document.documentElement.dataset.online = online ? 'yes' : 'no';
    document.querySelectorAll('[data-conn]').forEach((el) => {
      el.textContent = online ? 'Online' : 'Offline';
      el.className = online ? 'conn on' : 'conn off';
    });
    if (online) flushQueue();
  }
  window.addEventListener('online', setOnlineState);
  window.addEventListener('offline', setOnlineState);
  document.addEventListener('DOMContentLoaded', setOnlineState);

  /* ------------------------------------------------------------ indexeddb */
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

  async function queueCapture(record) {
    const db = await openDb();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite');
      tx.objectStore(STORE).put(record);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  async function listQueue() {
    const db = await openDb();
    return new Promise((resolve) => {
      const tx = db.transaction(STORE, 'readonly');
      const req = tx.objectStore(STORE).getAll();
      req.onsuccess = () => resolve(req.result || []);
      req.onerror = () => resolve([]);
    });
  }

  async function removeFromQueue(clientUid) {
    const db = await openDb();
    return new Promise((resolve) => {
      const tx = db.transaction(STORE, 'readwrite');
      tx.objectStore(STORE).delete(clientUid);
      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve();
    });
  }

  /* -------------------------------------------------------------- capture */
  function uid() {
    if (crypto && crypto.randomUUID) return crypto.randomUUID();
    return 'cap-' + Date.now() + '-' + Math.floor(Math.random() * 1e9);
  }

  async function handleCapture(form) {
    const fileInput = form.querySelector('input[type=file]');
    const file = fileInput && fileInput.files && fileInput.files[0];
    if (!file) { toast('Choose or take a photo first.'); return; }

    const record = {
      client_uid: uid(),
      blob: file,
      filename: file.name || 'capture.jpg',
      capture_kind: (form.querySelector('[name=capture_kind]') || {}).value || 'PHOTO',
      // The moment it was taken is the fact that matters. Recorded on the
      // device so a delayed upload never changes it.
      captured_at: new Date().toISOString(),
      device_note: (form.querySelector('[name=device_note]') || {}).value || '',
      matter_id: (form.querySelector('[name=matter_id]') || {}).value || '',
      queued_at: new Date().toISOString(),
    };

    await queueCapture(record);
    renderQueue();
    form.reset();
    toast(navigator.onLine ? 'Captured — uploading…' : 'Captured — saved on device.');
    flushQueue();
  }

  async function flushQueue() {
    if (!navigator.onLine) { renderQueue(); return; }
    const queued = await listQueue();
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
        if (response.ok) await removeFromQueue(item.client_uid);
      } catch (err) {
        break;   // stay queued; retried on reconnect
      }
    }
    renderQueue();
  }

  async function renderQueue() {
    const host = document.querySelector('[data-capture-queue]');
    if (!host) return;
    const queued = await listQueue();
    if (!queued.length) {
      host.innerHTML = '<p class="m-empty">Nothing waiting to upload.</p>';
      return;
    }
    host.innerHTML = queued.map((item) => `
      <div class="m-row">
        <div>
          <b>${escapeHtml(item.filename)}</b>
          <div class="m-sub">${escapeHtml(item.capture_kind)} ·
            captured ${escapeHtml((item.captured_at || '').slice(0, 16).replace('T', ' '))}</div>
          ${item.device_note ? `<div class="m-sub">${escapeHtml(item.device_note)}</div>` : ''}
        </div>
        <span class="m-chip warn">queued</span>
      </div>`).join('');
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  /* ------------------------------------------------------- offline bundle */
  async function loadBundle() {
    const host = document.querySelector('[data-offline-bundle]');
    if (!host) return;
    try {
      const response = await fetch('/api/offline/bundle');
      const bundle = await response.json();
      renderBundle(host, bundle, navigator.onLine);
    } catch (err) {
      host.innerHTML =
        '<p class="m-empty">No cached copy on this device yet. Open this page once ' +
        'while online to download the pinned documents.</p>';
    }
  }

  function renderBundle(host, bundle, live) {
    const docs = bundle.documents || [];
    if (!docs.length) {
      host.innerHTML =
        '<p class="m-empty">No documents pinned. Pin what you need to read with no ' +
        'signal — start with the exhibits for your next hearing.</p>';
      return;
    }
    const stamp = (bundle.built_at || '').slice(0, 16).replace('T', ' ');
    host.innerHTML = `
      <div class="m-stamp">${live ? 'Live' : 'Cached'} copy · built ${escapeHtml(stamp)} UTC</div>
      ${docs.map((d) => `
        <a class="m-row" href="/m/doc?id=${d.id}">
          <div>
            <b>${escapeHtml(d.extract || d.title)}</b>
            <div class="m-sub">${escapeHtml(d.doc_uid)} ·
              ${escapeHtml(d.date || 'no date')}
              ${d.date_source ? '· ' + escapeHtml(d.date_source) : ''}</div>
          </div>
          <span class="m-chip ok">${escapeHtml(d.reason)}</span>
        </a>`).join('')}`;
  }

  /* --------------------------------------------------------------- toast */
  let toastTimer = null;
  function toast(message) {
    let el = document.querySelector('.m-toast');
    if (!el) {
      el = document.createElement('div');
      el.className = 'm-toast';
      document.body.appendChild(el);
    }
    el.textContent = message;
    el.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('show'), 2600);
  }

  /* ----------------------------------------------------------------- boot */
  document.addEventListener('DOMContentLoaded', () => {
    const captureForm = document.querySelector('[data-capture-form]');
    if (captureForm) {
      captureForm.addEventListener('submit', (event) => {
        event.preventDefault();
        handleCapture(captureForm);
      });
    }
    renderQueue();
    loadBundle();

    document.querySelectorAll('[data-countdown]').forEach((el) => {
      const due = el.dataset.countdown;
      if (due) tickCountdown(el, due);
    });
  });

  /* Deadline countdown. Rendered on the device from the stored date, so it is
   * correct offline and cannot silently freeze at a stale value. */
  function tickCountdown(el, due) {
    function update() {
      const target = new Date(due + 'T23:59:59Z').getTime();
      const diff = target - Date.now();
      if (isNaN(target)) { el.textContent = '—'; return; }
      if (diff < 0) {
        const days = Math.ceil(Math.abs(diff) / 86400000);
        el.textContent = `passed ${days}d ago`;
        el.classList.add('over');
        return;
      }
      const days = Math.floor(diff / 86400000);
      const hours = Math.floor((diff % 86400000) / 3600000);
      el.textContent = days > 0 ? `${days}d ${hours}h` : `${hours}h`;
      if (days <= 3) el.classList.add('urgent');
    }
    update();
    setInterval(update, 60000);
  }
})();
