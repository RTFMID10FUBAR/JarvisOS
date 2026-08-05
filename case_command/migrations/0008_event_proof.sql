-- Proof for timeline events, and events a person adds by hand.
--
-- Two things drive this table.
--
-- First: every item on a timeline should be able to answer "what proves this?"
-- An event with a document behind it and an event someone remembers are both
-- worth recording, and they are not the same kind of thing. Storing them the
-- same way, in one nullable `source_document_id` column, would make them look
-- alike in every view that reads it. They must not look alike. A hearing is
-- exactly where that difference gets tested.
--
-- Second: an event can have more than one thing supporting it. A disconnection
-- has a utility notice, a photograph, and a memory of the day. One column
-- cannot hold three, and picking the "best" one throws away the other two —
-- including the corroboration that makes the account credible.
--
-- So: one row per piece of proof, typed, each carrying its own locator.

CREATE TABLE event_proof (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id    INTEGER NOT NULL REFERENCES events(id),

    proof_type  TEXT NOT NULL CHECK (proof_type IN (
        'DOCUMENT',            -- something in the record, with a locator
        'PHOTO',               -- an image captured and ingested
        'RECORDING',           -- audio or video in the record
        'THIRD_PARTY_RECORD',  -- a bill, a medical record, a utility log
        'WITNESS',             -- a named person who would say so
        'RECOLLECTION',        -- Jacob's own memory. Never proof of the fact.
        'NONE'                 -- explicitly nothing yet, recorded so the gap is visible
    )),

    -- Documentary proof points at a document and says where in it.
    document_id INTEGER REFERENCES documents(id),
    locator     TEXT,          -- page, paragraph, line, or timestamp

    -- Testimonial proof names who says so. For a recollection that is Jacob.
    asserted_by TEXT,
    -- When the assertion was made, which is not when the event happened. A
    -- memory recorded the same week is a different thing from the same memory
    -- recorded two years later, and a reader is entitled to see the gap.
    asserted_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    -- What this proof actually shows. For documentary proof this should be
    -- quoted or closely paraphrased from the document, not characterised.
    detail      TEXT,
    notes       TEXT,

    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by  TEXT NOT NULL DEFAULT 'jacob',

    -- Documentary proof without a locator is not checkable. "It is in the
    -- record somewhere" cannot be handed to a tribunal.
    CHECK (proof_type NOT IN ('DOCUMENT','PHOTO','RECORDING','THIRD_PARTY_RECORD')
           OR document_id IS NOT NULL),
    CHECK (proof_type <> 'DOCUMENT' OR locator IS NOT NULL),
    -- Testimonial proof has to name who is testifying.
    CHECK (proof_type NOT IN ('WITNESS','RECOLLECTION') OR asserted_by IS NOT NULL)
);

CREATE INDEX idx_event_proof_event ON event_proof(event_id);
CREATE INDEX idx_event_proof_document ON event_proof(document_id);

-- Proof is not deleted. Withdrawing an assertion is itself a fact about the
-- record, and a proof row that quietly vanished would leave an event looking
-- better supported than its history shows.
CREATE TRIGGER event_proof_no_delete BEFORE DELETE ON event_proof
BEGIN
    SELECT RAISE(ABORT, 'event proof cannot be deleted; add a superseding row instead');
END;

-- Events gain the provenance of their own creation. An event read out of a
-- filing and an event typed in from memory are both legitimate; which one this
-- is must survive into every view.
ALTER TABLE events ADD COLUMN origin TEXT NOT NULL DEFAULT 'INGESTED'
    CHECK (origin IN ('INGESTED','MANUAL','FLEET_PROPOSED'));
ALTER TABLE events ADD COLUMN recalled INTEGER NOT NULL DEFAULT 0;
ALTER TABLE events ADD COLUMN date_precision TEXT NOT NULL DEFAULT 'EXACT'
    CHECK (date_precision IN ('EXACT','APPROXIMATE','MONTH_ONLY','YEAR_ONLY','UNKNOWN'));
