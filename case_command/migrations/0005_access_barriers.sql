-- Access barriers: contemporaneous record of what prevented a filing.
--
-- Why this is a first-class table rather than a note.
--
-- When a tribunal requires hand delivery or mail, that requires printing, which
-- requires electricity. If the loss of electricity is itself the subject of the
-- proceeding, the filing requirement and the injury are the same fact. That is
-- not a logistics complaint — it is concrete prejudice to the right to be heard,
-- and it is exactly what issues PSC-020 (loss of electric service during the
-- appeal perfection period) and PSC-021 (actual prejudice to judicial review)
-- are about.
--
-- An abstract assertion of prejudice is weak. A dated log of specific filings
-- that specific barriers prevented, each with the deadline it affected, is
-- evidence. Memory is not: a contemporaneous record made at the time carries
-- weight that a reconstruction months later does not.
--
-- This table stores no facts on its own. Every row is entered by Jacob.

CREATE TABLE access_barriers (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id                INTEGER REFERENCES matters(id),
    issue_id                 INTEGER REFERENCES issues(id),
    title                    TEXT NOT NULL,

    incident_date            TEXT,
    barrier_type             TEXT NOT NULL DEFAULT 'OTHER'
        CHECK (barrier_type IN (
            'NO_ELECTRICITY',     -- service was off
            'NO_PRINTER',         -- no working printer or no supplies
            'NO_INTERNET',        -- no connectivity to e-file or email
            'NO_TRANSPORT',       -- could not travel to file, serve, or appear
            'NO_FUNDS',           -- could not pay postage, copying, or fees
            'DISABILITY',         -- a disability-related barrier
            'HEALTH',             -- medical event prevented action
            'NO_NOTICE',          -- did not receive notice in time to act
            'OTHER')),

    -- What the barrier actually stopped. Concrete beats general.
    what_was_blocked         TEXT,
    deadline_affected        TEXT,
    deadline_date            TEXT,
    deadline_id              INTEGER REFERENCES deadlines(id),
    filing_id                INTEGER REFERENCES filings(id),

    -- What was tried instead, and whether it worked. A barrier that was worked
    -- around still happened, and the effort itself is part of the record.
    workaround_attempted     TEXT,
    workaround_result        TEXT,
    hours_lost               REAL,
    cost_incurred            REAL,

    -- Whether the tribunal was told. An unreported barrier is much harder to
    -- rely on later.
    reported_to_tribunal     INTEGER NOT NULL DEFAULT 0,
    how_reported             TEXT,
    reported_date            TEXT,

    -- Supporting proof: a shutoff notice, a photograph, a receipt, a bounced
    -- e-filing confirmation.
    evidence_document_id     INTEGER REFERENCES documents(id),

    status                   TEXT NOT NULL DEFAULT 'ACTIVE',
    verification_status      TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (verification_status IN ('VERIFIED_PRIMARY','VERIFIED_SECONDARY','PARTIALLY_VERIFIED',
                                       'DISPUTED','INFERENCE','UNKNOWN','MISSING_SOURCE','SUPERSEDED')),
    source_document_id       INTEGER REFERENCES documents(id),
    source_page_or_paragraph TEXT,
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by               TEXT NOT NULL DEFAULT 'jacob',
    last_reviewed_by         TEXT,
    notes                    TEXT
);

CREATE INDEX idx_access_barriers_date ON access_barriers(incident_date);
CREATE INDEX idx_access_barriers_matter ON access_barriers(matter_id);

-- Like every other canonical record, an access barrier is never deleted.
CREATE TRIGGER access_barriers_no_delete BEFORE DELETE ON access_barriers
BEGIN
    SELECT RAISE(ABORT, 'access barriers cannot be deleted; change status instead');
END;
