"""Build a populated demo instance for screenshots and manual review.

    python -m case_command.tests.demo /path/to/demo_root

Everything created here is synthetic. It exercises the views with realistic
*shapes* — a pending motion, a recommended decision, a Fleet proposal awaiting
review — without asserting anything about the real cases.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .. import backup, fleet, preservation
from ..config import ensure_layout, load_config
from ..db import insert, open_database
from ..ingest import scan_all
from .fixtures import build_fixture_tree


def build(root: Path) -> dict[str, object]:
    config = load_config(data_root=root)
    ensure_layout(config)
    build_fixture_tree(config.data_root)
    conn = open_database(config)

    results = scan_all(config, conn, actor="demo")

    case2 = conn.execute("SELECT * FROM matters WHERE slug='psc-26-0315'").fetchone()
    case1 = conn.execute("SELECT * FROM matters WHERE slug='psc-24-0735'").fetchone()

    # Assign the PSC documents to Case 2 so the matter view has content.
    for row in conn.execute(
            "SELECT id FROM documents WHERE folder='00_INBOX' AND classification_rule "
            "LIKE 'psc%'").fetchall():
        conn.execute("UPDATE documents SET matter_id=? WHERE id=?", (case2["id"], row["id"]))
    conn.execute("UPDATE events SET matter_id=? WHERE matter_id IS NULL", (case2["id"],))
    # Filings inherit the matter their document was assigned to. Ingestion could
    # not know it, because the matter had not been confirmed yet.
    conn.execute("""
        UPDATE filings SET matter_id = (
            SELECT d.matter_id FROM documents d WHERE d.id = filings.document_id)
        WHERE matter_id IS NULL AND document_id IS NOT NULL
    """)

    # -- parties, counsel, ALJ ---------------------------------------------
    for name, kind, role in (("Jacob Kerr", "party", "Complainant"),
                             ("Appalachian Power Company", "utility", "Respondent"),
                             ("Commission Staff", "agency", "Staff")):
        insert(conn, "actors", {"matter_id": case2["id"], "title": name,
                                "actor_type": kind, "role": role,
                                "verification_status": "UNKNOWN"})
    insert(conn, "aljs", {"matter_id": case2["id"], "title": "(ALJ of record)",
                          "agency": "PSC of West Virginia",
                          "verification_status": "MISSING_SOURCE",
                          "notes": "Name requires confirmation from a docketed order."})

    # -- the governing rule and its elements --------------------------------
    insert(conn, "rules", {
        "matter_id": case2["id"], "title": "Pretermination process",
        "rule_number": "150 C.S.R. 3 (confirm subsection)",
        "elements": json.dumps([
            "Written notice provided before termination",
            "Personal contact attempted",
            "Dispute meeting offered on request",
            "Written decision issued after a dispute",
        ]),
        "verification_status": "MISSING_SOURCE",
        "notes": "Rule text and subsection require confirmation against the published rule.",
    })

    # -- three unresolved threshold motions ---------------------------------
    issue13 = conn.execute("SELECT id FROM issues WHERE issue_key='PSC-013'").fetchone()
    motion_ids = []
    for title, filed in (("Motion to compel the complete APCo chronology", "2026-04-01"),
                         ("Motion for a ruling on the scope of the hearing", "2026-04-08"),
                         ("Motion to strike the preclusion defense", "2026-04-15")):
        motion_ids.append(insert(conn, "motions", {
            "matter_id": case2["id"], "issue_id": issue13["id"], "title": title,
            "motion_type": "threshold", "filed_date": filed, "threshold_motion": 1,
            "ruled_on": 0, "verification_status": "UNKNOWN",
        }))
    preservation.on_motion_ignored(conn, motion_ids[0], actor="demo")

    # -- a recommended decision drives the exception workflow ---------------
    order_id = insert(conn, "orders", {
        "matter_id": case2["id"], "title": "Recommended Decision",
        "entered_date": "2026-07-20", "is_recommended_decision": 1,
        "verification_status": "MISSING_SOURCE",
    })
    preservation.on_recommended_decision(conn, order_id, actor="demo")

    # -- the Case 1 final order, with the appeal workflow -------------------
    final_id = insert(conn, "orders", {
        "matter_id": case1["id"], "title": "Final Order (Case 24-0735-E-C)",
        "entered_date": "2025-09-03", "is_final": 1,
        "verification_status": "MISSING_SOURCE",
    })
    preservation.on_final_order(conn, final_id, actor="demo")

    # -- a hearing on the calendar -----------------------------------------
    insert(conn, "events", {
        "matter_id": case2["id"], "title": "PSC evidentiary hearing",
        "event_date": "2026-08-25", "event_type": "HEARING",
        "boundary_classification": "PROCEDURAL_HISTORY", "approved": 1,
        "verification_status": "MISSING_SOURCE",
        "legal_significance": "Hearing at which the pretermination issues are tried.",
    })

    # -- a contradiction between the complaint and the answer ---------------
    complaint = conn.execute(
        "SELECT id FROM documents WHERE original_filename LIKE 'PSC_26-0315%'").fetchone()
    answer = conn.execute(
        "SELECT id FROM documents WHERE original_filename LIKE 'APCo_Answer%'").fetchone()
    if complaint and answer:
        insert(conn, "contradictions", {
            "matter_id": case2["id"],
            "title": "Written notice: received versus mailed",
            "left_statement": "Complainant states no pretermination written notice was received.",
            "left_source_document_id": complaint["id"], "left_source_locator": "p.1 ¶4",
            "right_statement": "APCo states written notice was mailed September 12, 2025.",
            "right_source_document_id": answer["id"], "right_source_locator": "p.1 ¶4",
            "resolved": 0, "verification_status": "DISPUTED",
        })

    # -- relief requested, no disposition yet -------------------------------
    for title in ("Restoration of electric service",
                  "Finding that pretermination process was not followed",
                  "Explanation of the $3,130.73 calculation"):
        insert(conn, "relief", {"matter_id": case2["id"], "title": title,
                                "relief_type": "requested",
                                "verification_status": "UNKNOWN"})

    # -- a Fleet proposal awaiting review -----------------------------------
    doc = conn.execute("SELECT doc_uid FROM documents LIMIT 1").fetchone()
    fleet.submit_proposal(conn, {
        "job_id": "demo-timeline-001",
        "job_type": "timeline_extraction",
        "matter_id": case2["id"],
        "documents_reviewed": [doc["doc_uid"]] if doc else [],
        "proposed_facts": [{
            "title": "Termination date",
            "statement": "Electric service was terminated on September 29, 2025.",
            "fact_date": "2025-09-29",
            "verification_status": "VERIFIED_PRIMARY",
            "source_doc_uid": doc["doc_uid"] if doc else None,
            "source_page_or_paragraph": "p.1 ¶2",
        }],
        "proposed_issue_updates": [{
            "issue_key": "PSC-002",
            "legal_element": "Written notice before termination",
            "missing_proof": "No mailing record has been produced.",
        }],
        "conflicts_found": [{
            "title": "Notice mailed versus not received",
            "left_statement": "No notice received.",
            "right_statement": "Notice mailed September 12, 2025.",
        }],
        "missing_sources": [{
            "title": "APCo mailing log for September 2025",
            "question": "Where is the mailing record for the pretermination notice?",
            "why_it_matters": "It is the only proof that notice was actually sent.",
            "how_to_resolve": "Request it in discovery or by motion to compel.",
        }],
        "defense_attacks": [{
            "title": "Preclusion: issues were decided in Case 24-0735-E-C",
            "raised_by": "APCO_COUNSEL",
            "strength": "HIGH",
            "best_reply": "The conduct at issue postdates the September 3, 2025 final order.",
        }],
        "recommended_repairs": [],
        "confidence": 0.72,
        "citations": ["150 C.S.R. 3"],
        "approval_required": True,
    }, agent="fleet-sonnet")

    backup.create_backup(config, conn, label="demo", actor="demo")
    conn.close()

    return {
        "data_root": str(config.data_root),
        "database": str(config.db_path),
        "ingested": sum(1 for r in results if r.status == "ingested"),
        "duplicates": sum(1 for r in results if r.status == "duplicate"),
    }


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("./demo_root")
    print(json.dumps(build(target), indent=2))
