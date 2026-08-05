-- Paired devices and delta sync.
--
-- A standalone phone app is not a browser: it holds its own copy of the record
-- and reconciles. That needs three things the web UI never did.
--
-- 1. Identity. A device is paired once with a short code shown on the desktop,
--    and afterwards carries a token. No account, no cloud, no password to lose
--    — the pairing happens on the same network, between two machines Jacob
--    already controls.
--
-- 2. A cursor. Sync asks "what changed since X" rather than refetching the case
--    every time. Over a phone connection on a bad day, that difference is the
--    difference between having the record and not.
--
-- 3. A record of what each device holds. If a phone is lost, what was on it is
--    a fact worth knowing, and it is here rather than only on the device.

CREATE TABLE devices (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    device_uid     TEXT NOT NULL UNIQUE,
    label          TEXT NOT NULL,
    platform       TEXT,                 -- ios | android | web | other
    app_version    TEXT,

    -- SHA-256 of the bearer token. The token itself is shown once at pairing
    -- and never stored, so a stolen database yields no working credential.
    token_hash     TEXT NOT NULL,
    token_prefix   TEXT NOT NULL,        -- first 8 chars, so a device is identifiable in a list

    paired_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    last_seen_at   TEXT,
    last_sync_cursor TEXT,
    sync_count     INTEGER NOT NULL DEFAULT 0,

    revoked        INTEGER NOT NULL DEFAULT 0,
    revoked_at     TEXT,
    revoked_reason TEXT,
    notes          TEXT
);

CREATE INDEX idx_devices_token ON devices(token_hash);

-- Short-lived pairing codes. Displayed on the desktop, typed into the phone.
CREATE TABLE pairing_codes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    expires_at  TEXT NOT NULL,
    used_at     TEXT,
    device_id   INTEGER REFERENCES devices(id),
    created_by  TEXT NOT NULL DEFAULT 'jacob'
);

-- A device is never deleted, only revoked. What a lost phone was carrying is a
-- fact worth keeping.
CREATE TRIGGER devices_no_delete BEFORE DELETE ON devices
BEGIN
    SELECT RAISE(ABORT, 'devices cannot be deleted; revoke them instead');
END;
