-- Offline availability: documents deliberately kept on the phone.
--
-- The situation this exists for: a hearing room with no signal, or a house with
-- no power. Those are the moments the record matters most and is least
-- reachable. A pinned document is one Jacob has decided must be readable with
-- no network at all.
--
-- Pinning is a decision, not a cache heuristic. Phone storage is finite, so the
-- system never guesses what to keep — it keeps what was chosen, reports the
-- size, and says plainly when a pin can no longer be honoured.

CREATE TABLE offline_pins (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id    INTEGER NOT NULL REFERENCES documents(id),
    matter_id      INTEGER REFERENCES matters(id),

    -- Why it is pinned. A pin made for a specific hearing can be released once
    -- that hearing is over; a standing pin should not be.
    reason         TEXT NOT NULL DEFAULT 'MANUAL'
        CHECK (reason IN ('MANUAL', 'EXHIBIT', 'HEARING_PACK', 'DEADLINE', 'EVIDENCE')),
    hearing_event_id INTEGER REFERENCES events(id),

    -- What to keep. Text is cheap and is what you actually argue from; the
    -- original file can be tens of megabytes and is opt-in.
    include_text     INTEGER NOT NULL DEFAULT 1,
    include_original INTEGER NOT NULL DEFAULT 0,
    include_preview  INTEGER NOT NULL DEFAULT 1,

    est_bytes      INTEGER NOT NULL DEFAULT 0,
    priority       INTEGER NOT NULL DEFAULT 100,   -- lower syncs first

    pinned_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    pinned_by      TEXT NOT NULL DEFAULT 'jacob',
    last_synced_at TEXT,
    sync_state     TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (sync_state IN ('PENDING','SYNCED','STALE','FAILED','UNAVAILABLE')),
    sync_error     TEXT,
    notes          TEXT,

    UNIQUE (document_id, reason)
);

CREATE INDEX idx_offline_pins_matter ON offline_pins(matter_id);
CREATE INDEX idx_offline_pins_state ON offline_pins(sync_state);

-- Evidence captured on the phone while offline.
--
-- A photograph taken at the moment a meter is pulled, or a shutoff notice
-- photographed on the porch, is evidence that will never exist again. It is
-- accepted with no network, stored on the device, and reconciled into the
-- record when a connection returns. Nothing is discarded because the upload
-- failed.
CREATE TABLE capture_queue (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    client_uid     TEXT NOT NULL UNIQUE,   -- generated on the device, dedupes retries
    matter_id      INTEGER REFERENCES matters(id),
    capture_kind   TEXT NOT NULL DEFAULT 'PHOTO'
        CHECK (capture_kind IN ('PHOTO','SCAN','AUDIO','VIDEO','NOTE')),

    -- Captured on the device, at the time it happened. This is the fact that
    -- matters; the upload time is bookkeeping.
    captured_at    TEXT,
    device_note    TEXT,
    latitude       REAL,
    longitude      REAL,

    filename       TEXT,
    byte_size      INTEGER,
    sha256         TEXT,
    stored_path    TEXT,
    document_id    INTEGER REFERENCES documents(id),

    received_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    state          TEXT NOT NULL DEFAULT 'RECEIVED'
        CHECK (state IN ('RECEIVED','INGESTED','FAILED','DUPLICATE')),
    error          TEXT,
    notes          TEXT
);

CREATE INDEX idx_capture_state ON capture_queue(state);

-- Captured evidence is never deleted. A failed ingestion stays visible so the
-- photograph is not silently lost.
CREATE TRIGGER capture_queue_no_delete BEFORE DELETE ON capture_queue
BEGIN
    SELECT RAISE(ABORT, 'captured evidence cannot be deleted; change state instead');
END;
