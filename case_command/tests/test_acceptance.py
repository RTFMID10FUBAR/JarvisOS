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
    access, audit, backup, checks, fleet, health, migrate_tree, packets,
    preservation, triage, views, watcher,
)
from ..classify import classify_text
from ..config import (
    ARCHIVE, FINAL_FILINGS, INBOX, MORTGAGE, PSC_AEP, SHARED_EVIDENCE,
    VETERANS, ensure_layout, load_config,
)
from ..db import insert, open_database
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
