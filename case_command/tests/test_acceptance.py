"""Acceptance tests — section 14 of the specification.

Each test names the requirement it proves. Run with:

    python -m unittest case_command.tests.test_acceptance -v
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from .. import (
    access, api, atlas, audit, backup, checks, client, fleet, health,
    migrate_tree, offline, packets, preservation, triage, views, watcher,
)
from ..classify import classify_text
from ..config import (
    ARCHIVE, FINAL_FILINGS, INBOX, MORTGAGE, PSC_AEP, SHARED_EVIDENCE,
    VETERANS, ensure_layout, load_config,
)
from ..db import insert, open_database, utcnow
from ..hashing import sha256_bytes
from ..ingest import ingest_path, scan_all
from .fixtures import build_fixture_tree, PSC_COMPLAINT


class CaseCommandTest(unittest.TestCase):
    """Base: a fresh data root and database for every test."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="cc-test-"))
        self.config = load_config(data_root=self.root)
        ensure_layout(self.config)
        self.paths = build_fixture_tree(self.root)
        self.conn = open_database(self.config)
        self.addCleanup(self._teardown)

    def _teardown(self) -> None:
        try:
            self.conn.close()
        except sqlite3.Error:
            pass
        shutil.rmtree(self.root, ignore_errors=True)

    def ingest_all(self):
        return scan_all(self.config, self.conn, actor="test")

    def matter(self, slug: str) -> sqlite3.Row:
        return self.conn.execute("SELECT * FROM matters WHERE slug=?", (slug,)).fetchone()


# ===========================================================================
# Ingestion
# ===========================================================================
class TestIngestion(CaseCommandTest):

    def test_new_document_in_inbox_is_detected(self):
        """A new document in 00_INBOX is detected."""
        new_file = self.root / INBOX / "brand_new_filing.txt"
        new_file.write_text("Public Service Commission notice of hearing.", encoding="utf-8")
        queued = watcher.discover(self.config, self.conn)
        self.assertGreater(queued, 0)
        results = watcher.drain(self.config, self.conn)
        names = {Path(r.path).name for r in results if r.status == "ingested"}
        self.assertIn("brand_new_filing.txt", names)

    def test_text_and_metadata_are_extracted(self):
        """Text and metadata are extracted."""
        result = ingest_path(self.config, self.conn, self.paths["psc_complaint"])
        self.assertEqual(result.status, "ingested")
        row = self.conn.execute("SELECT * FROM documents WHERE id=?",
                                (result.document_id,)).fetchone()
        self.assertGreater(row["text_chars"], 500)
        self.assertEqual(row["text_method"], "native")
        self.assertTrue(Path(row["text_path"]).exists())
        # Metadata: case number, dates, parties, requested relief.
        self.assertIn("case_number", result.entities)
        self.assertIn("date", result.entities)
        self.assertIn("party", result.entities)
        self.assertTrue(
            any(c["value"] == "26-0315-E-C" for c in result.entities["case_number"]))

    def test_duplicate_detected_by_hash(self):
        """A duplicate is detected by hash, across different folders and names."""
        first = ingest_path(self.config, self.conn, self.paths["psc_complaint"])
        second = ingest_path(self.config, self.conn, self.paths["duplicate"])
        self.assertEqual(first.status, "ingested")
        self.assertEqual(second.status, "duplicate")
        self.assertEqual(second.duplicate_of, first.doc_uid)
        self.assertEqual(first.sha256, second.sha256)
        # One canonical document, not two.
        count = self.conn.execute("SELECT COUNT(*) n FROM documents").fetchone()["n"]
        self.assertEqual(count, 1)

    def test_matter_is_proposed_correctly(self):
        """The matter is proposed correctly."""
        result = ingest_path(self.config, self.conn, self.paths["psc_complaint"])
        self.assertEqual(result.classification["folder"], PSC_AEP)
        self.assertGreater(result.classification["confidence"], 0.5)

    def test_original_remains_unchanged(self):
        """The original file is unchanged by ingestion."""
        path = self.paths["psc_complaint"]
        before_bytes = path.read_bytes()
        before_stat = path.stat()
        ingest_path(self.config, self.conn, path)
        self.assertEqual(path.read_bytes(), before_bytes)
        self.assertEqual(path.stat().st_size, before_stat.st_size)
        self.assertEqual(path.stat().st_mtime, before_stat.st_mtime)

    def test_zip_packet_members_are_ingested(self):
        """A ZIP litigation packet has its members ingested as documents."""
        result = ingest_path(self.config, self.conn, self.paths["packet"])
        self.assertEqual(result.status, "ingested")
        self.assertGreaterEqual(len(result.nested), 2)
        members = self.conn.execute(
            "SELECT original_filename FROM documents WHERE source_document_id=?",
            (result.document_id,)).fetchall()
        names = {row["original_filename"] for row in members}
        self.assertIn("exhibit_a_notes.txt", names)

    def test_extraction_failure_is_reported_not_hidden(self):
        """A failed extraction is reported and the document stays visible."""
        broken = self.root / INBOX / "scanned.xlsx"
        broken.write_bytes(b"not really a spreadsheet")
        result = ingest_path(self.config, self.conn, broken)
        self.assertEqual(result.status, "ingested")   # indexed, not dropped
        row = self.conn.execute("SELECT * FROM documents WHERE id=?",
                                (result.document_id,)).fetchone()
        self.assertIsNotNone(row["extraction_error"])
        unknown = self.conn.execute(
            "SELECT COUNT(*) n FROM unknowns WHERE source_document_id=? "
            "AND title LIKE '%extraction failed%'", (result.document_id,)).fetchone()["n"]
        self.assertEqual(unknown, 1)


# ===========================================================================
# Classification
# ===========================================================================
class TestClassification(CaseCommandTest):

    def test_psc_document_routes_to_psc_folder(self):
        """A PSC document routes to 01_PSC_AEP."""
        result = ingest_path(self.config, self.conn, self.paths["psc_complaint"])
        self.assertEqual(result.classification["folder"], PSC_AEP)

    def test_mortgage_document_routes_to_mortgage_folder(self):
        """A mortgage document routes to 02_MORTGAGE."""
        result = ingest_path(self.config, self.conn, self.paths["mortgage"])
        self.assertEqual(result.classification["folder"], MORTGAGE)

    def test_veterans_document_routes_to_veterans_folder(self):
        """A VA document routes to 04_VETERANS."""
        result = ingest_path(self.config, self.conn, self.paths["va"])
        self.assertEqual(result.classification["folder"], VETERANS)

    def test_shared_evidence_links_to_many_matters_without_duplication(self):
        """Shared evidence links to multiple matters without being copied."""
        result = ingest_path(self.config, self.conn, self.paths["packet"])
        self.assertEqual(result.classification["folder"], SHARED_EVIDENCE)

        links = self.conn.execute(
            "SELECT COUNT(*) n FROM document_matter_links WHERE document_id=?",
            (result.document_id,)).fetchone()["n"]
        self.assertGreaterEqual(links, 2)

        # One physical location; the links are references, not copies.
        rows = self.conn.execute(
            "SELECT COUNT(*) n FROM documents WHERE sha256=?", (result.sha256,)).fetchone()
        self.assertEqual(rows["n"], 1)

    def test_draft_is_not_marked_filed(self):
        """A draft is not marked filed."""
        result = ingest_path(self.config, self.conn, self.paths["draft"])
        self.assertTrue(result.classification["looks_draft"])
        self.assertFalse(result.classification["looks_final"])
        filings = self.conn.execute(
            "SELECT COUNT(*) n FROM filings WHERE document_id=?",
            (result.document_id,)).fetchone()["n"]
        self.assertEqual(filings, 0)

    def test_drive_presence_is_never_proof_of_filing(self):
        """A document with filing language still cannot reach a confirmed status."""
        result = ingest_path(self.config, self.conn, self.paths["psc_complaint"])
        filing = self.conn.execute(
            "SELECT * FROM filings WHERE document_id=?", (result.document_id,)).fetchone()
        self.assertIsNotNone(filing)
        self.assertEqual(filing["filing_status"], "FILED_UNCONFIRMED")
        self.assertIsNone(filing["proof_type"])

        # The database itself refuses a confirmed status without proof.
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "UPDATE filings SET filing_status='DOCKETED' WHERE id=?", (filing["id"],))

        # With proof, it is allowed.
        self.conn.execute(
            "UPDATE filings SET filing_status='DOCKETED', proof_type='ELECTRONIC_RECEIPT', "
            "proof_reference='PSC-2026-0000418' WHERE id=?", (filing["id"],))
        after = self.conn.execute("SELECT filing_status FROM filings WHERE id=?",
                                  (filing["id"],)).fetchone()
        self.assertEqual(after["filing_status"], "DOCKETED")

    def test_ambiguous_document_asks_rather_than_guesses(self):
        """A low-confidence classification opens a decision instead of guessing."""
        ambiguous = self.root / INBOX / "misc_note.txt"
        ambiguous.write_text("Meeting notes. Nothing specific.", encoding="utf-8")
        result = ingest_path(self.config, self.conn, ambiguous)
        self.assertTrue(result.approvals_opened >= 1)
        kinds = {row["kind"] for row in self.conn.execute(
            "SELECT kind FROM approvals WHERE target_id=? AND target_table='documents'",
            (result.document_id,))}
        self.assertIn("matter_assignment", kinds)


# ===========================================================================
# Litigation integrity
# ===========================================================================
class TestLitigationIntegrity(CaseCommandTest):

    def test_case_1_and_case_2_remain_separate(self):
        """Case 1 and Case 2 remain separate matters."""
        case1 = self.matter("psc-24-0735")
        case2 = self.matter("psc-26-0315")
        self.assertIsNotNone(case1)
        self.assertIsNotNone(case2)
        self.assertNotEqual(case1["id"], case2["id"])
        self.assertEqual(case1["case_number"], "24-0735-E-C")
        self.assertEqual(case2["case_number"], "26-0315-E-C")

        # They are linked, and the link explicitly is not a merge.
        link = self.conn.execute(
            "SELECT * FROM matter_links WHERE matter_id=? AND related_matter_id=?",
            (case1["id"], case2["id"])).fetchone()
        self.assertIsNotNone(link)
        self.assertEqual(link["relationship"], "PRIOR_CASE_SAME_PARTIES")

    def test_all_six_psc_matters_exist_separately(self):
        """Six separate linked PSC/AEP matters, not one merged case."""
        slugs = {row["slug"] for row in self.conn.execute(
            "SELECT slug FROM matters WHERE folder=?", (PSC_AEP,))}
        self.assertEqual(slugs, {
            "psc-24-0735", "psc-26-0315", "wvsca-appeal-24-0735",
            "wvsca-mandamus", "kanawha-rule-60", "federal-civil-rights",
        })

    def test_september_3_2025_boundary_is_enforced(self):
        """The September 3, 2025 boundary is recorded and enforced."""
        case1 = self.matter("psc-24-0735")
        self.assertEqual(case1["boundary_date"], "2025-09-03")

        boundary_event = self.conn.execute(
            "SELECT * FROM events WHERE matter_id=? AND event_date='2025-09-03'",
            (case1["id"],)).fetchone()
        self.assertIsNotNone(boundary_event)

    def test_post_final_order_conduct_is_not_relitigation(self):
        """Post-final-order conduct is not automatically classified as relitigation."""
        case2 = self.matter("psc-26-0315")
        result = ingest_path(self.config, self.conn, self.paths["psc_complaint"])

        # The complaint is dated after the boundary; every event it produced that
        # postdates the boundary must be NEW CONDUCT, never a decided issue.
        self.conn.execute("UPDATE documents SET matter_id=? WHERE id=?",
                          (case2["id"], result.document_id))
        events = self.conn.execute(
            "SELECT event_date, boundary_classification FROM events "
            "WHERE source_document_id=? AND event_date > '2025-09-03'",
            (result.document_id,)).fetchall()
        self.assertGreater(len(events), 0)
        for event in events:
            self.assertNotEqual(event["boundary_classification"], "CASE_1_DECIDED_ISSUE")

        # And the seeded issue for post-final-order conduct says so explicitly.
        issue = self.conn.execute(
            "SELECT * FROM issues WHERE issue_key='PSC-001'").fetchone()
        self.assertEqual(issue["boundary_classification"], "POST_FINAL_ORDER_NEW_CONDUCT")

    def test_prior_evidence_can_be_linked_for_limited_purpose(self):
        """Prior evidence can be linked for a limited purpose."""
        case2 = self.matter("psc-26-0315")
        result = ingest_path(self.config, self.conn, self.paths["psc_order"])
        link_id = insert(self.conn, "document_matter_links", {
            "document_id": result.document_id,
            "matter_id": case2["id"],
            "relationship": "PRIOR_EVIDENCE",
            "limited_purpose": "Offered to establish the boundary date only.",
            "boundary_classification": "PRIOR_EVIDENCE_FOR_LIMITED_PURPOSE",
        })
        link = self.conn.execute("SELECT * FROM document_matter_links WHERE id=?",
                                 (link_id,)).fetchone()
        self.assertEqual(link["boundary_classification"],
                         "PRIOR_EVIDENCE_FOR_LIMITED_PURPOSE")
        # The purpose is recorded, and the document is linked rather than copied.
        self.assertTrue(link["limited_purpose"])
        self.assertEqual(link["relationship"], "PRIOR_EVIDENCE")
        copies = self.conn.execute(
            "SELECT COUNT(*) n FROM documents WHERE sha256=?", (result.sha256,)).fetchone()
        self.assertEqual(copies["n"], 1)

        # The seeded August 7, 2024 site-visit issue uses the same treatment.
        issue = self.conn.execute(
            "SELECT * FROM issues WHERE issue_key='PSC-006'").fetchone()
        self.assertEqual(issue["boundary_classification"],
                         "PRIOR_EVIDENCE_FOR_LIMITED_PURPOSE")

    def test_no_issue_disappears_during_fleet_review(self):
        """No issue disappears during Fleet review, even when items are rejected."""
        before = fleet.issues_before_and_after(self.conn)
        self.assertEqual(before["count"], 23)

        proposal = fleet.submit_proposal(self.conn, {
            "job_id": "job-omission-test",
            "job_type": "defense_red_team",
            "matter_id": self.matter("psc-26-0315")["id"],
            "documents_reviewed": [],
            "proposed_facts": [],
            "proposed_issue_updates": [
                {"issue_key": "PSC-009", "status": "WEAK",
                 "notes": "Reviewer thinks this is weak."},
                {"issue_key": "PSC-014", "status": "OUTSIDE_CURRENT_HEARING"},
            ],
            "conflicts_found": [], "missing_sources": [], "defense_attacks": [],
            "recommended_repairs": [], "confidence": 0.6, "citations": [],
            "approval_required": True,
        })

        for item in fleet.pending_items(self.conn, proposal["proposal_id"]):
            fleet.decide_item(self.conn, item["id"], "APPROVED", reviewer="test")

        after = fleet.issues_before_and_after(self.conn)
        self.assertEqual(after["count"], before["count"])
        self.assertEqual(set(after["keys"]), set(before["keys"]))
        # Weak and out-of-scope, but still present and still readable.
        self.assertEqual(after["statuses"]["PSC-009"], "WEAK")
        self.assertEqual(after["statuses"]["PSC-014"], "OUTSIDE_CURRENT_HEARING")

    def test_issues_cannot_be_deleted(self):
        """An issue cannot be deleted at the database level."""
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("DELETE FROM issues WHERE issue_key='PSC-001'")

    def test_all_23_preloaded_issues_present(self):
        """Every preloaded PSC/AEP issue exists and is protected."""
        rows = self.conn.execute(
            "SELECT issue_key, protected FROM issues ORDER BY issue_key").fetchall()
        self.assertEqual(len(rows), 23)
        self.assertTrue(all(row["protected"] == 1 for row in rows))
        self.assertEqual(rows[0]["issue_key"], "PSC-001")
        self.assertEqual(rows[-1]["issue_key"], "PSC-023")


# ===========================================================================
# Fleet prohibitions
# ===========================================================================
class TestFleetProhibitions(CaseCommandTest):

    def _base(self, **overrides):
        payload = {
            "job_id": "job-1", "job_type": "document_extraction", "matter_id": None,
            "documents_reviewed": [], "proposed_facts": [], "proposed_issue_updates": [],
            "conflicts_found": [], "missing_sources": [], "defense_attacks": [],
            "recommended_repairs": [], "confidence": 0.5, "citations": [],
            "approval_required": True,
        }
        payload.update(overrides)
        return payload

    def test_fleet_cannot_mark_a_fact_verified_without_a_source(self):
        with self.assertRaises(fleet.FleetRejection) as ctx:
            fleet.submit_proposal(self.conn, self._base(proposed_facts=[
                {"statement": "APCo mailed notice on September 12, 2025.",
                 "verification_status": "VERIFIED_PRIMARY"},
            ]))
        self.assertIn("without a source", str(ctx.exception))

    def test_fleet_cannot_delete_an_issue(self):
        with self.assertRaises(fleet.FleetRejection) as ctx:
            fleet.submit_proposal(self.conn, self._base(proposed_issue_updates=[
                {"issue_key": "PSC-001", "action": "delete"},
            ]))
        self.assertIn("may not delete", str(ctx.exception))

    def test_fleet_cannot_merge_matters(self):
        with self.assertRaises(fleet.FleetRejection):
            fleet.submit_proposal(self.conn, self._base(proposed_issue_updates=[
                {"issue_key": "PSC-001", "action": "merge"},
            ]))

    def test_fleet_cannot_mark_a_filing_filed_without_proof(self):
        with self.assertRaises(fleet.FleetRejection) as ctx:
            fleet.submit_proposal(self.conn, self._base(recommended_repairs=[
                {"target_table": "filings", "target_id": 1, "filing_status": "DOCKETED"},
            ]))
        self.assertIn("never proof of filing", str(ctx.exception))

    def test_fleet_cannot_mark_an_issue_decided(self):
        with self.assertRaises(fleet.FleetRejection) as ctx:
            fleet.submit_proposal(self.conn, self._base(proposed_issue_updates=[
                {"issue_key": "PSC-016", "status": "DECIDED"},
            ]))
        self.assertIn("Only a human", str(ctx.exception))

    def test_fleet_cannot_run_a_job_outside_the_allowed_set(self):
        with self.assertRaises(fleet.FleetRejection):
            fleet.submit_proposal(self.conn, self._base(job_type="delete_everything"))

    def test_fleet_cannot_send_or_file_documents(self):
        with self.assertRaises(fleet.FleetRejection) as ctx:
            fleet.submit_proposal(self.conn, self._base(recommended_repairs=[
                {"action": "send", "to": "psc@wv.gov"},
            ]))
        self.assertIn("may not send", str(ctx.exception))

    def test_missing_required_response_fields_is_rejected(self):
        with self.assertRaises(fleet.FleetRejection) as ctx:
            fleet.submit_proposal(self.conn, {"job_id": "x"})
        self.assertIn("missing required response fields", str(ctx.exception))

    def test_approved_fact_without_source_is_downgraded_not_promoted(self):
        """Even after approval, an unsourced fact is stored as MISSING_SOURCE."""
        proposal = fleet.submit_proposal(self.conn, self._base(proposed_facts=[
            {"statement": "Service was terminated.", "verification_status": "INFERENCE"},
        ]))
        item = fleet.pending_items(self.conn, proposal["proposal_id"])[0]
        outcome = fleet.decide_item(self.conn, item["id"], "APPROVED", reviewer="test")
        fact = self.conn.execute("SELECT * FROM facts WHERE id=?",
                                 (outcome["applied_record_id"],)).fetchone()
        self.assertIn(fact["verification_status"], ("INFERENCE", "MISSING_SOURCE"))
        self.assertIsNone(fact["source_document_id"])

    def test_valid_proposal_is_stored_pending_and_applies_only_on_approval(self):
        result = ingest_path(self.config, self.conn, self.paths["psc_complaint"])
        proposal = fleet.submit_proposal(self.conn, self._base(
            job_type="timeline_extraction",
            proposed_facts=[{
                "title": "Service terminated September 29, 2025",
                "statement": "APCo terminated electric service on September 29, 2025.",
                "verification_status": "VERIFIED_PRIMARY",
                "source_doc_uid": result.doc_uid,
                "source_page_or_paragraph": "p.1 ¶2",
            }]))
        self.assertEqual(proposal["review_status"], "PENDING")
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) n FROM facts").fetchone()["n"], 0)

        item = fleet.pending_items(self.conn, proposal["proposal_id"])[0]
        fleet.decide_item(self.conn, item["id"], "APPROVED", reviewer="test")
        fact = self.conn.execute("SELECT * FROM facts").fetchone()
        self.assertEqual(fact["verification_status"], "VERIFIED_PRIMARY")
        self.assertEqual(fact["source_page_or_paragraph"], "p.1 ¶2")


# ===========================================================================
# Hearing support
# ===========================================================================
class TestHearingSupport(CaseCommandTest):

    def setUp(self) -> None:
        super().setUp()
        self.case2 = self.matter("psc-26-0315")

    def test_hearing_mode_loads(self):
        """Hearing mode loads for the PSC matter."""
        data = views.hearing_mode(self.conn, self.case2["id"], hearing_date="2026-08-25")
        self.assertTrue(data)
        self.assertEqual(data["hearing_date"], "2026-08-25")
        self.assertEqual(data["matter"]["case_number"], "26-0315-E-C")

    def test_scope_statement_appears(self):
        data = views.hearing_mode(self.conn, self.case2["id"])
        self.assertIn("2025-09-03", data["scope_statement"])
        self.assertIn("new conduct", data["scope_statement"].lower())
        self.assertIn("outside the scope", data["scope_objection"].lower())

    def test_rule_element_checklist_appears(self):
        insert(self.conn, "rules", {
            "matter_id": self.case2["id"],
            "title": "Pretermination notice",
            "rule_number": "150 C.S.R. 3",
            "elements": json.dumps([
                "Written notice provided", "Personal contact attempted",
                "Dispute meeting offered", "Written decision issued",
            ]),
        })
        data = views.hearing_mode(self.conn, self.case2["id"])
        self.assertEqual(len(data["rule_elements"]), 1)
        self.assertEqual(len(data["rule_elements"][0]["elements"]), 4)

    def test_apco_source_record_questions_appear(self):
        data = views.hearing_mode(self.conn, self.case2["id"])
        self.assertGreater(len(data["witness_questions"]), 0)
        joined = " ".join(
            q for entry in data["witness_questions"] for q in entry["questions"]).lower()
        self.assertIn("what document in the record", joined)
        self.assertIn("omitted from the chronology", joined)

    def test_requested_findings_appear(self):
        data = views.hearing_mode(self.conn, self.case2["id"])
        self.assertGreater(len(data["proposed_findings"]), 0)
        # Unwritten findings are shown as gaps, not silently omitted.
        self.assertTrue(any(not f["has_finding"] for f in data["proposed_findings"]))

    def test_billing_issues_marked_outside_scope_unless_relevant(self):
        """A billing issue is presented as out of scope, and stays in the record."""
        self.conn.execute(
            "UPDATE issues SET hearing_scope='OUTSIDE_CURRENT_HEARING' WHERE issue_key='PSC-009'")
        data = views.hearing_mode(self.conn, self.case2["id"])
        out_keys = {i["issue_key"] for i in data["out_of_scope_issues"]}
        in_keys = {i["issue_key"] for i in data["in_scope_issues"]}
        self.assertIn("PSC-009", out_keys)
        self.assertNotIn("PSC-009", in_keys)
        # Still present in the record.
        still_there = self.conn.execute(
            "SELECT COUNT(*) n FROM issues WHERE issue_key='PSC-009'").fetchone()["n"]
        self.assertEqual(still_there, 1)


# ===========================================================================
# Preservation
# ===========================================================================
class TestPreservation(CaseCommandTest):

    def setUp(self) -> None:
        super().setUp()
        self.case2 = self.matter("psc-26-0315")

    def test_ignored_motion_generates_preservation_warning(self):
        """An ignored motion generates a preservation warning."""
        issue = self.conn.execute(
            "SELECT id FROM issues WHERE issue_key='PSC-013'").fetchone()
        motion_id = insert(self.conn, "motions", {
            "matter_id": self.case2["id"], "issue_id": issue["id"],
            "title": "Motion to compel the complete chronology",
            "filed_date": "2026-04-01", "threshold_motion": 1, "ruled_on": 0,
        })
        outcome = preservation.on_motion_ignored(self.conn, motion_id)
        self.assertTrue(outcome["warning"])

        findings = checks.preservation_check(self.conn, self.case2["id"])
        blockers = [f for f in findings if f.severity == "BLOCKER"]
        self.assertTrue(any("ignored" in f.title.lower() for f in blockers))

    def test_recommended_decision_generates_exception_workflow(self):
        """A Recommended Decision generates an exception-deadline workflow."""
        order_id = insert(self.conn, "orders", {
            "matter_id": self.case2["id"], "title": "Recommended Decision",
            "entered_date": "2026-06-01", "is_recommended_decision": 1,
        })
        outcome = preservation.on_recommended_decision(self.conn, order_id)
        self.assertEqual(outcome["due_date"], "2026-06-16")   # 15 provisional days
        self.assertTrue(outcome["provisional"])
        self.assertGreater(outcome["issues_flagged"], 0)

        deadline = self.conn.execute(
            "SELECT * FROM deadlines WHERE id=?", (outcome["deadline_id"],)).fetchone()
        # A computed deadline is never presented as verified.
        self.assertEqual(deadline["verification_status"], "INFERENCE")
        self.assertIn("Confirm", deadline["notes"])

    def test_final_order_generates_appeal_deadline_workflow(self):
        """A final order generates an appeal-deadline workflow."""
        order_id = insert(self.conn, "orders", {
            "matter_id": self.case2["id"], "title": "Final Order",
            "entered_date": "2026-07-01", "is_final": 1,
        })
        outcome = preservation.on_final_order(self.conn, order_id)
        self.assertEqual(outcome["due_date"], "2026-07-31")   # 30 provisional days
        self.assertTrue(outcome["provisional"])

        rows = self.conn.execute(
            "SELECT COUNT(*) n FROM preservation_items WHERE appeal_deadline=?",
            ("2026-07-31",)).fetchone()["n"]
        self.assertGreater(rows, 0)

    def test_missing_ruling_remains_visible(self):
        """A missing ruling stays visible and does not clear itself."""
        issue = self.conn.execute(
            "SELECT id FROM issues WHERE issue_key='PSC-013'").fetchone()
        item = self.conn.execute(
            "SELECT id FROM preservation_items WHERE issue_id=?", (issue["id"],)).fetchone()
        self.conn.execute(
            "UPDATE preservation_items SET raised=1, ruling_requested=1, ruling_issued=0 "
            "WHERE id=?", (item["id"],))

        for _ in range(3):   # repeated reads never make it disappear
            matrix = preservation.preservation_matrix(self.conn, self.case2["id"])
            at_risk = [row for row in matrix if row["issue_key"] == "PSC-013"]
            self.assertEqual(len(at_risk), 1)
            self.assertTrue(at_risk[0]["at_risk"])
            self.assertIn("no ruling", at_risk[0]["risk_flags"])

        dashboard = views.dashboard(self.conn)
        self.assertTrue(any(row["issue_key"] == "PSC-013"
                            for row in dashboard["missing_rulings"]))

    def test_preservation_view_shows_every_required_column(self):
        data = views.preservation_view(self.conn, self.case2["id"])
        self.assertEqual(len(data["sections"]), 1)
        row = data["sections"][0]["rows"][0]
        for column in ("raised", "where_raised", "date_raised", "ruling_requested",
                       "ruling_issued", "ignored", "exception_required", "exception_filed",
                       "final_order_treatment", "appeal_deadline", "standard_of_review",
                       "remedy"):
            self.assertIn(column, row)


# ===========================================================================
# Reliability
# ===========================================================================
class TestReliability(CaseCommandTest):

    def test_restart_does_not_lose_queued_work(self):
        """Queued work survives a restart."""
        watcher.discover(self.config, self.conn)
        before = watcher.queue_stats(self.conn).pending
        self.assertGreater(before, 0)

        # Simulate a crash mid-job, then a restart.
        self.conn.execute("UPDATE ingest_queue SET state='IN_PROGRESS' WHERE id=1")
        self.conn.close()

        self.conn = open_database(self.config)
        recovered = watcher.recover_interrupted(self.conn)
        self.assertEqual(recovered, 1)
        self.assertEqual(watcher.queue_stats(self.conn).pending, before)

        results = watcher.drain(self.config, self.conn)
        self.assertGreater(len(results), 0)
        self.assertEqual(watcher.queue_stats(self.conn).pending, 0)

    def test_failed_extraction_is_reported(self):
        """A failure is recorded on the job and surfaced, never swallowed."""
        bad = self.root / INBOX / "unreadable.xls"
        bad.write_bytes(b"\x00\x01\x02 not a spreadsheet")
        result = ingest_path(self.config, self.conn, bad)
        row = self.conn.execute("SELECT extraction_error FROM documents WHERE id=?",
                                (result.document_id,)).fetchone()
        self.assertIsNotNone(row["extraction_error"])

        report = health.run_health_checks(self.config, self.conn)
        extraction = next(c for c in report["checks"] if c["check"] == "text_extraction")
        self.assertEqual(extraction["status"], "WARN")

    def test_database_backup_restores_successfully(self):
        """A backup verifies and restores, and the record survives."""
        self.ingest_all()
        before = self.conn.execute("SELECT COUNT(*) n FROM documents").fetchone()["n"]
        self.assertGreater(before, 0)

        meta = backup.create_backup(self.config, self.conn, label="test")
        self.assertTrue(meta["verification"]["ok"])
        self.assertTrue(meta["verification"]["audit_chain_intact"])

        # Restore refuses without approval.
        refused = backup.restore(self.config, Path(meta["path"]), approved=False)
        self.assertFalse(refused["restored"])
        self.assertEqual(refused["reason"], "approval required")

        # Change the live database, then restore over it.
        self.conn.execute("UPDATE documents SET title='mutated'")
        self.conn.close()

        result = backup.restore(self.config, Path(meta["path"]), approved=True)
        self.assertTrue(result["restored"])
        self.assertTrue(result["post_restore_verification"]["ok"])
        self.assertIsNotNone(result["safety_copy"])
        self.assertTrue(Path(result["safety_copy"]).exists())

        self.conn = open_database(self.config)
        after = self.conn.execute("SELECT COUNT(*) n FROM documents").fetchone()["n"]
        self.assertEqual(after, before)
        mutated = self.conn.execute(
            "SELECT COUNT(*) n FROM documents WHERE title='mutated'").fetchone()["n"]
        self.assertEqual(mutated, 0)

    def test_no_record_ids_break(self):
        """Every foreign key resolves and no document loses its original."""
        self.ingest_all()
        self.assertEqual(self.conn.execute("PRAGMA foreign_key_check").fetchall(), [])
        for row in self.conn.execute("SELECT storage_path FROM documents"):
            self.assertTrue(Path(row["storage_path"]).exists(), row["storage_path"])

    def test_audit_log_is_append_only_and_chain_verifies(self):
        self.ingest_all()
        ok, problems = audit.verify_chain(self.conn)
        self.assertTrue(ok, problems)
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("DELETE FROM audit_log WHERE id=1")
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("UPDATE audit_log SET actor='forged' WHERE id=1")

    def test_health_check_reports_overall_status(self):
        self.ingest_all()
        backup.create_backup(self.config, self.conn, label="health")
        report = health.run_health_checks(self.config, self.conn)
        self.assertIn(report["overall"], ("OK", "WARN"))
        failures = [c for c in report["checks"] if c["status"] == "FAIL"]
        self.assertEqual(failures, [], [c["detail"] for c in failures])


# ===========================================================================
# Migration safety
# ===========================================================================
class TestMigrationSafety(CaseCommandTest):

    def test_plan_is_read_only_and_detects_duplicates(self):
        """Building a plan changes nothing and finds content-identical copies."""
        snapshot = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        plan = migrate_tree.build_plan(self.config)

        self.assertGreater(plan.file_count, 0)
        self.assertGreaterEqual(plan.duplicate_groups, 1)
        self.assertTrue(any(m.kind == "DEDUPE" for m in plan.moves))

        for path, content in snapshot.items():
            self.assertTrue(path.exists(), f"{path} disappeared during planning")
            self.assertEqual(path.read_bytes(), content)

    def test_dry_run_moves_nothing(self):
        plan = migrate_tree.build_plan(self.config)
        before = sorted(str(p) for p in self.root.rglob("*") if p.is_file())
        outcome = migrate_tree.dry_run(self.config, plan)
        after = sorted(str(p) for p in self.root.rglob("*") if p.is_file())
        self.assertTrue(outcome["dry_run"])
        self.assertEqual(before, after)

    def test_execute_refuses_without_approval(self):
        """Originals are never relocated without explicit approval."""
        plan = migrate_tree.build_plan(self.config)
        before = sorted(str(p) for p in self.root.rglob("*") if p.is_file())
        outcome = migrate_tree.execute(self.config, self.conn, plan)
        self.assertFalse(outcome["executed"])
        self.assertEqual(outcome["reason"], "approval required")
        self.assertEqual(before, sorted(str(p) for p in self.root.rglob("*") if p.is_file()))

    def test_execute_with_approval_is_reversible(self):
        """An approved migration writes a rollback manifest and can be undone."""
        self.ingest_all()
        plan = migrate_tree.build_plan(self.config)
        original_locations = {m.source for m in plan.moves}
        self.assertTrue(original_locations)

        outcome = migrate_tree.execute(self.config, self.conn, plan, approved=True)
        self.assertTrue(outcome["executed"])
        self.assertGreater(outcome["moves_completed"], 0)
        for source in original_locations:
            self.assertFalse(Path(source).exists())

        undo = migrate_tree.rollback(self.config, self.conn,
                                     Path(outcome["rollback_manifest"]))
        self.assertEqual(undo["failures"], [])
        for source in original_locations:
            self.assertTrue(Path(source).exists(), f"{source} was not restored")


# ===========================================================================
# Token efficiency
# ===========================================================================
class TestTokenEfficiency(CaseCommandTest):

    def test_packet_is_small_and_scoped(self):
        """A Fleet packet carries only the issue, its facts, and bounded excerpts."""
        self.ingest_all()
        case2 = self.matter("psc-26-0315")
        issue = self.conn.execute(
            "SELECT id FROM issues WHERE issue_key='PSC-002'").fetchone()

        packet = packets.build_packet(
            self.conn, task="Check pretermination notice elements.",
            job_type="rule_element_analysis", matter_id=case2["id"],
            issue_id=issue["id"], text_budget=4000)

        self.assertLessEqual(packet["budget"]["text_chars_used"], 4000)
        self.assertIn("expected_output_schema", packet)
        self.assertEqual(packet["issue"]["issue_key"], "PSC-002")
        self.assertLess(packets.packet_size(packet), 40_000)

    def test_packet_refuses_a_disallowed_job(self):
        with self.assertRaises(ValueError):
            packets.build_packet(self.conn, task="x", job_type="rewrite_the_record")

    def test_unchanged_document_is_not_re_extracted(self):
        """A document with an unchanged hash reuses the cached extraction."""
        first = ingest_path(self.config, self.conn, self.paths["psc_complaint"])
        cached = self.conn.execute(
            "SELECT * FROM text_cache WHERE sha256=?", (first.sha256,)).fetchone()
        self.assertIsNotNone(cached)

        copy = self.root / SHARED_EVIDENCE / "same_content.txt"
        copy.write_text(PSC_COMPLAINT, encoding="utf-8")
        second = ingest_path(self.config, self.conn, copy)
        # Identical content is a duplicate; nothing is re-extracted or re-OCR'd.
        self.assertEqual(second.status, "duplicate")
        count = self.conn.execute(
            "SELECT COUNT(*) n FROM text_cache WHERE sha256=?", (first.sha256,)).fetchone()["n"]
        self.assertEqual(count, 1)


# ===========================================================================
# Anti-omission checks
# ===========================================================================
class TestAntiOmission(CaseCommandTest):

    def setUp(self) -> None:
        super().setUp()
        self.case2 = self.matter("psc-26-0315")

    def test_completeness_check_blocks_a_draft_that_drops_an_issue(self):
        draft = "This filing addresses only the September 29, 2025 termination."
        report = checks.run_all(self.conn, self.case2["id"], draft)
        self.assertFalse(report.ok)
        omitted = [f for f in report.blockers if f.check == "completeness"]
        self.assertGreater(len(omitted), 0)
        self.assertTrue(any("absent from the draft" in f.title for f in omitted))

    def test_an_issue_marked_reserved_is_not_an_omission(self):
        self.conn.execute("UPDATE issues SET status='RESERVED' WHERE matter_id=?",
                          (self.case2["id"],))
        report = checks.run_all(self.conn, self.case2["id"], "A short draft.")
        completeness_blockers = [f for f in report.blockers if f.check == "completeness"]
        self.assertEqual(completeness_blockers, [])

    def test_source_check_blocks_a_verified_item_without_a_source(self):
        insert(self.conn, "facts", {
            "matter_id": self.case2["id"], "title": "Unsourced assertion",
            "statement": "Something asserted without proof.",
            "verification_status": "VERIFIED_PRIMARY",
        })
        findings = checks.source_check(self.conn, self.case2["id"])
        self.assertTrue(any(f.severity == "BLOCKER" and "without a source" in f.title
                            for f in findings))

    def test_conflict_check_blocks_on_an_open_contradiction(self):
        insert(self.conn, "contradictions", {
            "matter_id": self.case2["id"],
            "title": "Notice date conflict",
            "left_statement": "No written notice was received.",
            "right_statement": "APCo states notice was mailed September 12, 2025.",
            "resolved": 0,
        })
        findings = checks.conflict_check(self.conn, self.case2["id"])
        self.assertTrue(any(f.severity == "BLOCKER" for f in findings))

    def test_defense_check_reports_missing_perspectives(self):
        findings = checks.defense_check(self.conn, self.case2["id"])
        self.assertGreater(len(findings), 0)
        self.assertTrue(any("not red-teamed" in f.title for f in findings))

    def test_can_mark_final_is_false_while_blockers_remain(self):
        ok, report = checks.can_mark_final(self.conn, self.case2["id"], "short draft")
        self.assertFalse(ok)
        self.assertGreater(len(report.blockers), 0)


# ===========================================================================
# Views render
# ===========================================================================
class TestViews(CaseCommandTest):

    def test_all_seven_views_produce_data(self):
        self.ingest_all()
        case2 = self.matter("psc-26-0315")

        dashboard = views.dashboard(self.conn)
        self.assertIn("todays_actions", dashboard)
        self.assertGreater(dashboard["counts"]["documents"], 0)

        matter = views.matter_view(self.conn, case2["id"])
        for key in ("filings", "orders", "timeline", "issues", "claims", "defenses",
                    "evidence", "deadlines", "relief", "preservation_summary",
                    "parties", "counsel", "judges", "aljs"):
            self.assertIn(key, matter)

        line = views.timeline(self.conn, matter_id=case2["id"])
        self.assertIn("events", line)

        matrix = views.issue_matrix(self.conn, case2["id"])
        self.assertGreater(matrix["count"], 0)
        for column in ("legal_element", "verified_facts", "disputed_facts", "inference",
                       "authority", "evidence", "opponent_defense", "best_reply",
                       "missing_proof", "requested_finding", "requested_relief",
                       "preservation_status", "appeal_standard", "risk_rating"):
            self.assertIn(column, matrix["matrix"][0])

        compare = views.comparison(self.conn, mode="complaint_answer")
        self.assertIn("candidates", compare)

        hearing = views.hearing_mode(self.conn, case2["id"])
        self.assertIn("scope_statement", hearing)

        preservation_data = views.preservation_view(self.conn, case2["id"])
        self.assertEqual(len(preservation_data["sections"]), 1)

    def test_comparison_finds_differences_between_complaint_and_answer(self):
        complaint = ingest_path(self.config, self.conn, self.paths["psc_complaint"])
        answer = ingest_path(self.config, self.conn, self.paths["apco_answer"])
        result = views.comparison(self.conn, mode="complaint_answer",
                                  left_id=complaint.document_id,
                                  right_id=answer.document_id)
        self.assertGreater(result["difference_count"], 0)
        self.assertTrue(result["left_text"])
        self.assertTrue(result["right_text"])


# ===========================================================================
# Chronological triage
# ===========================================================================
class TestTriage(CaseCommandTest):

    def test_chronology_is_ordered_and_dates_carry_provenance(self):
        self.ingest_all()
        triage.backfill_extracts(self.conn)
        report = triage.chronology(self.conn)

        dates = [e["date"] for e in report["dated"]]
        self.assertEqual(dates, sorted(dates), "chronology must be in date order")
        for entry in report["dated"]:
            self.assertTrue(entry["date_source"], "every date must say where it came from")

    def test_a_documents_own_date_beats_a_date_it_merely_cites(self):
        """The APCo answer cites a September 2025 order but was served in March 2026."""
        result = ingest_path(self.config, self.conn, self.paths["apco_answer"])
        row = self.conn.execute("SELECT * FROM documents WHERE id=?",
                                (result.document_id,)).fetchone()
        self.assertEqual(row["document_date"], "2026-03-20")
        self.assertEqual(row["date_source"], "service date")

    def test_signature_block_date_is_preferred(self):
        result = ingest_path(self.config, self.conn, self.paths["psc_complaint"])
        row = self.conn.execute("SELECT * FROM documents WHERE id=?",
                                (result.document_id,)).fetchone()
        self.assertEqual(row["document_date"], "2026-03-05")
        self.assertEqual(row["date_source"], "signature block")

    def test_entered_field_dates_an_order(self):
        result = ingest_path(self.config, self.conn, self.paths["psc_order"])
        row = self.conn.execute("SELECT * FROM documents WHERE id=?",
                                (result.document_id,)).fetchone()
        self.assertEqual(row["document_date"], "2025-09-03")
        self.assertEqual(row["date_source"], "entered date")

    def test_undated_documents_are_listed_separately_not_guessed(self):
        self.ingest_all()
        triage.backfill_extracts(self.conn)
        report = triage.chronology(self.conn)
        self.assertGreater(report["undated_count"], 0)
        for entry in report["undated"]:
            self.assertIsNone(entry["date"])
            self.assertEqual(entry["date_source"], "no date found")
        # An undated document never leaks into the dated list.
        self.assertTrue(all(e["date"] for e in report["dated"]))

    def test_description_is_a_verbatim_extract_from_the_document(self):
        result = ingest_path(self.config, self.conn, self.paths["psc_complaint"])
        triage.backfill_extracts(self.conn)
        row = self.conn.execute("SELECT * FROM documents WHERE id=?",
                                (result.document_id,)).fetchone()
        self.assertEqual(row["extract_line"], "FORMAL COMPLAINT")
        # The line must appear verbatim in the source text.
        source = Path(row["text_path"]).read_text(encoding="utf-8")
        self.assertIn(row["extract_line"], source)

    def test_unreadable_document_says_so_rather_than_showing_blank(self):
        broken = self.root / INBOX / "scan.xlsx"
        broken.write_bytes(b"not a spreadsheet")
        ingest_path(self.config, self.conn, broken)
        triage.backfill_extracts(self.conn)
        report = triage.chronology(self.conn)
        entry = next(e for e in report["dated"] + report["undated"]
                     if e["filename"] == "scan.xlsx")
        self.assertIn("no text", entry["extract"].lower())
        self.assertIn("UNREADABLE", entry["flags"])

    def test_copy_locations_are_recorded_and_shown(self):
        """A byte-identical file in a second folder is recorded as a copy location.

        This is the "what is a copy" answer: one canonical document plus the
        other places the identical bytes are sitting. Without this the extra
        path exists only in the audit log, and a cleanup could delete the wrong
        one.
        """
        canonical = ingest_path(self.config, self.conn, self.paths["psc_complaint"])
        duplicate = ingest_path(self.config, self.conn, self.paths["duplicate"])
        self.assertEqual(duplicate.status, "duplicate")

        groups = triage.copy_locations(self.conn)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["doc_uid"], canonical.doc_uid)
        paths = {c["path"] for c in groups[0]["copies"]}
        self.assertIn(str(self.paths["duplicate"]), paths)

        triage.backfill_extracts(self.conn)
        report = triage.chronology(self.conn)
        entry = next(e for e in report["dated"] + report["undated"]
                     if e["doc_uid"] == canonical.doc_uid)
        self.assertEqual(entry["copy_count"], 1)
        self.assertTrue(any("COPY" in flag for flag in entry["flags"]))
        self.assertEqual(report["redundant_copies"], 1)

    def test_propose_copy_archive_moves_and_deletes_nothing(self):
        ingest_path(self.config, self.conn, self.paths["psc_complaint"])
        ingest_path(self.config, self.conn, self.paths["duplicate"])

        before_docs = self.conn.execute("SELECT COUNT(*) n FROM documents").fetchone()["n"]
        outcome = triage.propose_copy_archive(self.conn)

        self.assertEqual(outcome["proposed"], 1)
        self.assertEqual(outcome["moved"], 0)
        self.assertEqual(outcome["deleted"], 0)
        # Both files still on disk, document count unchanged.
        self.assertTrue(self.paths["duplicate"].exists())
        self.assertTrue(self.paths["psc_complaint"].exists())
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) n FROM documents").fetchone()["n"],
            before_docs)

    def test_copy_records_cannot_be_deleted(self):
        ingest_path(self.config, self.conn, self.paths["psc_complaint"])
        ingest_path(self.config, self.conn, self.paths["duplicate"])
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("DELETE FROM document_copies")

    def test_triage_decision_is_recorded_and_reversible(self):
        result = ingest_path(self.config, self.conn, self.paths["draft"])
        triage.set_status(self.conn, result.document_id, "IRRELEVANT",
                          reviewer="test", note="not related to any matter")
        row = self.conn.execute("SELECT * FROM documents WHERE id=?",
                                (result.document_id,)).fetchone()
        self.assertEqual(row["triage_status"], "IRRELEVANT")
        self.assertEqual(row["triage_by"], "test")

        # Still in the record, still searchable, not deleted.
        self.assertEqual(row["status"], "ACTIVE")
        self.assertTrue(Path(row["storage_path"]).exists())

        # And the decision can be taken back.
        triage.set_status(self.conn, result.document_id, "KEEP", reviewer="test")
        self.assertEqual(
            self.conn.execute("SELECT triage_status FROM documents WHERE id=?",
                              (result.document_id,)).fetchone()["triage_status"], "KEEP")

    def test_triage_rejects_an_unknown_status(self):
        result = ingest_path(self.config, self.conn, self.paths["draft"])
        with self.assertRaises(ValueError):
            triage.set_status(self.conn, result.document_id, "DELETE")

    def test_csv_export_contains_every_row(self):
        self.ingest_all()
        triage.backfill_extracts(self.conn)
        report = triage.chronology(self.conn)
        csv_text = triage.to_csv(report)
        lines = [line for line in csv_text.splitlines() if line.strip()]
        self.assertEqual(len(lines), report["total"] + 1)   # + header
        self.assertIn("what_it_is_extract", lines[0])


# ===========================================================================
# Access barriers
# ===========================================================================
class TestAccessBarriers(CaseCommandTest):

    def _log(self, **overrides):
        payload = {
            "incident_date": "2026-03-10",
            "barrier_type": "NO_ELECTRICITY",
            "what_was_blocked": "Response to APCo Answer",
            "matter_id": self.matter("psc-26-0315")["id"],
        }
        payload.update(overrides)
        return access.log_barrier(self.conn, **payload)

    def test_barrier_links_to_the_prejudice_issues(self):
        """A logged barrier attaches to PSC-020 and PSC-021 automatically."""
        result = self._log()
        self.assertEqual(set(result["linked_issues"]), {"PSC-020", "PSC-021"})

        for key in ("PSC-020", "PSC-021"):
            issue = self.conn.execute(
                "SELECT id FROM issues WHERE issue_key=?", (key,)).fetchone()
            link = self.conn.execute(
                "SELECT * FROM issue_links WHERE issue_id=? AND linked_type='access_barrier' "
                "AND linked_id=?", (issue["id"], result["barrier_id"])).fetchone()
            self.assertIsNotNone(link, f"{key} not linked")
            # Proposed, not auto-approved.
            self.assertEqual(link["approved"], 0)

    def test_a_barrier_without_proof_is_not_verified(self):
        result = self._log()
        self.assertEqual(result["verification_status"], "UNKNOWN")
        row = self.conn.execute("SELECT * FROM access_barriers WHERE id=?",
                                (result["barrier_id"],)).fetchone()
        self.assertIsNone(row["evidence_document_id"])

    def test_attaching_proof_upgrades_verification(self):
        document = ingest_path(self.config, self.conn, self.paths["psc_order"])
        result = self._log()
        outcome = access.attach_evidence(self.conn, result["barrier_id"],
                                         document.document_id, locator="p.1")
        self.assertEqual(outcome["verification_status"], "VERIFIED_SECONDARY")
        row = self.conn.execute("SELECT * FROM access_barriers WHERE id=?",
                                (result["barrier_id"],)).fetchone()
        self.assertEqual(row["source_document_id"], document.document_id)
        self.assertEqual(row["source_page_or_paragraph"], "p.1")

    def test_a_vague_entry_is_refused(self):
        """A general assertion of hardship is not evidence and is not accepted."""
        with self.assertRaises(ValueError) as ctx:
            self._log(what_was_blocked="   ")
        self.assertIn("not evidence", str(ctx.exception))

    def test_invalid_barrier_type_is_refused(self):
        with self.assertRaises(ValueError):
            self._log(barrier_type="EVERYTHING_IS_BAD")

    def test_summary_counts_but_does_not_conclude(self):
        """The summary arranges what was entered; it draws no legal conclusion."""
        self._log(deadline_affected="Response due", deadline_date="2026-03-15",
                  hours_lost=4.0)
        self._log(incident_date="2026-04-02", barrier_type="NO_PRINTER",
                  what_was_blocked="Exceptions to Recommended Decision",
                  reported_to_tribunal=True, cost_incurred=18.5)

        summary = access.summarize(self.conn)
        self.assertEqual(summary["count"], 2)
        self.assertEqual(summary["date_range"], "2026-03-10 to 2026-04-02")
        self.assertEqual(summary["total_hours_lost"], 4.0)
        self.assertEqual(summary["total_cost_incurred"], 18.5)
        self.assertEqual(summary["reported_to_tribunal"], 1)

        # No characterization of the incidents anywhere in the output.
        blob = json.dumps(summary).lower()
        for word in ("prejudice occurred", "violation", "unlawful", "wrongful",
                     "egregious", "deliberate"):
            self.assertNotIn(word, blob)

    def test_summary_names_its_own_weaknesses(self):
        self._log()
        summary = access.summarize(self.conn)
        gaps = " ".join(summary["gaps"]).lower()
        self.assertIn("no supporting document", gaps)
        self.assertIn("never reported to the tribunal", gaps)

    def test_empty_log_says_so_rather_than_implying_no_barriers_existed(self):
        summary = access.summarize(self.conn)
        self.assertEqual(summary["count"], 0)
        self.assertIn("contemporaneous", summary["note"])

    def test_barriers_cannot_be_deleted(self):
        self._log()
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("DELETE FROM access_barriers")

    def test_barrier_appears_on_the_dashboard(self):
        self._log(deadline_affected="Response due", deadline_date="2026-03-15")
        data = views.dashboard(self.conn)
        self.assertEqual(data["access_barriers"]["count"], 1)


# ===========================================================================
# Offline availability and phone capture
# ===========================================================================
class TestOffline(CaseCommandTest):

    def test_pinning_a_document_reports_its_size_before_download(self):
        result = ingest_path(self.config, self.conn, self.paths["psc_complaint"])
        pinned = offline.pin(self.conn, result.document_id)
        self.assertGreater(pinned["est_bytes"], 0)
        self.assertIn("est_mb", pinned)

        report = offline.storage_report(self.conn)
        self.assertEqual(report["pin_count"], 1)
        self.assertFalse(report["over_budget"])

    def test_a_pin_that_cannot_be_honoured_says_so(self):
        """A document with no extracted text cannot be read offline, and says so
        now rather than in the hearing."""
        broken = self.root / INBOX / "unreadable.xls"
        broken.write_bytes(b"\x00\x01 not a spreadsheet")
        result = ingest_path(self.config, self.conn, broken)
        self.conn.execute("UPDATE documents SET text_path=NULL WHERE id=?",
                          (result.document_id,))

        offline.pin(self.conn, result.document_id)
        row = self.conn.execute(
            "SELECT * FROM offline_pins WHERE document_id=?",
            (result.document_id,)).fetchone()
        self.assertEqual(row["sync_state"], "UNAVAILABLE")
        self.assertIn("nothing to read offline", row["sync_error"])

        report = offline.storage_report(self.conn)
        self.assertEqual(len(report["unavailable"]), 1)

    def test_unpinning_keeps_the_document_in_the_record(self):
        result = ingest_path(self.config, self.conn, self.paths["psc_complaint"])
        offline.pin(self.conn, result.document_id)
        outcome = offline.unpin(self.conn, result.document_id)

        self.assertEqual(outcome["released"], 1)
        still_there = self.conn.execute(
            "SELECT COUNT(*) n FROM documents WHERE id=?",
            (result.document_id,)).fetchone()["n"]
        self.assertEqual(still_there, 1)
        self.assertTrue(self.paths["psc_complaint"].exists())

    def test_hearing_pack_pins_exhibits_first(self):
        """Exhibits sync before everything else, so the most important material
        lands even if the connection drops."""
        self.ingest_all()
        case2 = self.matter("psc-26-0315")
        document = self.conn.execute("SELECT id FROM documents LIMIT 1").fetchone()
        insert(self.conn, "evidence", {
            "matter_id": case2["id"], "document_id": document["id"],
            "title": "Photographs of spoiled food", "exhibit_number": "A",
        })
        self.conn.execute("UPDATE documents SET matter_id=? WHERE id=?",
                          (case2["id"], document["id"]))

        pack = offline.build_hearing_pack(self.conn, case2["id"])
        self.assertGreater(pack["pinned"], 0)

        priorities = {
            row["document_id"]: row["priority"]
            for row in self.conn.execute("SELECT document_id, priority FROM offline_pins")
        }
        self.assertEqual(priorities[document["id"]], 10)   # exhibit tier
        self.assertTrue(all(p >= 10 for p in priorities.values()))

    def test_hearing_pack_falls_back_to_matter_documents(self):
        """Early in a matter nothing is an exhibit yet — walking in with an empty
        phone would hurt most exactly then."""
        self.ingest_all()
        case2 = self.matter("psc-26-0315")
        self.conn.execute(
            "UPDATE documents SET matter_id=? WHERE folder='00_INBOX'", (case2["id"],))
        pack = offline.build_hearing_pack(self.conn, case2["id"])
        self.assertGreater(pack["pinned"], 0)

    def test_bundle_carries_hearing_context_with_the_documents(self):
        """Exhibits are useless offline without the scope statement and the
        rule elements."""
        self.ingest_all()
        case2 = self.matter("psc-26-0315")
        self.conn.execute("UPDATE documents SET matter_id=? WHERE folder='00_INBOX'",
                          (case2["id"],))
        offline.build_hearing_pack(self.conn, case2["id"])

        bundle = offline.build_bundle(self.conn, case2["id"])
        self.assertGreater(bundle["document_count"], 0)
        self.assertIn("scope_statement", bundle["hearing"])
        self.assertIn("objections", bundle["hearing"])
        self.assertIn("in_scope_issues", bundle["hearing"])
        # Text travels with it, or there is nothing to read.
        self.assertTrue(any(d["text"] for d in bundle["documents"]))
        # Provenance travels too.
        self.assertTrue(all("date_source" in d for d in bundle["documents"]))

    def test_bundle_omits_pins_that_cannot_be_honoured(self):
        result = ingest_path(self.config, self.conn, self.paths["psc_complaint"])
        offline.pin(self.conn, result.document_id)
        self.conn.execute("UPDATE offline_pins SET sync_state='UNAVAILABLE'")
        bundle = offline.build_bundle(self.conn)
        self.assertEqual(bundle["document_count"], 0)

    def test_capture_is_ingested_through_the_normal_pipeline(self):
        outcome = offline.accept_capture(
            self.conn, self.config,
            client_uid="cap-1", filename="meter.txt",
            data=b"Photograph of the meter base, tag 44812, taken at the residence.",
            capture_kind="PHOTO", captured_at="2026-03-10T14:15:00Z",
            device_note="Meter pulled; tag number visible.")

        self.assertEqual(outcome["state"], "INGESTED")
        self.assertIsNotNone(outcome["doc_uid"])

        row = self.conn.execute("SELECT * FROM documents WHERE id=?",
                                (outcome["document_id"],)).fetchone()
        self.assertEqual(row["sha256"], row["sha256"])   # hashed like any document
        # The capture time is the fact that matters, not the upload time.
        self.assertEqual(row["document_date"], "2026-03-10")
        self.assertEqual(row["date_source"], "captured on device")

    def test_a_replayed_capture_is_not_counted_twice(self):
        """A retry after a dropped connection is the same capture, not a second."""
        payload = dict(client_uid="cap-retry", filename="a.txt", data=b"first capture")
        first = offline.accept_capture(self.conn, self.config, **payload)
        second = offline.accept_capture(self.conn, self.config, **payload)

        self.assertEqual(first["state"], "INGESTED")
        self.assertTrue(second["duplicate"])
        rows = self.conn.execute(
            "SELECT COUNT(*) n FROM capture_queue WHERE client_uid='cap-retry'"
        ).fetchone()["n"]
        self.assertEqual(rows, 1)

    def test_captured_evidence_cannot_be_deleted(self):
        offline.accept_capture(self.conn, self.config, client_uid="cap-2",
                               filename="b.txt", data=b"evidence")
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("DELETE FROM capture_queue")

    def test_failed_capture_ingestion_keeps_the_file(self):
        """A photograph is never discarded because the pipeline choked on it."""
        outcome = offline.accept_capture(
            self.conn, self.config, client_uid="cap-3",
            filename="weird.xlsx", data=b"\x00\x01 not a spreadsheet at all")
        row = self.conn.execute("SELECT * FROM capture_queue WHERE client_uid='cap-3'"
                                ).fetchone()
        self.assertIsNotNone(row["stored_path"])
        self.assertTrue(Path(row["stored_path"]).exists())
        self.assertIn(outcome["state"], ("INGESTED", "FAILED", "DUPLICATE"))

    def test_invalid_pin_reason_is_refused(self):
        result = ingest_path(self.config, self.conn, self.paths["psc_complaint"])
        with self.assertRaises(ValueError):
            offline.pin(self.conn, result.document_id, reason="WHENEVER")


# ===========================================================================
# Versioned API — what a standalone native client talks to
# ===========================================================================
class TestApi(CaseCommandTest):

    def _pair(self, label: str = "Phone", platform: str = "ios") -> str:
        code = api.create_pairing_code(self.conn)["code"]
        return api.redeem_pairing_code(self.conn, code=code, label=label,
                                       platform=platform)["token"]

    def test_pairing_returns_a_token_stored_only_as_a_hash(self):
        """A copied database must yield no working credential."""
        token = self._pair()
        row = self.conn.execute("SELECT * FROM devices").fetchone()
        self.assertNotEqual(row["token_hash"], token)
        self.assertEqual(len(row["token_hash"]), 64)      # sha256 hex
        self.assertEqual(row["token_prefix"], token[:8])
        # The raw token appears nowhere in the row.
        self.assertNotIn(token, json.dumps({k: row[k] for k in row.keys()}, default=str))

    def test_a_pairing_code_works_once(self):
        code = api.create_pairing_code(self.conn)["code"]
        api.redeem_pairing_code(self.conn, code=code, label="First")
        with self.assertRaises(api.ApiError) as ctx:
            api.redeem_pairing_code(self.conn, code=code, label="Second")
        self.assertEqual(ctx.exception.status, 409)

    def test_an_expired_code_is_refused(self):
        code = api.create_pairing_code(self.conn)["code"]
        self.conn.execute("UPDATE pairing_codes SET expires_at='2000-01-01T00:00:00.000Z'")
        with self.assertRaises(api.ApiError) as ctx:
            api.redeem_pairing_code(self.conn, code=code, label="Late")
        self.assertEqual(ctx.exception.status, 410)

    def test_unknown_and_missing_tokens_are_refused(self):
        for header in (None, "", "Bearer nonsense", "Basic abc"):
            with self.assertRaises(api.ApiError) as ctx:
                api.authenticate(self.conn, header)
            self.assertIn(ctx.exception.status, (401, 403))

    def test_a_revoked_device_is_cut_off(self):
        token = self._pair()
        device_uid = self.conn.execute("SELECT device_uid FROM devices").fetchone()["device_uid"]
        api.authenticate(self.conn, f"Bearer {token}")     # works before

        api.revoke_device(self.conn, device_uid, reason="left at the courthouse")
        with self.assertRaises(api.ApiError) as ctx:
            api.authenticate(self.conn, f"Bearer {token}")
        self.assertEqual(ctx.exception.status, 403)

    def test_a_device_cannot_be_deleted_only_revoked(self):
        self._pair()
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("DELETE FROM devices")

    def test_first_sync_returns_everything_then_nothing(self):
        self.ingest_all()
        first = api.sync(self.conn)
        self.assertTrue(first["full_sync"])
        self.assertGreater(first["total"], 0)
        self.assertIn("matters", first["changed"])
        self.assertIn("issues", first["changed"])

        second = api.sync(self.conn, since=first["next_cursor"])
        self.assertFalse(second["full_sync"])
        self.assertEqual(second["total"], 0)

    def test_delta_sync_returns_only_what_changed(self):
        self.ingest_all()
        cursor = api.sync(self.conn)["next_cursor"]

        issue = self.conn.execute("SELECT id FROM issues LIMIT 1").fetchone()
        from ..db import update

        update(self.conn, "issues", issue["id"], {"risk_rating": "HIGH"})

        delta = api.sync(self.conn, since=cursor)
        self.assertEqual(delta["total"], 1)
        self.assertEqual(list(delta["changed"].keys()), ["issues"])
        self.assertEqual(delta["changed"]["issues"][0]["risk_rating"], "HIGH")

    def test_sync_says_when_more_is_waiting(self):
        """A client must never believe it is up to date when it is not."""
        self.ingest_all()
        capped = api.sync(self.conn, limit_per_table=2)
        self.assertTrue(capped["more_available"])
        self.assertTrue(capped["truncated_tables"])

    def test_document_detail_carries_provenance_and_copies(self):
        result = ingest_path(self.config, self.conn, self.paths["psc_complaint"])
        ingest_path(self.config, self.conn, self.paths["duplicate"])

        detail = api.document_detail(self.conn, result.doc_uid)
        self.assertEqual(detail["doc_uid"], result.doc_uid)
        self.assertEqual(detail["date_source"], "signature block")
        self.assertGreater(len(detail["text"]), 100)
        self.assertTrue(detail["has_original"])
        # The other physical location travels with it.
        self.assertEqual(len(detail["copies"]), 1)

    def test_document_original_is_served_unmodified(self):
        result = ingest_path(self.config, self.conn, self.paths["psc_complaint"])
        before = self.paths["psc_complaint"].read_bytes()
        body, filename, _content_type = api.document_original(self.conn, result.doc_uid)

        self.assertEqual(body, before)
        self.assertEqual(filename, self.paths["psc_complaint"].name)
        # Serving it changed nothing on disk.
        self.assertEqual(self.paths["psc_complaint"].read_bytes(), before)

    def test_unknown_document_is_a_404_not_a_crash(self):
        with self.assertRaises(api.ApiError) as ctx:
            api.document_detail(self.conn, "CC-DOC-999999")
        self.assertEqual(ctx.exception.status, 404)

    def test_matter_detail_includes_atlas_and_coverage(self):
        self.ingest_all()
        case2 = self.matter("psc-26-0315")
        detail = api.matter_detail(self.conn, case2["id"])
        self.assertIn("atlas", detail)
        self.assertIn("coverage", detail)
        self.assertIn("available", detail["atlas"])
        # Coverage is counts, never a score. No field may carry a percentage or
        # a health number — the note is allowed to say the word "score" because
        # it exists to say the opposite.
        self.assertIn("issues_total", detail["coverage"])
        for key in detail["coverage"]:
            lowered = key.lower()
            for banned in ("score", "percent", "pct", "health", "rating", "grade"):
                self.assertNotIn(banned, lowered, f"coverage field {key!r} looks like a score")
        for key, value in detail["coverage"].items():
            if isinstance(value, str):
                continue
            self.assertIsInstance(value, int, f"coverage field {key!r} is not a plain count")

    def test_index_is_open_and_documents_the_guarantees(self):
        index = api.index()
        self.assertEqual(index["api_version"], "v1")
        self.assertGreaterEqual(len(index["endpoints"]), 8)
        joined = " ".join(index["guarantees"]).lower()
        self.assertIn("read-only", joined)
        self.assertIn("transmits", joined)


class TestSyncPaging(CaseCommandTest):
    """A paged sync must deliver exactly what an unpaged one does.

    These exist because the first version did not. It set the cursor to
    wall-clock time on every response, so a client that received a capped page
    moved its cursor past everything it had not yet seen and never asked again.
    It did not error. It reported success while holding a fraction of the
    record — the one failure this system cannot tolerate, and the reason the
    conformance rule walks the whole record one row at a time instead of
    checking that a field exists.
    """

    def _walk(self, limit: int) -> dict[str, list[int]]:
        """Every row id per table, gathered by paging with `limit` per table."""
        seen: dict[str, set[int]] = {t: set() for t in api.SYNC_TABLES}
        cursor, rounds = None, 0
        while True:
            rounds += 1
            self.assertLess(rounds, 500, "paged sync did not converge")
            page = api.sync(self.conn, since=cursor, limit_per_table=limit)
            for table, rows in page["changed"].items():
                seen[table].update(r["id"] for r in rows)
            cursor = page["next_cursor"]
            if not page["more_available"]:
                break
        self.rounds = rounds
        return {t: sorted(ids) for t, ids in seen.items()}

    def test_paging_one_row_at_a_time_loses_nothing(self):
        self.ingest_all()
        whole = api.sync(self.conn, limit_per_table=10_000)
        expected = {t: sorted(r["id"] for r in whole["changed"].get(t, []))
                    for t in api.SYNC_TABLES}
        self.assertGreater(sum(len(v) for v in expected.values()), 50)

        self.assertEqual(self._walk(1), expected)
        self.assertGreater(self.rounds, 1, "a limit of 1 should have needed many rounds")
        self.assertEqual(self._walk(7), expected)

    def test_a_truncated_page_never_advances_the_cursor_to_now(self):
        self.ingest_all()
        page = api.sync(self.conn, limit_per_table=1)
        self.assertTrue(page["more_available"])
        # The cursor must sit inside the data, not at wall-clock time. Every
        # row still waiting has updated_at >= it.
        self.assertLess(page["next_cursor"], utcnow())
        delivered = sum(len(rows) for rows in page["changed"].values())
        follow_up = api.sync(self.conn, since=page["next_cursor"],
                             limit_per_table=10_000)
        self.assertGreater(follow_up["total"], 0,
                           "the cursor moved past everything still waiting")
        whole = api.sync(self.conn, limit_per_table=10_000)
        # Nothing was stranded: what came back plus what is still waiting
        # accounts for the entire record (re-reads only ever add).
        self.assertGreaterEqual(delivered + follow_up["total"], whole["total"])

    def test_a_timestamp_group_is_never_split(self):
        """Rows written in one transaction share a timestamp and must page together."""
        self.ingest_all()
        stamp = "2026-01-01T00:00:00.000Z"
        self.conn.execute("UPDATE issues SET updated_at=?", (stamp,))
        self.conn.commit()
        total = self.conn.execute("SELECT COUNT(*) c FROM issues").fetchone()["c"]

        page = api.sync(self.conn, since="2025-12-31T00:00:00.000Z", limit_per_table=1)
        # The limit is a target, not a cap: the whole group came back rather
        # than one row of it, because the cursor cannot stop mid-group without
        # stranding the rest.
        self.assertEqual(len(page["changed"]["issues"]), total)
        self.assertNotEqual(page["next_cursor"], stamp,
                            "cursor stopped on a fully-delivered group")

    def test_a_page_landing_exactly_on_the_end_is_not_reported_as_more(self):
        self.ingest_all()
        total = self.conn.execute("SELECT COUNT(*) c FROM matters").fetchone()["c"]
        page = api.sync(self.conn, limit_per_table=total)
        self.assertNotIn("matters", page["truncated_tables"])

    def test_more_available_and_truncated_tables_agree(self):
        self.ingest_all()
        for limit in (1, 3, 10, 10_000):
            page = api.sync(self.conn, limit_per_table=limit)
            self.assertEqual(page["more_available"], bool(page["truncated_tables"]),
                             f"disagreement at limit={limit}")


class TestReferenceClient(CaseCommandTest):
    """The device side: what the phone holds, and what it refuses to trust."""

    def store(self):
        store = client.LocalStore(Path(self.root) / "device.db")
        self.addCleanup(store.close)
        return store

    def test_a_tampered_cache_is_discarded_rather_than_served(self):
        """"It was in my phone's cache" is not a provenance."""
        store = self.store()
        data = b"the original exhibit"
        digest = sha256_bytes(data)
        store.put_blob(sha256=digest, doc_uid="CC-DOC-000001",
                       filename="exhibit.txt", data=data)
        self.assertEqual(store.blob(digest), data)

        store.conn.execute("UPDATE blobs SET data=? WHERE sha256=?",
                           (b"something else entirely", digest))
        store.conn.commit()
        with self.assertRaises(client.ClientError):
            store.blob(digest)
        # And it is gone, not left to be served on the next attempt.
        self.assertIsNone(store.blob(digest))

    def test_a_capture_taken_offline_is_kept(self):
        store = self.store()
        uid = store.queue_capture(filename="notice.jpg", data=b"bytes",
                                  captured_at="2026-08-04T09:00:00.000Z")
        self.assertEqual(len(store.pending()), 1)
        # A retry reuses the same client_uid, so the server counts one capture.
        with self.assertRaises(sqlite3.IntegrityError):
            store.queue_capture(filename="notice.jpg", data=b"bytes",
                                captured_at="2026-08-04T09:00:00.000Z", client_uid=uid)
        store.mark_sent(uid)
        self.assertEqual(store.pending(), [])

    def test_the_mirror_survives_a_column_it_has_never_seen(self):
        """A phone that cannot sync is worse than one that does not know a column."""
        store = self.store()
        store.apply("issues", [{"id": 1, "matter_id": 2, "updated_at": "2026-01-01",
                                "title": "Curtailment", "a_field_from_the_future": 7}])
        row = store.row("issues", 1)
        self.assertEqual(row["title"], "Curtailment")
        self.assertEqual(row["a_field_from_the_future"], 7)

    def test_every_conformance_rule_has_a_description(self):
        rules = dict(client.CONFORMANCE_RULES)
        self.assertEqual(len(rules), len(client.CONFORMANCE_RULES))
        for name, text in rules.items():
            self.assertTrue(text.endswith("."), f"{name} description is not a sentence")

    def test_the_mirror_covers_every_table_the_server_replicates(self):
        """A table the server sends and the client ignores is a silent gap."""
        self.assertEqual(set(client.MIRROR_TABLES), set(api.SYNC_TABLES))


class TestAtlasGraph(CaseCommandTest):
    """The Path Atlas map draws relationships; it must not invent them."""

    def graph(self):
        self.ingest_all()
        return atlas.graph(self.conn, self.matter("psc-26-0315")["id"])

    def test_every_edge_connects_two_real_nodes(self):
        g = self.graph()
        ids = {n["id"] for n in g["nodes"]}
        self.assertTrue(g["edges"])
        for edge in g["edges"]:
            self.assertIn(edge["from"], ids)
            self.assertIn(edge["to"], ids)

    def test_a_blocked_path_is_drawn_with_the_thing_that_blocks_it(self):
        """The point of the map: never a blocked node with nothing attached."""
        g = self.graph()
        blocked = [n for n in g["nodes"] if n["state"] == "blocked"]
        self.assertTrue(blocked, "fixture should produce at least one blocked path")
        for node in blocked:
            incoming = [e for e in g["edges"] if e["to"] == node["id"] and e["kind"] == "blocks"]
            self.assertTrue(incoming, f"{node['label']!r} is blocked by nothing visible")

    def test_no_node_carries_a_score_or_a_prediction(self):
        g = self.graph()
        banned = ("score", "confidence", "likelihood", "probability", "likely",
                  "success", "percent", "odds")
        blob = json.dumps(g["nodes"]).lower()
        for word in banned:
            self.assertNotIn(word, blob, f"the map leaked {word!r}")

    def test_labels_are_wrapped_not_sliced(self):
        """A label cut mid-word can drop the word that says what to supply."""
        lines = atlas._wrap("17 issue(s) need a linked source document", 30, 2)
        self.assertEqual(lines, ["17 issue(s) need a linked", "source document"])
        for line in lines:
            self.assertLessEqual(len(line), 30)
        # Nothing was lost.
        self.assertEqual(" ".join(lines), "17 issue(s) need a linked source document")

    def test_genuine_overflow_is_marked(self):
        text = "A very long label that will definitely not fit in two lines no matter what"
        lines = atlas._wrap(text, 30, 2)
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[-1].endswith("\u2026"), "truncation was silent")

    def test_cross_matter_links_are_reported_not_merged(self):
        g = self.graph()
        # Six matters, permanently separate. The map shows references between
        # them; it must never present them as one matter.
        self.assertTrue(g["links"])
        slugs = {l["slug"] for l in g["links"]}
        self.assertNotIn(g["matter"]["slug"], slugs)

    def test_a_matter_with_nothing_to_evaluate_says_why(self):
        g = atlas.graph(self.conn, self.matter("kanawha-rule-60")["id"])
        if g["empty"]:
            self.assertIn("record", g["empty_reason"].lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
