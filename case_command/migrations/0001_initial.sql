-- Case Command initial schema.
--
-- Design rules encoded here, not just in application code:
--   * Every canonical record carries the same provenance columns.
--   * verification_status is constrained to the eight approved values.
--   * A filing may not claim FILED_CONFIRMED / DOCKETED / ENTERED without proof.
--   * The audit log is append-only, enforced by triggers.
--   * Canonical litigation records cannot be deleted, only re-statused.
--   * A document is stored once; cross-matter use is a link, never a copy.

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- matters
-- ---------------------------------------------------------------------------
CREATE TABLE matters (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id                INTEGER,                    -- self-reference; set to own id
    parent_matter_id         INTEGER REFERENCES matters(id),
    slug                     TEXT NOT NULL UNIQUE,
    title                    TEXT NOT NULL,
    caption                  TEXT,
    case_number              TEXT,
    forum                    TEXT,
    forum_type               TEXT,
    folder                   TEXT NOT NULL,
    posture                  TEXT,
    status                   TEXT NOT NULL DEFAULT 'ACTIVE',
    verification_status      TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (verification_status IN ('VERIFIED_PRIMARY','VERIFIED_SECONDARY','PARTIALLY_VERIFIED',
                                       'DISPUTED','INFERENCE','UNKNOWN','MISSING_SOURCE','SUPERSEDED')),
    source_document_id       INTEGER,
    source_page_or_paragraph TEXT,
    boundary_date            TEXT,                       -- e.g. PSC final order date
    boundary_label           TEXT,
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by               TEXT NOT NULL DEFAULT 'system',
    last_reviewed_by         TEXT,
    notes                    TEXT
);

-- Related-but-separate matters. Linking must never imply merging.
CREATE TABLE matter_links (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id      INTEGER NOT NULL REFERENCES matters(id),
    related_matter_id INTEGER NOT NULL REFERENCES matters(id),
    relationship   TEXT NOT NULL,
    notes          TEXT,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by     TEXT NOT NULL DEFAULT 'system',
    UNIQUE (matter_id, related_matter_id, relationship),
    CHECK (matter_id <> related_matter_id)
);

-- ---------------------------------------------------------------------------
-- documents
-- ---------------------------------------------------------------------------
CREATE TABLE documents (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_uid                  TEXT NOT NULL UNIQUE,       -- canonical ID, e.g. CC-DOC-000042
    matter_id                INTEGER REFERENCES matters(id),
    title                    TEXT NOT NULL,
    original_filename        TEXT NOT NULL,
    storage_path             TEXT NOT NULL,              -- single physical location
    folder                   TEXT NOT NULL,
    sha256                   TEXT NOT NULL UNIQUE,
    byte_size                INTEGER NOT NULL,
    mime_type                TEXT,
    file_kind                TEXT,
    page_count               INTEGER,
    text_path                TEXT,
    text_method              TEXT,                       -- native | ocr | none | partial
    text_confidence          REAL,
    text_chars               INTEGER,
    ocr_used                 INTEGER NOT NULL DEFAULT 0,
    extraction_error         TEXT,
    analysis_version         INTEGER NOT NULL DEFAULT 0,
    document_date            TEXT,
    filed_date               TEXT,
    served_date              TEXT,
    classification_rule      TEXT,
    classification_confidence REAL,
    classification_approved  INTEGER NOT NULL DEFAULT 0,
    duplicate_of_id          INTEGER REFERENCES documents(id),
    status                   TEXT NOT NULL DEFAULT 'ACTIVE',
    verification_status      TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (verification_status IN ('VERIFIED_PRIMARY','VERIFIED_SECONDARY','PARTIALLY_VERIFIED',
                                       'DISPUTED','INFERENCE','UNKNOWN','MISSING_SOURCE','SUPERSEDED')),
    source_document_id       INTEGER REFERENCES documents(id),
    source_page_or_paragraph TEXT,
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by               TEXT NOT NULL DEFAULT 'system',
    last_reviewed_by         TEXT,
    notes                    TEXT
);
CREATE INDEX idx_documents_sha ON documents(sha256);
CREATE INDEX idx_documents_matter ON documents(matter_id);
CREATE INDEX idx_documents_folder ON documents(folder);

-- Store once, link many. This table is how a document serves several matters
-- without ever being copied into a second folder.
CREATE TABLE document_matter_links (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id         INTEGER NOT NULL REFERENCES documents(id),
    matter_id           INTEGER NOT NULL REFERENCES matters(id),
    relationship        TEXT NOT NULL DEFAULT 'RELEVANT',
    limited_purpose     TEXT,
    boundary_classification TEXT
        CHECK (boundary_classification IS NULL OR boundary_classification IN
               ('CASE_1_DECIDED_ISSUE','POST_FINAL_ORDER_NEW_CONDUCT',
                'PRIOR_EVIDENCE_FOR_LIMITED_PURPOSE','PROCEDURAL_HISTORY','UNKNOWN')),
    approved            INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by          TEXT NOT NULL DEFAULT 'system',
    notes               TEXT,
    UNIQUE (document_id, matter_id, relationship)
);
CREATE INDEX idx_dml_document ON document_matter_links(document_id);
CREATE INDEX idx_dml_matter ON document_matter_links(matter_id);

CREATE TABLE document_versions (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id                INTEGER REFERENCES matters(id),
    document_id              INTEGER NOT NULL REFERENCES documents(id),
    version_number           INTEGER NOT NULL,
    sha256                   TEXT NOT NULL,
    storage_path             TEXT NOT NULL,
    byte_size                INTEGER,
    title                    TEXT NOT NULL,
    status                   TEXT NOT NULL DEFAULT 'ACTIVE',
    verification_status      TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (verification_status IN ('VERIFIED_PRIMARY','VERIFIED_SECONDARY','PARTIALLY_VERIFIED',
                                       'DISPUTED','INFERENCE','UNKNOWN','MISSING_SOURCE','SUPERSEDED')),
    source_document_id       INTEGER REFERENCES documents(id),
    source_page_or_paragraph TEXT,
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by               TEXT NOT NULL DEFAULT 'system',
    last_reviewed_by         TEXT,
    notes                    TEXT,
    UNIQUE (document_id, version_number)
);

-- ---------------------------------------------------------------------------
-- filings and orders
-- ---------------------------------------------------------------------------
CREATE TABLE filings (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id                INTEGER REFERENCES matters(id),
    document_id              INTEGER REFERENCES documents(id),
    title                    TEXT NOT NULL,
    filing_type              TEXT,
    filed_by                 TEXT,
    filed_date               TEXT,
    served_date              TEXT,
    docket_number            TEXT,
    filing_status            TEXT NOT NULL DEFAULT 'DRAFT'
        CHECK (filing_status IN ('DRAFT','READY_FOR_REVIEW','APPROVED','SENT','FILED_UNCONFIRMED',
                                 'FILED_CONFIRMED','DOCKETED','ENTERED','REJECTED','SUPERSEDED')),
    -- Drive presence is never proof of filing. A confirmed status requires one
    -- of the approved proof types plus a pointer to the proof itself.
    proof_type               TEXT
        CHECK (proof_type IS NULL OR proof_type IN ('DOCKET_ENTRY','CLERK_CONFIRMATION','STAMPED_COPY',
                                                    'ELECTRONIC_RECEIPT','OFFICIAL_ORDER','VERIFIED_SERVICE_RECEIPT')),
    proof_document_id        INTEGER REFERENCES documents(id),
    proof_reference          TEXT,
    status                   TEXT NOT NULL DEFAULT 'ACTIVE',
    verification_status      TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (verification_status IN ('VERIFIED_PRIMARY','VERIFIED_SECONDARY','PARTIALLY_VERIFIED',
                                       'DISPUTED','INFERENCE','UNKNOWN','MISSING_SOURCE','SUPERSEDED')),
    source_document_id       INTEGER REFERENCES documents(id),
    source_page_or_paragraph TEXT,
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by               TEXT NOT NULL DEFAULT 'system',
    last_reviewed_by         TEXT,
    notes                    TEXT,
    CHECK (filing_status NOT IN ('FILED_CONFIRMED','DOCKETED','ENTERED')
           OR (proof_type IS NOT NULL AND (proof_document_id IS NOT NULL OR proof_reference IS NOT NULL)))
);
CREATE INDEX idx_filings_matter ON filings(matter_id);

CREATE TABLE orders (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id                INTEGER REFERENCES matters(id),
    document_id              INTEGER REFERENCES documents(id),
    title                    TEXT NOT NULL,
    order_type               TEXT,
    entered_date             TEXT,
    issued_by                TEXT,
    is_final                 INTEGER NOT NULL DEFAULT 0,
    is_recommended_decision  INTEGER NOT NULL DEFAULT 0,
    disposition              TEXT,
    appeal_deadline          TEXT,
    exception_deadline       TEXT,
    status                   TEXT NOT NULL DEFAULT 'ACTIVE',
    verification_status      TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (verification_status IN ('VERIFIED_PRIMARY','VERIFIED_SECONDARY','PARTIALLY_VERIFIED',
                                       'DISPUTED','INFERENCE','UNKNOWN','MISSING_SOURCE','SUPERSEDED')),
    source_document_id       INTEGER REFERENCES documents(id),
    source_page_or_paragraph TEXT,
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by               TEXT NOT NULL DEFAULT 'system',
    last_reviewed_by         TEXT,
    notes                    TEXT
);

-- ---------------------------------------------------------------------------
-- events (timeline)
-- ---------------------------------------------------------------------------
CREATE TABLE events (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id                INTEGER REFERENCES matters(id),
    title                    TEXT NOT NULL,
    event_date               TEXT,
    event_end_date           TEXT,
    event_type               TEXT,
    actor_id                 INTEGER,
    actor_name               TEXT,
    legal_significance       TEXT,
    boundary_classification  TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (boundary_classification IN
               ('CASE_1_DECIDED_ISSUE','POST_FINAL_ORDER_NEW_CONDUCT',
                'PRIOR_EVIDENCE_FOR_LIMITED_PURPOSE','PROCEDURAL_HISTORY','UNKNOWN','NOT_APPLICABLE')),
    disputed                 INTEGER NOT NULL DEFAULT 0,
    approved                 INTEGER NOT NULL DEFAULT 0,
    status                   TEXT NOT NULL DEFAULT 'ACTIVE',
    verification_status      TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (verification_status IN ('VERIFIED_PRIMARY','VERIFIED_SECONDARY','PARTIALLY_VERIFIED',
                                       'DISPUTED','INFERENCE','UNKNOWN','MISSING_SOURCE','SUPERSEDED')),
    source_document_id       INTEGER REFERENCES documents(id),
    source_page_or_paragraph TEXT,
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by               TEXT NOT NULL DEFAULT 'system',
    last_reviewed_by         TEXT,
    notes                    TEXT
);
CREATE INDEX idx_events_matter_date ON events(matter_id, event_date);

-- ---------------------------------------------------------------------------
-- facts
-- ---------------------------------------------------------------------------
CREATE TABLE facts (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id                INTEGER REFERENCES matters(id),
    title                    TEXT NOT NULL,
    statement                TEXT,
    fact_date                TEXT,
    disputed                 INTEGER NOT NULL DEFAULT 0,
    approved                 INTEGER NOT NULL DEFAULT 0,
    status                   TEXT NOT NULL DEFAULT 'ACTIVE',
    verification_status      TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (verification_status IN ('VERIFIED_PRIMARY','VERIFIED_SECONDARY','PARTIALLY_VERIFIED',
                                       'DISPUTED','INFERENCE','UNKNOWN','MISSING_SOURCE','SUPERSEDED')),
    source_document_id       INTEGER REFERENCES documents(id),
    source_page_or_paragraph TEXT,
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by               TEXT NOT NULL DEFAULT 'system',
    last_reviewed_by         TEXT,
    notes                    TEXT
);
CREATE INDEX idx_facts_matter ON facts(matter_id);

-- ---------------------------------------------------------------------------
-- issues (the spine of the issue matrix)
-- ---------------------------------------------------------------------------
CREATE TABLE issues (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id                INTEGER REFERENCES matters(id),
    issue_key                TEXT UNIQUE,
    title                    TEXT NOT NULL,
    legal_element            TEXT,
    inference                TEXT,
    best_reply               TEXT,
    opponent_defense         TEXT,
    missing_proof            TEXT,
    requested_finding        TEXT,
    requested_relief         TEXT,
    appeal_standard          TEXT,
    risk_rating              TEXT,
    hearing_scope            TEXT,          -- IN_SCOPE | OUTSIDE_CURRENT_HEARING | CONDITIONAL
    boundary_classification  TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (boundary_classification IN
               ('CASE_1_DECIDED_ISSUE','POST_FINAL_ORDER_NEW_CONDUCT',
                'PRIOR_EVIDENCE_FOR_LIMITED_PURPOSE','PROCEDURAL_HISTORY','UNKNOWN','NOT_APPLICABLE')),
    -- An issue is never deleted. It may only move between these states.
    status                   TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE','RESERVED','WEAK','MISSING_PROOF','OUTSIDE_CURRENT_HEARING',
                          'SUPERSEDED_BY_AUTHORITY','DECIDED')),
    verification_status      TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (verification_status IN ('VERIFIED_PRIMARY','VERIFIED_SECONDARY','PARTIALLY_VERIFIED',
                                       'DISPUTED','INFERENCE','UNKNOWN','MISSING_SOURCE','SUPERSEDED')),
    source_document_id       INTEGER REFERENCES documents(id),
    source_page_or_paragraph TEXT,
    protected                INTEGER NOT NULL DEFAULT 0,   -- preloaded issues: cannot be deleted
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by               TEXT NOT NULL DEFAULT 'system',
    last_reviewed_by         TEXT,
    notes                    TEXT
);
CREATE INDEX idx_issues_matter ON issues(matter_id);

CREATE TABLE issue_links (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id       INTEGER NOT NULL REFERENCES issues(id),
    linked_type    TEXT NOT NULL,   -- fact | evidence | authority | event | document | filing | order | rule
    linked_id      INTEGER NOT NULL,
    role           TEXT,            -- supports | disputes | element_of | context
    approved       INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by     TEXT NOT NULL DEFAULT 'system',
    notes          TEXT,
    UNIQUE (issue_id, linked_type, linked_id, role)
);
CREATE INDEX idx_issue_links_issue ON issue_links(issue_id);

-- ---------------------------------------------------------------------------
-- claims, defenses, authorities, rules, tariffs
-- ---------------------------------------------------------------------------
CREATE TABLE claims (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id                INTEGER REFERENCES matters(id),
    issue_id                 INTEGER REFERENCES issues(id),
    title                    TEXT NOT NULL,
    elements                 TEXT,
    asserted_by              TEXT,
    status                   TEXT NOT NULL DEFAULT 'ACTIVE',
    verification_status      TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (verification_status IN ('VERIFIED_PRIMARY','VERIFIED_SECONDARY','PARTIALLY_VERIFIED',
                                       'DISPUTED','INFERENCE','UNKNOWN','MISSING_SOURCE','SUPERSEDED')),
    source_document_id       INTEGER REFERENCES documents(id),
    source_page_or_paragraph TEXT,
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by               TEXT NOT NULL DEFAULT 'system',
    last_reviewed_by         TEXT,
    notes                    TEXT
);

CREATE TABLE defenses (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id                INTEGER REFERENCES matters(id),
    issue_id                 INTEGER REFERENCES issues(id),
    title                    TEXT NOT NULL,
    raised_by                TEXT,
    strength                 TEXT,
    best_reply               TEXT,
    status                   TEXT NOT NULL DEFAULT 'ACTIVE',
    verification_status      TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (verification_status IN ('VERIFIED_PRIMARY','VERIFIED_SECONDARY','PARTIALLY_VERIFIED',
                                       'DISPUTED','INFERENCE','UNKNOWN','MISSING_SOURCE','SUPERSEDED')),
    source_document_id       INTEGER REFERENCES documents(id),
    source_page_or_paragraph TEXT,
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by               TEXT NOT NULL DEFAULT 'system',
    last_reviewed_by         TEXT,
    notes                    TEXT
);

CREATE TABLE authorities (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id                INTEGER REFERENCES matters(id),
    title                    TEXT NOT NULL,
    citation                 TEXT,
    authority_type           TEXT,
    jurisdiction             TEXT,
    holding                  TEXT,
    citation_verified        INTEGER NOT NULL DEFAULT 0,
    citation_verified_source TEXT,
    status                   TEXT NOT NULL DEFAULT 'ACTIVE',
    verification_status      TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (verification_status IN ('VERIFIED_PRIMARY','VERIFIED_SECONDARY','PARTIALLY_VERIFIED',
                                       'DISPUTED','INFERENCE','UNKNOWN','MISSING_SOURCE','SUPERSEDED')),
    source_document_id       INTEGER REFERENCES documents(id),
    source_page_or_paragraph TEXT,
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by               TEXT NOT NULL DEFAULT 'system',
    last_reviewed_by         TEXT,
    notes                    TEXT
);

CREATE TABLE rules (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id                INTEGER REFERENCES matters(id),
    title                    TEXT NOT NULL,
    rule_number              TEXT,
    rule_body                TEXT,
    elements                 TEXT,           -- JSON array of element strings
    status                   TEXT NOT NULL DEFAULT 'ACTIVE',
    verification_status      TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (verification_status IN ('VERIFIED_PRIMARY','VERIFIED_SECONDARY','PARTIALLY_VERIFIED',
                                       'DISPUTED','INFERENCE','UNKNOWN','MISSING_SOURCE','SUPERSEDED')),
    source_document_id       INTEGER REFERENCES documents(id),
    source_page_or_paragraph TEXT,
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by               TEXT NOT NULL DEFAULT 'system',
    last_reviewed_by         TEXT,
    notes                    TEXT
);

CREATE TABLE tariffs (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id                INTEGER REFERENCES matters(id),
    title                    TEXT NOT NULL,
    tariff_number            TEXT,
    utility                  TEXT,
    effective_date           TEXT,
    provision_text           TEXT,
    status                   TEXT NOT NULL DEFAULT 'ACTIVE',
    verification_status      TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (verification_status IN ('VERIFIED_PRIMARY','VERIFIED_SECONDARY','PARTIALLY_VERIFIED',
                                       'DISPUTED','INFERENCE','UNKNOWN','MISSING_SOURCE','SUPERSEDED')),
    source_document_id       INTEGER REFERENCES documents(id),
    source_page_or_paragraph TEXT,
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by               TEXT NOT NULL DEFAULT 'system',
    last_reviewed_by         TEXT,
    notes                    TEXT
);

-- ---------------------------------------------------------------------------
-- evidence
-- ---------------------------------------------------------------------------
CREATE TABLE evidence (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id                INTEGER REFERENCES matters(id),
    document_id              INTEGER REFERENCES documents(id),
    title                    TEXT NOT NULL,
    evidence_type            TEXT,
    exhibit_number           TEXT,
    proves                   TEXT,
    admissibility_notes      TEXT,
    shared_across_matters    INTEGER NOT NULL DEFAULT 0,
    status                   TEXT NOT NULL DEFAULT 'ACTIVE',
    verification_status      TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (verification_status IN ('VERIFIED_PRIMARY','VERIFIED_SECONDARY','PARTIALLY_VERIFIED',
                                       'DISPUTED','INFERENCE','UNKNOWN','MISSING_SOURCE','SUPERSEDED')),
    source_document_id       INTEGER REFERENCES documents(id),
    source_page_or_paragraph TEXT,
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by               TEXT NOT NULL DEFAULT 'system',
    last_reviewed_by         TEXT,
    notes                    TEXT
);

-- ---------------------------------------------------------------------------
-- people: actors, judges, aljs, counsel
-- ---------------------------------------------------------------------------
CREATE TABLE actors (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id                INTEGER REFERENCES matters(id),
    title                    TEXT NOT NULL,          -- display name
    actor_type               TEXT,                   -- party | agency | utility | witness | staff
    role                     TEXT,
    organization             TEXT,
    status                   TEXT NOT NULL DEFAULT 'ACTIVE',
    verification_status      TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (verification_status IN ('VERIFIED_PRIMARY','VERIFIED_SECONDARY','PARTIALLY_VERIFIED',
                                       'DISPUTED','INFERENCE','UNKNOWN','MISSING_SOURCE','SUPERSEDED')),
    source_document_id       INTEGER REFERENCES documents(id),
    source_page_or_paragraph TEXT,
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by               TEXT NOT NULL DEFAULT 'system',
    last_reviewed_by         TEXT,
    notes                    TEXT
);

CREATE TABLE judges (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id                INTEGER REFERENCES matters(id),
    title                    TEXT NOT NULL,
    court                    TEXT,
    assigned_date            TEXT,
    reassigned_date          TEXT,
    status                   TEXT NOT NULL DEFAULT 'ACTIVE',
    verification_status      TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (verification_status IN ('VERIFIED_PRIMARY','VERIFIED_SECONDARY','PARTIALLY_VERIFIED',
                                       'DISPUTED','INFERENCE','UNKNOWN','MISSING_SOURCE','SUPERSEDED')),
    source_document_id       INTEGER REFERENCES documents(id),
    source_page_or_paragraph TEXT,
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by               TEXT NOT NULL DEFAULT 'system',
    last_reviewed_by         TEXT,
    notes                    TEXT
);

CREATE TABLE aljs (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id                INTEGER REFERENCES matters(id),
    title                    TEXT NOT NULL,
    agency                   TEXT,
    assigned_date            TEXT,
    reassigned_date          TEXT,
    status                   TEXT NOT NULL DEFAULT 'ACTIVE',
    verification_status      TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (verification_status IN ('VERIFIED_PRIMARY','VERIFIED_SECONDARY','PARTIALLY_VERIFIED',
                                       'DISPUTED','INFERENCE','UNKNOWN','MISSING_SOURCE','SUPERSEDED')),
    source_document_id       INTEGER REFERENCES documents(id),
    source_page_or_paragraph TEXT,
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by               TEXT NOT NULL DEFAULT 'system',
    last_reviewed_by         TEXT,
    notes                    TEXT
);

CREATE TABLE counsel (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id                INTEGER REFERENCES matters(id),
    title                    TEXT NOT NULL,
    firm                     TEXT,
    represents               TEXT,
    bar_number               TEXT,
    contact                  TEXT,
    status                   TEXT NOT NULL DEFAULT 'ACTIVE',
    verification_status      TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (verification_status IN ('VERIFIED_PRIMARY','VERIFIED_SECONDARY','PARTIALLY_VERIFIED',
                                       'DISPUTED','INFERENCE','UNKNOWN','MISSING_SOURCE','SUPERSEDED')),
    source_document_id       INTEGER REFERENCES documents(id),
    source_page_or_paragraph TEXT,
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by               TEXT NOT NULL DEFAULT 'system',
    last_reviewed_by         TEXT,
    notes                    TEXT
);

-- ---------------------------------------------------------------------------
-- deadlines, motions, rulings, relief
-- ---------------------------------------------------------------------------
CREATE TABLE deadlines (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id                INTEGER REFERENCES matters(id),
    issue_id                 INTEGER REFERENCES issues(id),
    title                    TEXT NOT NULL,
    due_date                 TEXT,
    deadline_type            TEXT,          -- appeal | exception | response | hearing | service
    trigger_event            TEXT,
    trigger_order_id         INTEGER REFERENCES orders(id),
    days_allowed             INTEGER,
    satisfied                INTEGER NOT NULL DEFAULT 0,
    satisfied_by_filing_id   INTEGER REFERENCES filings(id),
    status                   TEXT NOT NULL DEFAULT 'ACTIVE',
    verification_status      TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (verification_status IN ('VERIFIED_PRIMARY','VERIFIED_SECONDARY','PARTIALLY_VERIFIED',
                                       'DISPUTED','INFERENCE','UNKNOWN','MISSING_SOURCE','SUPERSEDED')),
    source_document_id       INTEGER REFERENCES documents(id),
    source_page_or_paragraph TEXT,
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by               TEXT NOT NULL DEFAULT 'system',
    last_reviewed_by         TEXT,
    notes                    TEXT
);
CREATE INDEX idx_deadlines_due ON deadlines(due_date);

CREATE TABLE motions (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id                INTEGER REFERENCES matters(id),
    issue_id                 INTEGER REFERENCES issues(id),
    filing_id                INTEGER REFERENCES filings(id),
    title                    TEXT NOT NULL,
    motion_type              TEXT,
    filed_date               TEXT,
    relief_sought            TEXT,
    ruled_on                 INTEGER NOT NULL DEFAULT 0,
    ruling_id                INTEGER,
    threshold_motion         INTEGER NOT NULL DEFAULT 0,
    status                   TEXT NOT NULL DEFAULT 'ACTIVE',
    verification_status      TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (verification_status IN ('VERIFIED_PRIMARY','VERIFIED_SECONDARY','PARTIALLY_VERIFIED',
                                       'DISPUTED','INFERENCE','UNKNOWN','MISSING_SOURCE','SUPERSEDED')),
    source_document_id       INTEGER REFERENCES documents(id),
    source_page_or_paragraph TEXT,
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by               TEXT NOT NULL DEFAULT 'system',
    last_reviewed_by         TEXT,
    notes                    TEXT
);

CREATE TABLE rulings (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id                INTEGER REFERENCES matters(id),
    motion_id                INTEGER REFERENCES motions(id),
    order_id                 INTEGER REFERENCES orders(id),
    title                    TEXT NOT NULL,
    ruled_date               TEXT,
    disposition              TEXT,
    reasoning                TEXT,
    status                   TEXT NOT NULL DEFAULT 'ACTIVE',
    verification_status      TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (verification_status IN ('VERIFIED_PRIMARY','VERIFIED_SECONDARY','PARTIALLY_VERIFIED',
                                       'DISPUTED','INFERENCE','UNKNOWN','MISSING_SOURCE','SUPERSEDED')),
    source_document_id       INTEGER REFERENCES documents(id),
    source_page_or_paragraph TEXT,
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by               TEXT NOT NULL DEFAULT 'system',
    last_reviewed_by         TEXT,
    notes                    TEXT
);

CREATE TABLE relief (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id                INTEGER REFERENCES matters(id),
    issue_id                 INTEGER REFERENCES issues(id),
    title                    TEXT NOT NULL,
    relief_type              TEXT,
    requested_in_filing_id   INTEGER REFERENCES filings(id),
    disposition              TEXT,
    granted                  INTEGER,
    status                   TEXT NOT NULL DEFAULT 'ACTIVE',
    verification_status      TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (verification_status IN ('VERIFIED_PRIMARY','VERIFIED_SECONDARY','PARTIALLY_VERIFIED',
                                       'DISPUTED','INFERENCE','UNKNOWN','MISSING_SOURCE','SUPERSEDED')),
    source_document_id       INTEGER REFERENCES documents(id),
    source_page_or_paragraph TEXT,
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by               TEXT NOT NULL DEFAULT 'system',
    last_reviewed_by         TEXT,
    notes                    TEXT
);

-- ---------------------------------------------------------------------------
-- preservation, contradictions, unknowns
-- ---------------------------------------------------------------------------
CREATE TABLE preservation_items (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id                INTEGER REFERENCES matters(id),
    issue_id                 INTEGER REFERENCES issues(id),
    title                    TEXT NOT NULL,
    raised                   INTEGER NOT NULL DEFAULT 0,
    where_raised             TEXT,
    date_raised              TEXT,
    ruling_requested         INTEGER NOT NULL DEFAULT 0,
    ruling_issued            INTEGER NOT NULL DEFAULT 0,
    ruling_id                INTEGER REFERENCES rulings(id),
    ignored                  INTEGER NOT NULL DEFAULT 0,
    exception_required       INTEGER NOT NULL DEFAULT 0,
    exception_filed          INTEGER NOT NULL DEFAULT 0,
    final_order_treatment    TEXT,
    appeal_deadline          TEXT,
    standard_of_review       TEXT,
    remedy                   TEXT,
    risk                     TEXT,
    status                   TEXT NOT NULL DEFAULT 'ACTIVE',
    verification_status      TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (verification_status IN ('VERIFIED_PRIMARY','VERIFIED_SECONDARY','PARTIALLY_VERIFIED',
                                       'DISPUTED','INFERENCE','UNKNOWN','MISSING_SOURCE','SUPERSEDED')),
    source_document_id       INTEGER REFERENCES documents(id),
    source_page_or_paragraph TEXT,
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by               TEXT NOT NULL DEFAULT 'system',
    last_reviewed_by         TEXT,
    notes                    TEXT
);

CREATE TABLE contradictions (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id                INTEGER REFERENCES matters(id),
    issue_id                 INTEGER REFERENCES issues(id),
    title                    TEXT NOT NULL,
    left_type                TEXT,
    left_id                  INTEGER,
    left_statement           TEXT,
    left_source_document_id  INTEGER REFERENCES documents(id),
    left_source_locator      TEXT,
    right_type               TEXT,
    right_id                 INTEGER,
    right_statement          TEXT,
    right_source_document_id INTEGER REFERENCES documents(id),
    right_source_locator     TEXT,
    resolution               TEXT,
    resolved                 INTEGER NOT NULL DEFAULT 0,
    status                   TEXT NOT NULL DEFAULT 'ACTIVE',
    verification_status      TEXT NOT NULL DEFAULT 'DISPUTED'
        CHECK (verification_status IN ('VERIFIED_PRIMARY','VERIFIED_SECONDARY','PARTIALLY_VERIFIED',
                                       'DISPUTED','INFERENCE','UNKNOWN','MISSING_SOURCE','SUPERSEDED')),
    source_document_id       INTEGER REFERENCES documents(id),
    source_page_or_paragraph TEXT,
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by               TEXT NOT NULL DEFAULT 'system',
    last_reviewed_by         TEXT,
    notes                    TEXT
);

CREATE TABLE unknowns (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id                INTEGER REFERENCES matters(id),
    issue_id                 INTEGER REFERENCES issues(id),
    title                    TEXT NOT NULL,
    question                 TEXT,
    why_it_matters           TEXT,
    how_to_resolve           TEXT,
    resolved                 INTEGER NOT NULL DEFAULT 0,
    status                   TEXT NOT NULL DEFAULT 'ACTIVE',
    verification_status      TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (verification_status IN ('VERIFIED_PRIMARY','VERIFIED_SECONDARY','PARTIALLY_VERIFIED',
                                       'DISPUTED','INFERENCE','UNKNOWN','MISSING_SOURCE','SUPERSEDED')),
    source_document_id       INTEGER REFERENCES documents(id),
    source_page_or_paragraph TEXT,
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by               TEXT NOT NULL DEFAULT 'system',
    last_reviewed_by         TEXT,
    notes                    TEXT
);

-- ---------------------------------------------------------------------------
-- fleet_proposals
-- ---------------------------------------------------------------------------
CREATE TABLE fleet_proposals (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id                   TEXT NOT NULL UNIQUE,
    matter_id                INTEGER REFERENCES matters(id),
    title                    TEXT NOT NULL,
    job_type                 TEXT NOT NULL,
    agent                    TEXT,
    documents_reviewed       TEXT,     -- JSON array of doc_uid
    proposed_facts           TEXT,     -- JSON
    proposed_issue_updates   TEXT,     -- JSON
    conflicts_found          TEXT,     -- JSON
    missing_sources          TEXT,     -- JSON
    defense_attacks          TEXT,     -- JSON
    recommended_repairs      TEXT,     -- JSON
    confidence               REAL,
    citations                TEXT,     -- JSON
    approval_required        INTEGER NOT NULL DEFAULT 1,
    review_status            TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (review_status IN ('PENDING','APPROVED','PARTIALLY_APPROVED','REJECTED','SUPERSEDED')),
    reviewed_by              TEXT,
    reviewed_at              TEXT,
    review_notes             TEXT,
    raw_payload              TEXT,
    status                   TEXT NOT NULL DEFAULT 'ACTIVE',
    verification_status      TEXT NOT NULL DEFAULT 'INFERENCE'
        CHECK (verification_status IN ('VERIFIED_PRIMARY','VERIFIED_SECONDARY','PARTIALLY_VERIFIED',
                                       'DISPUTED','INFERENCE','UNKNOWN','MISSING_SOURCE','SUPERSEDED')),
    source_document_id       INTEGER REFERENCES documents(id),
    source_page_or_paragraph TEXT,
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_by               TEXT NOT NULL DEFAULT 'fleet',
    last_reviewed_by         TEXT,
    notes                    TEXT
);

-- Individual proposed changes inside a Fleet job, approved or rejected one by one.
CREATE TABLE fleet_proposal_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id   INTEGER NOT NULL REFERENCES fleet_proposals(id),
    item_type     TEXT NOT NULL,          -- fact | issue_update | conflict | missing_source | ...
    target_table  TEXT,
    target_id     INTEGER,
    payload       TEXT NOT NULL,          -- JSON
    source_document_id INTEGER REFERENCES documents(id),
    source_page_or_paragraph TEXT,
    decision      TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (decision IN ('PENDING','APPROVED','REJECTED')),
    decided_by    TEXT,
    decided_at    TEXT,
    applied       INTEGER NOT NULL DEFAULT 0,
    applied_record_id INTEGER,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    notes         TEXT
);
CREATE INDEX idx_fpi_proposal ON fleet_proposal_items(proposal_id);

-- ---------------------------------------------------------------------------
-- audit_log (append-only, hash-chained)
-- ---------------------------------------------------------------------------
CREATE TABLE audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    actor         TEXT NOT NULL,
    action        TEXT NOT NULL,
    target_table  TEXT,
    target_id     INTEGER,
    matter_id     INTEGER,
    summary       TEXT,
    payload       TEXT,
    prev_hash     TEXT,
    entry_hash    TEXT NOT NULL
);
CREATE INDEX idx_audit_target ON audit_log(target_table, target_id);
CREATE INDEX idx_audit_ts ON audit_log(ts);

CREATE TRIGGER audit_log_no_update BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only: updates are not permitted');
END;

CREATE TRIGGER audit_log_no_delete BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only: deletes are not permitted');
END;

-- ---------------------------------------------------------------------------
-- No canonical litigation record may be deleted. Status changes only.
-- ---------------------------------------------------------------------------
CREATE TRIGGER issues_no_delete BEFORE DELETE ON issues
BEGIN
    SELECT RAISE(ABORT, 'issues cannot be deleted; change status instead');
END;

CREATE TRIGGER facts_no_delete BEFORE DELETE ON facts
BEGIN
    SELECT RAISE(ABORT, 'facts cannot be deleted; change status instead');
END;

CREATE TRIGGER evidence_no_delete BEFORE DELETE ON evidence
BEGIN
    SELECT RAISE(ABORT, 'evidence cannot be deleted; change status instead');
END;

CREATE TRIGGER documents_no_delete BEFORE DELETE ON documents
BEGIN
    SELECT RAISE(ABORT, 'documents cannot be deleted; change status instead');
END;

CREATE TRIGGER preservation_no_delete BEFORE DELETE ON preservation_items
BEGIN
    SELECT RAISE(ABORT, 'preservation items cannot be deleted; change status instead');
END;

CREATE TRIGGER contradictions_no_delete BEFORE DELETE ON contradictions
BEGIN
    SELECT RAISE(ABORT, 'contradictions cannot be deleted; resolve them instead');
END;

CREATE TRIGGER unknowns_no_delete BEFORE DELETE ON unknowns
BEGIN
    SELECT RAISE(ABORT, 'unknowns cannot be deleted; resolve them instead');
END;

CREATE TRIGGER matters_no_delete BEFORE DELETE ON matters
BEGIN
    SELECT RAISE(ABORT, 'matters cannot be deleted; change status instead');
END;

-- ---------------------------------------------------------------------------
-- ingestion queue (durable; survives restart)
-- ---------------------------------------------------------------------------
CREATE TABLE ingest_queue (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    path           TEXT NOT NULL,
    folder         TEXT,
    discovered_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    started_at     TEXT,
    finished_at    TEXT,
    state          TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (state IN ('PENDING','IN_PROGRESS','DONE','FAILED','SKIPPED')),
    attempts       INTEGER NOT NULL DEFAULT 0,
    last_error     TEXT,
    document_id    INTEGER REFERENCES documents(id),
    UNIQUE (path, state) ON CONFLICT IGNORE
);
CREATE INDEX idx_queue_state ON ingest_queue(state);

-- Cached extracted text keyed by content hash, so unchanged documents are never
-- re-extracted, re-OCR'd, or re-summarized.
CREATE TABLE text_cache (
    sha256           TEXT PRIMARY KEY,
    text_path        TEXT NOT NULL,
    method           TEXT NOT NULL,
    confidence       REAL,
    char_count       INTEGER,
    page_count       INTEGER,
    analysis_version INTEGER NOT NULL DEFAULT 1,
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- Full-text search over extracted document text.
CREATE VIRTUAL TABLE document_fts USING fts5(
    doc_uid UNINDEXED,
    title,
    body,
    tokenize = 'porter'
);

-- Pending human decisions surfaced by ingestion and by Fleet.
CREATE TABLE approvals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    kind          TEXT NOT NULL,        -- matter_assignment | filing_status | fleet_item | move | ...
    target_table  TEXT,
    target_id     INTEGER,
    matter_id     INTEGER REFERENCES matters(id),
    question      TEXT NOT NULL,
    options       TEXT,                 -- JSON
    proposed      TEXT,
    decision      TEXT,
    decided_by    TEXT,
    decided_at    TEXT,
    state         TEXT NOT NULL DEFAULT 'OPEN'
        CHECK (state IN ('OPEN','RESOLVED','DISMISSED')),
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX idx_approvals_state ON approvals(state);

-- Recorded health/backup runs so reliability is provable after the fact.
CREATE TABLE system_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    kind        TEXT NOT NULL,
    ok          INTEGER NOT NULL,
    detail      TEXT
);
