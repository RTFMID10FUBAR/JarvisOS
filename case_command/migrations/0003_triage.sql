-- Triage state for working through a large, disorganized document set.
--
-- Triage never removes anything. IRRELEVANT and DUPLICATE are statuses on a
-- document that remains in the record, still searchable, still linked. The
-- no-delete trigger on `documents` continues to apply.

ALTER TABLE documents ADD COLUMN triage_status TEXT NOT NULL DEFAULT 'UNREVIEWED';
ALTER TABLE documents ADD COLUMN triage_note   TEXT;
ALTER TABLE documents ADD COLUMN triage_by     TEXT;
ALTER TABLE documents ADD COLUMN triage_at     TEXT;

-- A one-line extract pulled verbatim from the document text, with the locator
-- it came from. This is an EXTRACT, not a generated summary: no model writes it,
-- so it cannot describe something the document does not say.
ALTER TABLE documents ADD COLUMN extract_line     TEXT;
ALTER TABLE documents ADD COLUMN extract_locator  TEXT;

-- Where the document's date came from, so an inferred date is never mistaken
-- for a date stated on the face of the document.
ALTER TABLE documents ADD COLUMN date_source TEXT;

CREATE INDEX idx_documents_triage ON documents(triage_status);
CREATE INDEX idx_documents_date ON documents(document_date);
