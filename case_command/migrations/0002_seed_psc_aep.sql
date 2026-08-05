-- PSC/AEP mandatory setup.
--
-- Six SEPARATE matters. They are linked to each other so the relationships are
-- visible, but they are never merged: Case 1 and Case 2 have different records,
-- different postures, and different preclusion consequences.
--
-- The September 3, 2025 PSC Final Order is recorded as a permanent boundary on
-- Case 1. Every PSC/AEP event and issue carries a boundary classification so
-- post-final-order conduct is never silently treated as relitigation.
--
-- The preloaded issues below come from Jacob's specification, not from a source
-- document. They are therefore created with verification_status='MISSING_SOURCE'
-- and protected=1: they cannot be deleted, and they will keep showing as
-- unsourced in the issue matrix until a filing or order is linked to each one.
-- That visible gap is intentional. Inventing a source would be worse than
-- showing the hole.

-- ---------------------------------------------------------------------------
-- matters
-- ---------------------------------------------------------------------------
INSERT INTO matters (slug, title, caption, case_number, forum, forum_type, folder,
                     posture, status, verification_status, boundary_date, boundary_label,
                     created_by, notes)
VALUES
 ('psc-24-0735',
  'PSC Case 24-0735-E-C',
  'Kerr v. Appalachian Power Company',
  '24-0735-E-C',
  'Public Service Commission of West Virginia',
  'AGENCY',
  '01_PSC_AEP',
  'Final order entered September 3, 2025',
  'ACTIVE',
  'UNKNOWN',
  '2025-09-03',
  'PSC Final Order (Case 1 boundary)',
  'seed',
  'Case 1. Issues actually decided here are CASE_1_DECIDED_ISSUE. Conduct after the boundary date belongs to Case 2 and is NOT relitigation.'),

 ('psc-26-0315',
  'PSC Case 26-0315-E-C',
  'Kerr v. Appalachian Power Company (post-final-order conduct)',
  '26-0315-E-C',
  'Public Service Commission of West Virginia',
  'AGENCY',
  '01_PSC_AEP',
  'Active',
  'ACTIVE',
  'UNKNOWN',
  '2025-09-03',
  'PSC Final Order in Case 1 (preclusion boundary)',
  'seed',
  'Case 2. Concerns conduct occurring after the September 3, 2025 final order in Case 1, including the September 29, 2025 termination.'),

 ('wvsca-appeal-24-0735',
  'WVSCA appeal from PSC Case 24-0735-E-C',
  'Kerr v. Public Service Commission of West Virginia',
  NULL,
  'West Virginia Supreme Court of Appeals',
  'APPELLATE_COURT',
  '01_PSC_AEP',
  'Appeal',
  'ACTIVE',
  'UNKNOWN',
  '2025-09-03',
  'Order appealed from',
  'seed',
  'Direct appeal from the Case 1 final order. Separate from the mandamus matter.'),

 ('wvsca-mandamus',
  'WVSCA mandamus matter',
  'State ex rel. Kerr v. Public Service Commission of West Virginia',
  NULL,
  'West Virginia Supreme Court of Appeals',
  'APPELLATE_COURT',
  '01_PSC_AEP',
  'Original jurisdiction',
  'ACTIVE',
  'UNKNOWN',
  NULL,
  NULL,
  'seed',
  'Extraordinary writ. Unreasonable-delay preservation lives here, not in the direct appeal.'),

 ('kanawha-rule-60',
  'Kanawha County Rule 60 matter',
  'Kerr — Rule 60 relief',
  NULL,
  'Circuit Court of Kanawha County, West Virginia',
  'TRIAL_COURT',
  '01_PSC_AEP',
  'Pending',
  'ACTIVE',
  'UNKNOWN',
  NULL,
  NULL,
  'seed',
  'Rule 60 relief from judgment. Separate matter; do not merge with the PSC cases.'),

 ('federal-civil-rights',
  'Related federal civil-rights action',
  'Kerr v. (defendants to be confirmed)',
  NULL,
  'United States District Court',
  'FEDERAL_COURT',
  '01_PSC_AEP',
  'Pending',
  'ACTIVE',
  'UNKNOWN',
  NULL,
  NULL,
  'seed',
  'Related federal civil-rights action. Caption, defendants, and case number require confirmation from a filed document.');

-- Every matter references itself, satisfying the common matter_id column.
UPDATE matters SET matter_id = id WHERE matter_id IS NULL;

-- ---------------------------------------------------------------------------
-- matter links: related, never merged
-- ---------------------------------------------------------------------------
INSERT INTO matter_links (matter_id, related_matter_id, relationship, created_by, notes)
SELECT a.id, b.id, r.rel, 'seed', r.note
FROM (
    SELECT 'psc-24-0735' AS a_slug, 'psc-26-0315'         AS b_slug, 'PRIOR_CASE_SAME_PARTIES' AS rel,
           'Case 1 precedes Case 2. Preclusion is an asserted defense, not an established fact.' AS note
    UNION ALL SELECT 'psc-24-0735', 'wvsca-appeal-24-0735', 'APPEALED_TO',
           'Direct appeal from the Case 1 final order.'
    UNION ALL SELECT 'psc-24-0735', 'wvsca-mandamus', 'RELATED_ORIGINAL_JURISDICTION',
           'Mandamus concerning delay in the PSC proceedings.'
    UNION ALL SELECT 'psc-26-0315', 'wvsca-mandamus', 'RELATED_ORIGINAL_JURISDICTION',
           'Mandamus concerning delay affecting Case 2.'
    UNION ALL SELECT 'psc-24-0735', 'kanawha-rule-60', 'RELATED_COLLATERAL',
           'Rule 60 collateral relief.'
    UNION ALL SELECT 'psc-24-0735', 'federal-civil-rights', 'RELATED_FEDERAL',
           'Related federal civil-rights action.'
    UNION ALL SELECT 'psc-26-0315', 'federal-civil-rights', 'RELATED_FEDERAL',
           'Related federal civil-rights action.'
) AS r
JOIN matters a ON a.slug = r.a_slug
JOIN matters b ON b.slug = r.b_slug;

-- ---------------------------------------------------------------------------
-- the permanent boundary event
-- ---------------------------------------------------------------------------
INSERT INTO events (matter_id, title, event_date, event_type, legal_significance,
                    boundary_classification, approved, status, verification_status,
                    created_by, notes)
SELECT id,
       'PSC Final Order entered in Case 24-0735-E-C',
       '2025-09-03',
       'FINAL_ORDER',
       'Permanent boundary date. Issues decided on or before this date are Case 1 issues. '
       'Conduct after this date is new conduct and is not relitigation.',
       'PROCEDURAL_HISTORY',
       1,
       'ACTIVE',
       'MISSING_SOURCE',
       'seed',
       'Boundary preloaded from specification. Link the entered order document to move this to VERIFIED_PRIMARY.'
FROM matters WHERE slug='psc-24-0735';

INSERT INTO events (matter_id, title, event_date, event_type, legal_significance,
                    boundary_classification, approved, status, verification_status,
                    created_by, notes)
SELECT id,
       'Boundary reference: PSC Final Order in Case 24-0735-E-C',
       '2025-09-03',
       'BOUNDARY_REFERENCE',
       'Preclusion boundary asserted against Case 2. Conduct after this date is new conduct.',
       'PROCEDURAL_HISTORY',
       1,
       'ACTIVE',
       'MISSING_SOURCE',
       'seed',
       'Boundary preloaded from specification.'
FROM matters WHERE slug='psc-26-0315';

-- ---------------------------------------------------------------------------
-- preloaded live PSC/AEP issues
--
-- protected=1 means the issue can never be deleted. Its status may move among
-- ACTIVE / RESERVED / WEAK / MISSING_PROOF / OUTSIDE_CURRENT_HEARING /
-- SUPERSEDED_BY_AUTHORITY / DECIDED, and nothing else.
-- ---------------------------------------------------------------------------
INSERT INTO issues (matter_id, issue_key, title, boundary_classification, hearing_scope,
                    status, verification_status, protected, created_by, notes)
SELECT m.id, s.issue_key, s.title, s.boundary, s.scope, 'ACTIVE', 'MISSING_SOURCE', 1, 'seed',
       'Preloaded from specification. Requires a source document before any part of it is treated as verified.'
FROM (
    SELECT 'PSC-001' AS issue_key,
           'September 29, 2025 termination' AS title,
           'psc-26-0315' AS slug,
           'POST_FINAL_ORDER_NEW_CONDUCT' AS boundary,
           'IN_SCOPE' AS scope
    UNION ALL SELECT 'PSC-002', 'Pretermination written notice', 'psc-26-0315',
        'POST_FINAL_ORDER_NEW_CONDUCT', 'IN_SCOPE'
    UNION ALL SELECT 'PSC-003', 'Personal-contact attempts', 'psc-26-0315',
        'POST_FINAL_ORDER_NEW_CONDUCT', 'IN_SCOPE'
    UNION ALL SELECT 'PSC-004', 'Dispute-meeting rights', 'psc-26-0315',
        'POST_FINAL_ORDER_NEW_CONDUCT', 'IN_SCOPE'
    UNION ALL SELECT 'PSC-005', 'Written-decision rights', 'psc-26-0315',
        'POST_FINAL_ORDER_NEW_CONDUCT', 'IN_SCOPE'
    UNION ALL SELECT 'PSC-006', 'August 7, 2024 site visit', 'psc-26-0315',
        'PRIOR_EVIDENCE_FOR_LIMITED_PURPOSE', 'CONDITIONAL'
    UNION ALL SELECT 'PSC-007', 'APCo chronology omissions', 'psc-26-0315',
        'POST_FINAL_ORDER_NEW_CONDUCT', 'IN_SCOPE'
    UNION ALL SELECT 'PSC-008', 'March 3, 2026 payment gate', 'psc-26-0315',
        'POST_FINAL_ORDER_NEW_CONDUCT', 'IN_SCOPE'
    UNION ALL SELECT 'PSC-009', '$3,130.73 calculation', 'psc-26-0315',
        'POST_FINAL_ORDER_NEW_CONDUCT', 'CONDITIONAL'
    UNION ALL SELECT 'PSC-010', 'Staff reliance on APCo information', 'psc-26-0315',
        'POST_FINAL_ORDER_NEW_CONDUCT', 'IN_SCOPE'
    UNION ALL SELECT 'PSC-011', 'APCo Rule 7.3 answer sufficiency', 'psc-26-0315',
        'POST_FINAL_ORDER_NEW_CONDUCT', 'IN_SCOPE'
    UNION ALL SELECT 'PSC-012', 'Hearing attribution to Complainant', 'psc-26-0315',
        'PROCEDURAL_HISTORY', 'IN_SCOPE'
    UNION ALL SELECT 'PSC-013', 'Three unresolved threshold motions', 'psc-26-0315',
        'PROCEDURAL_HISTORY', 'IN_SCOPE'
    UNION ALL SELECT 'PSC-014', '"Incomprehensible" characterization', 'psc-26-0315',
        'PROCEDURAL_HISTORY', 'IN_SCOPE'
    UNION ALL SELECT 'PSC-015', 'ALJ assignment and reassignment', 'psc-26-0315',
        'PROCEDURAL_HISTORY', 'IN_SCOPE'
    UNION ALL SELECT 'PSC-016', 'Case 1 preclusion defense', 'psc-26-0315',
        'CASE_1_DECIDED_ISSUE', 'IN_SCOPE'
    UNION ALL SELECT 'PSC-017', 'Post-final-order conduct distinction', 'psc-26-0315',
        'POST_FINAL_ORDER_NEW_CONDUCT', 'IN_SCOPE'
    UNION ALL SELECT 'PSC-018', 'TRO dissolution representation', 'wvsca-mandamus',
        'PROCEDURAL_HISTORY', 'CONDITIONAL'
    UNION ALL SELECT 'PSC-019', 'PSC missed represented ruling date', 'wvsca-mandamus',
        'PROCEDURAL_HISTORY', 'IN_SCOPE'
    UNION ALL SELECT 'PSC-020', 'Loss of electric service during appeal perfection period',
        'wvsca-appeal-24-0735', 'POST_FINAL_ORDER_NEW_CONDUCT', 'IN_SCOPE'
    UNION ALL SELECT 'PSC-021', 'Actual prejudice to judicial review', 'wvsca-appeal-24-0735',
        'POST_FINAL_ORDER_NEW_CONDUCT', 'IN_SCOPE'
    UNION ALL SELECT 'PSC-022', 'Exceptions versus delayed finality', 'wvsca-appeal-24-0735',
        'PROCEDURAL_HISTORY', 'IN_SCOPE'
    UNION ALL SELECT 'PSC-023', 'Mandamus and unreasonable-delay preservation', 'wvsca-mandamus',
        'PROCEDURAL_HISTORY', 'IN_SCOPE'
) AS s
JOIN matters m ON m.slug = s.slug;

-- Every preloaded issue gets a preservation record so an ignored ruling or a
-- missed exception surfaces as a warning rather than being forgotten.
INSERT INTO preservation_items (matter_id, issue_id, title, raised, ruling_requested,
                                ruling_issued, ignored, exception_required, exception_filed,
                                status, verification_status, created_by, notes)
SELECT i.matter_id, i.id,
       'Preservation: ' || i.title,
       0, 0, 0, 0, 0, 0,
       'ACTIVE', 'UNKNOWN', 'seed',
       'Created with the preloaded issue. Fill in where raised, date raised, ruling requested, '
       'and ruling obtained from the filings once they are linked.'
FROM issues i
WHERE i.protected = 1;

-- Preloaded issues have no source document yet. Record that as an explicit
-- unknown per issue rather than letting an unsourced issue look complete.
INSERT INTO unknowns (matter_id, issue_id, title, question, why_it_matters, how_to_resolve,
                      status, verification_status, created_by)
SELECT i.matter_id, i.id,
       'No source document linked for ' || i.issue_key,
       'Which filing, order, or exhibit establishes this issue?',
       'An issue without a source cannot be argued as a verified fact and cannot be shown to a tribunal.',
       'Ingest the relevant filing and link it to this issue in the issue matrix.',
       'ACTIVE', 'MISSING_SOURCE', 'seed'
FROM issues i
WHERE i.protected = 1;
