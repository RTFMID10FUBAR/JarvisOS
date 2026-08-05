-- A monotonic change number, so sync has an exact position to resume from.
--
-- Delta sync was built on `updated_at`, and that was wrong twice.
--
-- First the cursor was wall-clock time read at the start of a sync. Any row
-- written in that same millisecond was skipped, and because the client stores
-- the cursor it was skipped again forever — a permanent silent hole. CI hit it
-- by chance.
--
-- Then the cursor carried (updated_at, id) so it pointed at a row rather than
-- an instant. Better, and still not exact: an UPDATE moves a row to a new
-- position, and if that position lands in the same millisecond as the last row
-- already delivered but with a lower id, it sorts *behind* the cursor and is
-- never sent.
--
-- Both failures have the same root: a millisecond timestamp is not a unique,
-- monotonic position, so no amount of care about which timestamp to use can
-- make it one. Two rows can share a millisecond, and a clock can be adjusted
-- underneath a running system.
--
-- This is that position. Every insert and update to a replicated table takes
-- the next number from a single counter. Numbers only ever go up, they are
-- never reused, and `change_seq > cursor` is exact — no ties, no clock, no
-- resolution to reason about. A row is skipped only once it has genuinely been
-- handed to the client.

CREATE TABLE change_counter (
    id   INTEGER PRIMARY KEY CHECK (id = 1),
    next INTEGER NOT NULL
);
INSERT INTO change_counter (id, next) VALUES (1, 0);

-- Every replicated table gains the column. Existing rows are numbered in a
-- stable order so a client that has never synced still receives all of them,
-- and receives them in a deterministic order.
ALTER TABLE matters            ADD COLUMN change_seq INTEGER;
ALTER TABLE documents          ADD COLUMN change_seq INTEGER;
ALTER TABLE issues             ADD COLUMN change_seq INTEGER;
ALTER TABLE deadlines          ADD COLUMN change_seq INTEGER;
ALTER TABLE events             ADD COLUMN change_seq INTEGER;
ALTER TABLE preservation_items ADD COLUMN change_seq INTEGER;
ALTER TABLE access_barriers    ADD COLUMN change_seq INTEGER;




-- Backfill, oldest first, so an existing record replicates in a sensible order.

UPDATE matters SET change_seq = (
    SELECT COUNT(*) FROM matters AS earlier
    WHERE earlier.updated_at < matters.updated_at
       OR (earlier.updated_at = matters.updated_at AND earlier.id <= matters.id)
) + (SELECT next FROM change_counter);
UPDATE change_counter SET next = next + (SELECT COUNT(*) FROM matters);

UPDATE documents SET change_seq = (
    SELECT COUNT(*) FROM documents AS earlier
    WHERE earlier.updated_at < documents.updated_at
       OR (earlier.updated_at = documents.updated_at AND earlier.id <= documents.id)
) + (SELECT next FROM change_counter);
UPDATE change_counter SET next = next + (SELECT COUNT(*) FROM documents);

UPDATE issues SET change_seq = (
    SELECT COUNT(*) FROM issues AS earlier
    WHERE earlier.updated_at < issues.updated_at
       OR (earlier.updated_at = issues.updated_at AND earlier.id <= issues.id)
) + (SELECT next FROM change_counter);
UPDATE change_counter SET next = next + (SELECT COUNT(*) FROM issues);

UPDATE deadlines SET change_seq = (
    SELECT COUNT(*) FROM deadlines AS earlier
    WHERE earlier.updated_at < deadlines.updated_at
       OR (earlier.updated_at = deadlines.updated_at AND earlier.id <= deadlines.id)
) + (SELECT next FROM change_counter);
UPDATE change_counter SET next = next + (SELECT COUNT(*) FROM deadlines);

UPDATE events SET change_seq = (
    SELECT COUNT(*) FROM events AS earlier
    WHERE earlier.updated_at < events.updated_at
       OR (earlier.updated_at = events.updated_at AND earlier.id <= events.id)
) + (SELECT next FROM change_counter);
UPDATE change_counter SET next = next + (SELECT COUNT(*) FROM events);

UPDATE preservation_items SET change_seq = (
    SELECT COUNT(*) FROM preservation_items AS earlier
    WHERE earlier.updated_at < preservation_items.updated_at
       OR (earlier.updated_at = preservation_items.updated_at AND earlier.id <= preservation_items.id)
) + (SELECT next FROM change_counter);
UPDATE change_counter SET next = next + (SELECT COUNT(*) FROM preservation_items);

UPDATE access_barriers SET change_seq = (
    SELECT COUNT(*) FROM access_barriers AS earlier
    WHERE earlier.updated_at < access_barriers.updated_at
       OR (earlier.updated_at = access_barriers.updated_at AND earlier.id <= access_barriers.id)
) + (SELECT next FROM change_counter);
UPDATE change_counter SET next = next + (SELECT COUNT(*) FROM access_barriers);


-- One pair of triggers per table. `recursive_triggers` is off by default in
-- SQLite and open_database asserts it, so the UPDATE inside an AFTER UPDATE
-- trigger does not re-fire it.
--
-- The counter is bumped first and then read, so two rows can never be handed
-- the same number.

CREATE TRIGGER matters_change_seq_insert AFTER INSERT ON matters
BEGIN
    UPDATE change_counter SET next = next + 1;
    UPDATE matters SET change_seq = (SELECT next FROM change_counter) WHERE id = NEW.id;
END;

CREATE TRIGGER matters_change_seq_update AFTER UPDATE ON matters
BEGIN
    UPDATE change_counter SET next = next + 1;
    UPDATE matters SET change_seq = (SELECT next FROM change_counter) WHERE id = NEW.id;
END;

CREATE TRIGGER documents_change_seq_insert AFTER INSERT ON documents
BEGIN
    UPDATE change_counter SET next = next + 1;
    UPDATE documents SET change_seq = (SELECT next FROM change_counter) WHERE id = NEW.id;
END;

CREATE TRIGGER documents_change_seq_update AFTER UPDATE ON documents
BEGIN
    UPDATE change_counter SET next = next + 1;
    UPDATE documents SET change_seq = (SELECT next FROM change_counter) WHERE id = NEW.id;
END;

CREATE TRIGGER issues_change_seq_insert AFTER INSERT ON issues
BEGIN
    UPDATE change_counter SET next = next + 1;
    UPDATE issues SET change_seq = (SELECT next FROM change_counter) WHERE id = NEW.id;
END;

CREATE TRIGGER issues_change_seq_update AFTER UPDATE ON issues
BEGIN
    UPDATE change_counter SET next = next + 1;
    UPDATE issues SET change_seq = (SELECT next FROM change_counter) WHERE id = NEW.id;
END;

CREATE TRIGGER deadlines_change_seq_insert AFTER INSERT ON deadlines
BEGIN
    UPDATE change_counter SET next = next + 1;
    UPDATE deadlines SET change_seq = (SELECT next FROM change_counter) WHERE id = NEW.id;
END;

CREATE TRIGGER deadlines_change_seq_update AFTER UPDATE ON deadlines
BEGIN
    UPDATE change_counter SET next = next + 1;
    UPDATE deadlines SET change_seq = (SELECT next FROM change_counter) WHERE id = NEW.id;
END;

CREATE TRIGGER events_change_seq_insert AFTER INSERT ON events
BEGIN
    UPDATE change_counter SET next = next + 1;
    UPDATE events SET change_seq = (SELECT next FROM change_counter) WHERE id = NEW.id;
END;

CREATE TRIGGER events_change_seq_update AFTER UPDATE ON events
BEGIN
    UPDATE change_counter SET next = next + 1;
    UPDATE events SET change_seq = (SELECT next FROM change_counter) WHERE id = NEW.id;
END;

CREATE TRIGGER preservation_items_change_seq_insert AFTER INSERT ON preservation_items
BEGIN
    UPDATE change_counter SET next = next + 1;
    UPDATE preservation_items SET change_seq = (SELECT next FROM change_counter) WHERE id = NEW.id;
END;

CREATE TRIGGER preservation_items_change_seq_update AFTER UPDATE ON preservation_items
BEGIN
    UPDATE change_counter SET next = next + 1;
    UPDATE preservation_items SET change_seq = (SELECT next FROM change_counter) WHERE id = NEW.id;
END;

CREATE TRIGGER access_barriers_change_seq_insert AFTER INSERT ON access_barriers
BEGIN
    UPDATE change_counter SET next = next + 1;
    UPDATE access_barriers SET change_seq = (SELECT next FROM change_counter) WHERE id = NEW.id;
END;

CREATE TRIGGER access_barriers_change_seq_update AFTER UPDATE ON access_barriers
BEGIN
    UPDATE change_counter SET next = next + 1;
    UPDATE access_barriers SET change_seq = (SELECT next FROM change_counter) WHERE id = NEW.id;
END;

CREATE INDEX idx_matters_change_seq ON matters(change_seq);

CREATE INDEX idx_documents_change_seq ON documents(change_seq);

CREATE INDEX idx_issues_change_seq ON issues(change_seq);

CREATE INDEX idx_deadlines_change_seq ON deadlines(change_seq);

CREATE INDEX idx_events_change_seq ON events(change_seq);

CREATE INDEX idx_preservation_items_change_seq ON preservation_items(change_seq);

CREATE INDEX idx_access_barriers_change_seq ON access_barriers(change_seq);
