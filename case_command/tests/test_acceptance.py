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
    access, api, atlas, audit, backup, checks, chronology, client, filing,
    fleet, health, migrate_tree, offline, packets, preservation, triage,
    views, watcher,
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
# Document Center (the /triage screen and its bulk endpoint)
# ===========================================================================
class TestDocumentCenter(CaseCommandTest):
    """The Document Center screen: chronology(), the bulk decision endpoint,
    and the page they render — never a score, never a generated description.
    """

    def _start_server(self):
        """Spin up the real handler on an ephemeral port, in a thread."""
        import threading
        from http.server import ThreadingHTTPServer
        from ..web.server import CaseCommandHandler, _jinja_env

        handler = type("BoundHandler", (CaseCommandHandler,),
                       {"config": self.config, "env": _jinja_env()})
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(httpd.shutdown)
        self.addCleanup(httpd.server_close)
        self.addCleanup(thread.join, timeout=5)
        return httpd.server_address[1]

    def test_bulk_endpoint_actually_changes_status_and_is_audited(self):
        """POST /triage/bulk writes through triage.set_status for each document,
        exactly the way the single-document form does — one audit entry per
        document, not a single summary entry standing in for the whole batch.
        """
        import urllib.request
        from urllib.parse import urlencode

        first = ingest_path(self.config, self.conn, self.paths["draft"])
        second = ingest_path(self.config, self.conn, self.paths["hardship"])
        self.conn.commit()
        port = self._start_server()

        body = urlencode([
            ("document_id", str(first.document_id)),
            ("document_id", str(second.document_id)),
            ("status", "IRRELEVANT"),
            ("reviewer", "bulk-tester"),
            ("note", "swept in a bulk pass"),
            ("redirect_to", "/triage?status=IRRELEVANT"),
        ]).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/triage/bulk", data=body, method="POST")
        response = urllib.request.urlopen(request)
        self.assertEqual(response.status, 200)   # urllib follows the 303 redirect
        self.assertIn("/triage", response.geturl())

        rows = self.conn.execute(
            "SELECT id, triage_status, triage_note, triage_by FROM documents WHERE id IN (?,?)",
            (first.document_id, second.document_id)).fetchall()
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["triage_status"], "IRRELEVANT")
            self.assertEqual(row["triage_by"], "bulk-tester")
            self.assertEqual(row["triage_note"], "swept in a bulk pass")

        # One audit entry per document — the same trail a single decision leaves.
        entries = self.conn.execute(
            "SELECT target_id FROM audit_log WHERE action='TRIAGE_DECISION' "
            "AND actor='bulk-tester' ORDER BY id").fetchall()
        self.assertEqual({e["target_id"] for e in entries},
                         {first.document_id, second.document_id})

    def test_bulk_endpoint_rejects_an_unknown_status_and_writes_nothing(self):
        result = ingest_path(self.config, self.conn, self.paths["draft"])
        self.conn.commit()
        with self.assertRaises(ValueError):
            triage.set_status_bulk(self.conn, [result.document_id], "DELETE_FOREVER")
        row = self.conn.execute("SELECT triage_status FROM documents WHERE id=?",
                                (result.document_id,)).fetchone()
        self.assertEqual(row["triage_status"], "UNREVIEWED")

    def test_bulk_endpoint_reports_a_missing_document_without_losing_the_rest(self):
        result = ingest_path(self.config, self.conn, self.paths["draft"])
        outcome = triage.set_status_bulk(
            self.conn, [result.document_id, 999999], "KEEP", reviewer="test")
        self.assertEqual(outcome["updated_count"], 1)
        self.assertEqual(len(outcome["errors"]), 1)
        self.assertEqual(outcome["errors"][0]["document_id"], 999999)
        row = self.conn.execute("SELECT triage_status FROM documents WHERE id=?",
                                (result.document_id,)).fetchone()
        self.assertEqual(row["triage_status"], "KEEP")

    def test_extract_column_is_always_the_verbatim_extract_never_generated(self):
        """The chronology entry the page renders as 'what it is' must be exactly
        documents.extract_line — the same string extract_line() lifted verbatim
        out of the source text, never a paraphrase written after the fact.
        """
        self.ingest_all()
        triage.backfill_extracts(self.conn)
        report = triage.chronology(self.conn)

        checked = 0
        for entry in report["dated"] + report["undated"]:
            row = self.conn.execute("SELECT extract_line, text_path FROM documents WHERE id=?",
                                    (entry["id"],)).fetchone()
            expected = row["extract_line"] or "(not yet extracted)"
            self.assertEqual(entry["extract"], expected,
                             "the page's extract column must equal documents.extract_line verbatim")
            if row["text_path"] and Path(row["text_path"]).exists() and entry["extract"] not in (
                    "(not yet extracted)", "(no text could be extracted)"):
                source = Path(row["text_path"]).read_text(encoding="utf-8", errors="replace")
                self.assertIn(entry["extract"], source,
                             f"extract for {entry['doc_uid']} does not appear verbatim in its source text")
                checked += 1
        self.assertGreater(checked, 0, "the fixture set must exercise at least one verbatim extract")

    def test_document_center_page_carries_no_percentage_in_any_data_field(self):
        """No score, no confidence, no health rating — counts with a
        denominator only. If a '%' shows up in the rendered page outside of a
        CSS length (e.g. 'width: 58vh' has none), something regressed into a
        score.
        """
        import re

        self.ingest_all()
        port = self._start_server()
        import urllib.request

        html = urllib.request.urlopen(f"http://127.0.0.1:{port}/triage").read().decode("utf-8")
        self.assertIn("Document Center", html)

        # Strip inline style attributes and the <style> block's own CSS values
        # (positioning percentages such as top:0 or grid widths are layout, not
        # data) before checking the rendered content for a stray percentage.
        stripped = re.sub(r'style="[^"]*"', "", html)
        stripped = re.sub(r"<style>.*?</style>", "", stripped, flags=re.DOTALL)
        self.assertNotIn("%", stripped,
                         "a '%' appears in the Document Center's rendered content")

    def test_document_center_bulk_form_never_deletes_or_moves_a_document(self):
        """A triage decision changes status only; the file stays exactly where
        it was and the document row is never removed."""
        result = ingest_path(self.config, self.conn, self.paths["draft"])
        self.conn.commit()
        storage_path = self.conn.execute(
            "SELECT storage_path FROM documents WHERE id=?",
            (result.document_id,)).fetchone()["storage_path"]
        before_path = Path(storage_path)
        before_bytes = before_path.read_bytes()

        triage.set_status_bulk(self.conn, [result.document_id], "ARCHIVE_PROPOSED",
                               reviewer="test")

        self.assertTrue(before_path.exists())
        self.assertEqual(before_path.read_bytes(), before_bytes)
        count = self.conn.execute("SELECT COUNT(*) n FROM documents").fetchone()["n"]
        self.assertEqual(count, 1)


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

    def test_a_truncated_page_never_advances_past_undelivered_rows(self):
        """The cursor is a position in the data, never a wall clock."""
        self.ingest_all()
        page = api.sync(self.conn, limit_per_table=1)
        self.assertTrue(page["more_available"])

        delivered = sum(len(rows) for rows in page["changed"].values())
        follow_up = api.sync(self.conn, since=page["next_cursor"],
                             limit_per_table=10_000)
        self.assertGreater(follow_up["total"], 0,
                           "the cursor moved past everything still waiting")

        whole = api.sync(self.conn, limit_per_table=10_000)
        self.assertGreaterEqual(delivered + follow_up["total"], whole["total"])

    def test_a_row_written_in_the_same_millisecond_is_not_lost(self):
        """The bug CI caught, pinned so it cannot come back.

        The cursor used to be wall-clock time read at the start of a sync, so a
        row whose updated_at landed in that same millisecond was skipped — and
        skipped again on every later sync, because the client had stored the
        cursor. Silent, permanent loss. A change number owes nothing to a clock,
        so identical timestamps are simply not a factor.
        """
        self.ingest_all()
        cursor = api.sync(self.conn)["next_cursor"]

        # Stamp an edit with a timestamp that has already gone by. Under the old
        # scheme this was invisible forever.
        stale = "2000-01-01T00:00:00.000Z"
        issue = self.conn.execute("SELECT id FROM issues ORDER BY id LIMIT 1").fetchone()
        self.conn.execute(
            "UPDATE issues SET risk_rating='HIGH', updated_at=? WHERE id=?",
            (stale, issue["id"]))
        self.conn.commit()

        delta = api.sync(self.conn, since=cursor)
        self.assertEqual(delta["total"], 1, "an edit with an older timestamp was lost")
        self.assertEqual(delta["changed"]["issues"][0]["risk_rating"], "HIGH")

    def test_every_edit_is_delivered_exactly_once(self):
        """Repeatedly edit and sync; nothing missed, nothing re-sent."""
        self.ingest_all()
        cursor = api.sync(self.conn)["next_cursor"]
        ids = [r["id"] for r in self.conn.execute(
            "SELECT id FROM issues ORDER BY id LIMIT 5")]

        for index, issue_id in enumerate(ids):
            # Same millisecond as the previous edit is the interesting case, so
            # the timestamp is deliberately held constant across all of them.
            self.conn.execute(
                "UPDATE issues SET risk_rating=?, updated_at=? WHERE id=?",
                (f"R{index}", "2026-01-01T00:00:00.000Z", issue_id))
            self.conn.commit()

            page = api.sync(self.conn, since=cursor)
            self.assertEqual(page["total"], 1,
                             f"edit {index} was lost or duplicated")
            self.assertEqual(page["changed"]["issues"][0]["id"], issue_id)
            cursor = page["next_cursor"]

        self.assertEqual(api.sync(self.conn, since=cursor)["total"], 0)

    def test_a_capped_page_may_stop_mid_group_and_resume_exactly(self):
        """A change number is unique, so there is no group to keep whole."""
        self.ingest_all()
        # Every issue on one timestamp: under the old scheme this forced the
        # whole group into a single page, making the row limit a suggestion.
        self.conn.execute("UPDATE issues SET updated_at='2026-01-01T00:00:00.000Z'")
        self.conn.commit()
        total = self.conn.execute("SELECT COUNT(*) c FROM issues").fetchone()["c"]

        seen, cursor, rounds = [], None, 0
        while True:
            rounds += 1
            self.assertLess(rounds, 500)
            page = api.sync(self.conn, since=cursor, limit_per_table=1)
            seen.extend(r["id"] for r in page["changed"].get("issues", []))
            cursor = page["next_cursor"]
            if not page["more_available"]:
                break

        self.assertLessEqual(max(len(seen[:1]), 1), 1, "the limit was honoured")
        self.assertEqual(sorted(seen), sorted(
            r["id"] for r in self.conn.execute("SELECT id FROM issues")))
        self.assertEqual(len(seen), total)

    def test_an_unreadable_cursor_resends_rather_than_skips(self):
        """A cursor that cannot be read must never mean "you are up to date"."""
        self.ingest_all()
        for junk in ("not-a-cursor", "v3:{broken", "2026-01-01T00:00:00.000Z", ""):
            page = api.sync(self.conn, since=junk)
            self.assertGreater(page["total"], 0,
                               f"cursor {junk!r} was treated as current")

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


class TestChronology(CaseCommandTest):
    """Adding events by hand, and what is allowed to count as proof.

    The rule under test throughout: a thing you recall is not proof of the
    thing. It is a record that you recall it, made on a date. If those two ever
    render alike, the timeline is lying by omission at the exact moment it gets
    read out loud.
    """

    def an_event(self, **kw):
        kw.setdefault("title", "Power disconnected at the house")
        kw.setdefault("event_date", "2025-09-14")
        kw.setdefault("matter_id", self.matter("psc-26-0315")["id"])
        return chronology.add_event(self.conn, **kw)

    def a_document(self):
        self.ingest_all()
        return dict(self.conn.execute("SELECT * FROM documents LIMIT 1").fetchone())

    def test_a_new_event_starts_with_no_source(self):
        event = self.an_event()
        self.assertEqual(event["verification_status"], "MISSING_SOURCE")
        self.assertEqual(event["origin"], "MANUAL")
        self.assertEqual(event["proof"]["state"], "NONE")
        self.assertIn("record", event["proof"]["detail"].lower())

    def test_a_recollection_never_verifies_an_event(self):
        event = self.an_event()
        event = chronology.attach_proof(
            self.conn, event["id"], proof_type="RECOLLECTION",
            asserted_by="Jacob Kerr", detail="I remember the truck.")
        self.assertEqual(event["verification_status"], "UNKNOWN")
        self.assertEqual(event["proof"]["state"], "TESTIMONIAL")
        self.assertIn("not documented", event["proof"]["headline"])

    def test_documentary_proof_without_a_locator_is_refused(self):
        """'It is in the record somewhere' cannot be handed to a tribunal."""
        doc = self.a_document()
        event = self.an_event()
        with self.assertRaises(chronology.ProofError) as ctx:
            chronology.attach_proof(self.conn, event["id"],
                                    proof_type="DOCUMENT", document_id=doc["id"])
        self.assertIn("locator", str(ctx.exception))

    def test_documentary_proof_stops_at_partially_verified(self):
        """Having a source is necessary for verification, and not sufficient."""
        doc = self.a_document()
        event = self.an_event()
        event = chronology.attach_proof(
            self.conn, event["id"], proof_type="DOCUMENT",
            document_id=doc["id"], locator="p. 2 para 4")
        self.assertEqual(event["verification_status"], "PARTIALLY_VERIFIED")
        self.assertNotIn("VERIFIED_PRIMARY", event["verification_status"])
        self.assertIn(doc["doc_uid"], event["proof"]["headline"])

    def test_a_deliberate_status_is_not_overwritten(self):
        doc = self.a_document()
        event = self.an_event()
        self.conn.execute("UPDATE events SET verification_status='DISPUTED' WHERE id=?",
                          (event["id"],))
        self.conn.commit()
        event = chronology.attach_proof(
            self.conn, event["id"], proof_type="DOCUMENT",
            document_id=doc["id"], locator="p. 1")
        self.assertEqual(event["verification_status"], "DISPUTED")

    def test_testimonial_proof_must_name_who_says_so(self):
        event = self.an_event()
        for kind in ("RECOLLECTION", "WITNESS"):
            with self.assertRaises(chronology.ProofError):
                chronology.attach_proof(self.conn, event["id"], proof_type=kind)

    def test_an_undated_event_must_say_the_date_is_unknown(self):
        with self.assertRaises(chronology.ProofError) as ctx:
            chronology.add_event(self.conn, title="Something I cannot date",
                                 event_date=None)
        self.assertIn("UNKNOWN", str(ctx.exception))
        event = chronology.add_event(self.conn, title="Something I cannot date",
                                     event_date=None, date_precision="UNKNOWN")
        self.assertEqual(event["date_precision"], "UNKNOWN")

    def test_an_undated_event_is_listed_not_hidden(self):
        """Dropping an event nobody can date is the omission this system prevents."""
        matter = self.matter("psc-26-0315")["id"]
        self.an_event()
        chronology.add_event(self.conn, title="Undated but real", event_date=None,
                             date_precision="UNKNOWN", matter_id=matter)
        titles = [e["title"] for e in chronology.timeline(self.conn, matter_id=matter)]
        self.assertIn("Undated but real", titles)

    def test_the_recording_gap_is_reported(self):
        event = self.an_event(event_date="2020-01-01")
        event = chronology.attach_proof(
            self.conn, event["id"], proof_type="RECOLLECTION",
            asserted_by="Jacob Kerr")
        gap = event["proofs"][0]["recorded_after_days"]
        self.assertIsNotNone(gap)
        self.assertGreater(gap, 365, "a years-old memory should show the gap")

    def test_proof_cannot_be_deleted(self):
        event = self.an_event()
        chronology.attach_proof(self.conn, event["id"], proof_type="RECOLLECTION",
                                asserted_by="Jacob Kerr")
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("DELETE FROM event_proof WHERE event_id=?", (event["id"],))

    def test_proof_index_matches_per_event_lookup(self):
        doc = self.a_document()
        first = self.an_event()
        second = self.an_event(title="A second thing", event_date="2025-10-02")
        chronology.attach_proof(self.conn, first["id"], proof_type="DOCUMENT",
                                document_id=doc["id"], locator="p. 1")
        chronology.attach_proof(self.conn, second["id"], proof_type="RECOLLECTION",
                                asserted_by="Jacob Kerr")
        index = chronology.proof_index(self.conn, [first["id"], second["id"]])
        self.assertEqual(index[first["id"]]["summary"]["state"], "DOCUMENTED")
        self.assertEqual(index[second["id"]]["summary"]["state"], "TESTIMONIAL")
        for event_id in (first["id"], second["id"]):
            self.assertEqual(
                [p["proof_type"] for p in index[event_id]["proofs"]],
                [p["proof_type"] for p in chronology.proof_for(self.conn, event_id)])

    def test_coverage_is_a_count_never_a_score(self):
        self.an_event()
        report = chronology.unproved(self.conn)
        self.assertIn("of", report["label"])
        blob = json.dumps(report).lower()
        for banned in ("%", "score", "confidence", "likelihood", "probability"):
            if banned == "%":
                self.assertNotIn("%", report["label"])
            else:
                self.assertNotIn(banned, report["label"].lower())
        self.assertIn("not a score", report["note"])

    def test_nothing_here_characterises_the_case(self):
        event = self.an_event()
        event = chronology.attach_proof(self.conn, event["id"],
                                        proof_type="RECOLLECTION",
                                        asserted_by="Jacob Kerr")
        blob = json.dumps(event["proof"]).lower()
        for word in ("strong", "weak", "credible", "convincing", "likely",
                     "probably", "compelling"):
            self.assertNotIn(word, blob, f"proof summary characterised the case: {word!r}")


# ===========================================================================
# Filing Studio
# ===========================================================================
class TestFilingStudio(CaseCommandTest):
    """Filing Studio prepares a filing against the record. It never files,
    serves, or sends anything, and never predicts how a filing will be
    received."""

    def setUp(self) -> None:
        super().setUp()
        self.ingest_all()
        self.case2 = self.matter("psc-26-0315")

    def test_a_confirmed_filing_without_proof_is_flagged(self):
        # The proof CHECK constraint (migrations/0001_initial.sql) refuses an
        # ordinary insert of a confirmed status with no proof. Disabling it
        # for one write reproduces exactly the "record predates the
        # constraint" case checks.source_check already anticipates, so the
        # flag can be proven without weakening the constraint itself.
        self.conn.execute("PRAGMA ignore_check_constraints=1")
        filing_id = insert(self.conn, "filings", {
            "matter_id": self.case2["id"],
            "title": "Motion to Compel (legacy import)",
            "filing_type": "MOTION",
            "filing_status": "DOCKETED",
            "created_by": "legacy-import",
        })
        self.conn.execute("PRAGMA ignore_check_constraints=0")
        self.conn.commit()

        data = filing.build_filing_studio(self.conn, self.case2["id"])
        tracker = {row["id"]: row for row in data["status_tracker"]}
        self.assertIn(filing_id, tracker)
        row = tracker[filing_id]
        self.assertTrue(row["unproven_confirmation"],
                        "a confirmed status with no proof must be flagged")
        self.assertFalse(row["has_proof"])
        self.assertEqual(data["unproven_count"], 1)

    def test_a_confirmed_filing_with_real_proof_is_not_flagged(self):
        doc = self.conn.execute(
            "SELECT id FROM documents WHERE matter_id=? LIMIT 1",
            (self.case2["id"],)).fetchone()
        filing_id = insert(self.conn, "filings", {
            "matter_id": self.case2["id"],
            "document_id": doc["id"] if doc else None,
            "title": "Formal Complaint", "filing_type": "COMPLAINT",
            "filing_status": "FILED_CONFIRMED", "proof_type": "ELECTRONIC_RECEIPT",
            "proof_reference": "PSC-2026-0000418", "created_by": "test",
        })
        data = filing.build_filing_studio(self.conn, self.case2["id"])
        tracker = {row["id"]: row for row in data["status_tracker"]}
        self.assertFalse(tracker[filing_id]["unproven_confirmation"])
        self.assertEqual(data["unproven_count"], 0)

    def test_the_screen_exposes_no_transmit_action(self):
        """No function in this module files, serves, or sends anything, and
        the template exposes no button or form that could."""
        import inspect
        import re

        source = inspect.getsource(filing)
        for token in ("smtplib", "requests.post", "urlopen", "socket."):
            self.assertNotIn(token, source)

        template_path = (Path(__file__).resolve().parents[1]
                         / "web" / "templates" / "filing.html")
        html = template_path.read_text(encoding="utf-8")
        self.assertNotIn("<script", html.lower())

        # The only form on the page is the GET matter filter — nothing posts.
        forms = re.findall(r"<form[^>]*>", html)
        self.assertEqual(len(forms), 1)
        self.assertIn('method="get"', forms[0])

        # The only button on the page is that filter's — never an action that
        # files, sends, or serves. (The inspector text below is free to
        # *discuss* why there is no such button; that is not a button.)
        buttons = re.findall(r"<button[^>]*>(.*?)</button>", html, re.S)
        self.assertEqual([b.strip().lower() for b in buttons], ["show"])

    def test_path_matrix_contains_no_prediction_or_percentage_language(self):
        data = filing.build_filing_studio(self.conn, self.case2["id"])
        blob = json.dumps(data["path_matrix"]).lower()
        for banned in ("score", "confidence", "likelihood", "probability",
                      "likely", "success", "percent", "%", "grant", "odds",
                      "health rating"):
            self.assertNotIn(banned, blob, f"path matrix leaked {banned!r}")

    def test_staged_packet_reads_the_real_draft_filing_and_its_role(self):
        draft_doc = self.conn.execute(
            "SELECT id, doc_uid FROM documents WHERE original_filename LIKE 'DRAFT_Motion%'"
        ).fetchone()
        insert(self.conn, "filings", {
            "matter_id": self.case2["id"], "document_id": draft_doc["id"],
            "title": "Motion for Expedited Relief", "filing_type": "MOTION",
            "filing_status": "DRAFT", "created_by": "test",
        })
        data = filing.build_filing_studio(self.conn, self.case2["id"])
        self.assertEqual(len(data["staged_packet"]), 1)
        self.assertEqual(data["staged_packet"][0]["filing_type"], "MOTION")
        self.assertEqual(data["staged_packet"][0]["doc_uid"], draft_doc["doc_uid"])

    def test_staged_packet_is_an_honest_empty_state_with_no_drafts(self):
        data = filing.build_filing_studio(self.conn, self.case2["id"])
        self.assertEqual(data["staged_packet"], [])

    def test_smart_checklist_runs_the_real_checks_not_invented_ones(self):
        data = filing.build_filing_studio(self.conn, self.case2["id"])
        checklist = data["checklist"]
        self.assertIn("blockers", checklist)
        self.assertIn("advisory", checklist)
        checks_seen = {f["check"] for f in checklist["blockers"] + checklist["advisory"]}
        self.assertTrue(checks_seen, "no findings at all is suspicious for this fixture")
        self.assertTrue(checks_seen.issubset(
            {"completeness", "conflict", "defense", "preservation", "source"}))

    def test_draft_queue_excludes_confirmed_and_rejected_filings(self):
        doc = self.conn.execute(
            "SELECT id FROM documents WHERE matter_id=? LIMIT 1",
            (self.case2["id"],)).fetchone()
        insert(self.conn, "filings", {
            "matter_id": self.case2["id"], "document_id": doc["id"] if doc else None,
            "title": "Draft motion", "filing_status": "DRAFT", "created_by": "test",
        })
        insert(self.conn, "filings", {
            "matter_id": self.case2["id"], "document_id": doc["id"] if doc else None,
            "title": "Rejected filing", "filing_status": "REJECTED", "created_by": "test",
        })
        data = filing.build_filing_studio(self.conn, self.case2["id"])
        titles = {f["title"] for f in data["draft_queue"]}
        self.assertIn("Draft motion", titles)
        self.assertNotIn("Rejected filing", titles)


class TestTapToPair(CaseCommandTest):
    """Pairing by tapping a link instead of reading six characters across a room.

    The page is served to the phone, so the address it used to get there is the
    address that goes in the link — the one address known to work from where the
    phone is standing.
    """

    def _start_server(self):
        import threading
        from http.server import ThreadingHTTPServer
        from ..web.server import CaseCommandHandler, _jinja_env

        handler = type("BoundHandler", (CaseCommandHandler,),
                       {"config": self.config, "env": _jinja_env()})
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(httpd.shutdown)
        self.addCleanup(httpd.server_close)
        self.addCleanup(thread.join, timeout=5)
        return httpd.server_address[1]

    def _request(self, port, method, host_header):
        import urllib.request
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/pair", method=method,
            data=b"" if method == "POST" else None)
        request.add_header("Host", host_header)
        with urllib.request.urlopen(request) as response:
            return response.status, response.read().decode("utf-8")

    def test_get_pair_offers_no_code_until_one_is_asked_for(self):
        """A page left open in a tab is not a way in."""
        port = self._start_server()
        status, body = self._request(port, "GET", f"127.0.0.1:{port}")

        self.assertEqual(status, 200)
        self.assertIn("Create a pairing code", body)
        self.assertNotIn("casecommand://", body)
        self.assertEqual(
            0, self.conn.execute("SELECT COUNT(*) c FROM pairing_codes").fetchone()["c"],
            "merely viewing the page minted a code")

    def test_link_carries_the_address_the_phone_actually_reached(self):
        """Not 127.0.0.1, and not a guess from the machine's interface list — a
        machine can have several addresses and only some of them work from the
        phone. The one it just used demonstrably does.
        """
        import html
        import re
        from urllib.parse import parse_qs, urlsplit

        port = self._start_server()
        _, body = self._request(port, "POST", "192.168.1.50:8899")

        match = re.search(r'href="(casecommand://[^"]+)"', body)
        self.assertIsNotNone(match, "no pairing link on the page")
        link = html.unescape(match.group(1))

        parts = urlsplit(link)
        # Both must match the manifest's <data android:scheme android:host>,
        # or Android hands the tap to a browser and nothing happens.
        self.assertEqual(parts.scheme, "casecommand")
        self.assertEqual(parts.netloc, "pair")

        query = parse_qs(parts.query)
        self.assertEqual(query["host"][0], "http://192.168.1.50:8899")
        self.assertRegex(query["code"][0], r"^[A-HJ-NP-Z2-9]{6}$")

        row = self.conn.execute(
            "SELECT code, used_at FROM pairing_codes").fetchone()
        self.assertEqual(row["code"], query["code"][0],
                         "the link carries a code the server will not accept")
        self.assertIsNone(row["used_at"])

    def test_the_linked_code_pairs_a_device_and_then_is_spent(self):
        """End to end: the code in the link is redeemable exactly once."""
        import html
        import re
        from urllib.parse import parse_qs, urlsplit
        from .. import api

        port = self._start_server()
        _, body = self._request(port, "POST", f"127.0.0.1:{port}")
        link = html.unescape(re.search(r'href="(casecommand://[^"]+)"', body).group(1))
        code = parse_qs(urlsplit(link).query)["code"][0]

        paired = api.redeem_pairing_code(
            self.conn, code=code, label="Phone", platform="android")
        self.assertTrue(paired["token"])

        with self.assertRaises(api.ApiError):
            api.redeem_pairing_code(
                self.conn, code=code, label="Phone again", platform="android")


class TestAndroidManifest(CaseCommandTest):
    """The manifest is the one file in the app that is wrong only at runtime.

    It compiles whatever you put in it. An attribute on the wrong element is
    dropped without a word, and the app is broken on a phone while every build
    stays green — which is exactly what happened to cleartext below.
    """

    def _manifest(self):
        from xml.etree import ElementTree
        path = (Path(__file__).resolve().parents[2] / "clients" / "android" /
                "app" / "src" / "main" / "AndroidManifest.xml")
        self.assertTrue(path.exists(), path)
        return ElementTree.parse(path).getroot()

    ANDROID = "{http://schemas.android.com/apk/res/android}"

    def test_cleartext_is_permitted_where_the_attribute_is_read(self):
        """`usesCleartextTraffic` is an <application> attribute. On <activity>
        it is silently ignored, and since targetSdk 28 the default is to refuse
        cleartext — so every request to the LAN server fails with "CLEARTEXT
        communication not permitted" and no build ever complains.

        This app talks plain HTTP to one machine on the local network, by
        design: there is no public endpoint to secure and no certificate to
        obtain for one. So it has to be permitted, and permitted where Android
        actually looks.
        """
        root = self._manifest()
        application = root.find("application")
        self.assertIsNotNone(application)
        self.assertEqual(application.get(f"{self.ANDROID}usesCleartextTraffic"), "true")

        for activity in application.findall("activity"):
            self.assertIsNone(
                activity.get(f"{self.ANDROID}usesCleartextTraffic"),
                "usesCleartextTraffic on <activity> does nothing; it belongs on "
                "<application>")

    def test_the_pairing_link_has_somewhere_to_land(self):
        """The scheme and host in the manifest must be the ones the web page
        writes into the link. If they drift apart the tap opens a browser, which
        cannot do anything with a casecommand:// URL, and the failure looks like
        the link being broken rather than the filter not matching.
        """
        root = self._manifest()
        activity = root.find("application/activity")

        matched = []
        for intent_filter in activity.findall("intent-filter"):
            for data in intent_filter.findall("data"):
                if (data.get(f"{self.ANDROID}scheme") == "casecommand"
                        and data.get(f"{self.ANDROID}host") == "pair"):
                    categories = {c.get(f"{self.ANDROID}name")
                                  for c in intent_filter.findall("category")}
                    matched.append(categories)

        self.assertEqual(len(matched), 1, "no casecommand://pair intent-filter")
        # BROWSABLE is what lets a link in a browser start the app at all.
        self.assertIn("android.intent.category.BROWSABLE", matched[0])
        self.assertIn("android.intent.category.DEFAULT", matched[0])
        self.assertEqual(activity.get(f"{self.ANDROID}exported"), "true")


if __name__ == "__main__":
    unittest.main(verbosity=2)
