-- Physical copies of a document that already exists in the record.
--
-- `documents.sha256` is UNIQUE, so a byte-identical file found in a second
-- location does NOT create a second document row — that is what keeps the
-- record free of phantom duplicates. But the copy's path still has to be
-- recorded somewhere, or the triage list cannot answer "where are the copies?"
-- and a later cleanup could delete the wrong one.
--
-- This table is that record: one canonical document, N known physical locations.

CREATE TABLE document_copies (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id   INTEGER NOT NULL REFERENCES documents(id),
    path          TEXT NOT NULL UNIQUE,
    folder        TEXT,
    sha256        TEXT NOT NULL,
    byte_size     INTEGER,
    discovered_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    still_present INTEGER NOT NULL DEFAULT 1,
    disposition   TEXT NOT NULL DEFAULT 'UNREVIEWED'
        CHECK (disposition IN ('UNREVIEWED','KEEP','ARCHIVE_PROPOSED','ARCHIVED')),
    notes         TEXT
);

CREATE INDEX idx_document_copies_doc ON document_copies(document_id);
CREATE INDEX idx_document_copies_sha ON document_copies(sha256);

-- A copy record is never deleted either. If the file goes away, still_present
-- is set to 0 so the history of where it lived survives.
CREATE TRIGGER document_copies_no_delete BEFORE DELETE ON document_copies
BEGIN
    SELECT RAISE(ABORT, 'document copy records cannot be deleted; set still_present=0');
END;
