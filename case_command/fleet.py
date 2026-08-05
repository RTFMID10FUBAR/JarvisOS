"""Fleet interface: narrow jobs in, reviewable proposals out.

Fleet agents never write to the canonical record. They submit proposals that
Case Command validates, stores, and holds until a human approves each item.

The prohibitions in section 6 of the specification are enforced here as
validation rules, not as documentation. A proposal that attempts a prohibited
action is rejected with a named reason and recorded in the audit log — it does
not partially apply.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from . import audit
from .db import CONFIRMED_FILING_STATUSES, insert, utcnow

#: The complete set of jobs Fleet is permitted to run. Anything else is refused.
ALLOWED_JOBS = (
    "document_extraction",
    "complaint_to_answer_comparison",
    "timeline_extraction",
    "rule_element_analysis",
    "tariff_matching",
    "contradiction_detection",
    "defense_red_team",
    "judge_view_review",
    "evidence_gap_analysis",
    "deadline_extraction",
    "proposed_findings",
    "appeal_preservation_review",
    "citation_verification",
)

#: Every field a Fleet response must return.
REQUIRED_RESPONSE_FIELDS = (
    "job_id",
    "matter_id",
    "documents_reviewed",
    "proposed_facts",
    "proposed_issue_updates",
    "conflicts_found",
    "missing_sources",
    "defense_attacks",
    "recommended_repairs",
    "confidence",
    "citations",
    "approval_required",
)

#: Issue statuses Fleet may propose. Deletion and "abandoned" are absent by
#: design: Fleet cannot decide that an argument is gone.
FLEET_ALLOWED_ISSUE_STATUSES = (
    "ACTIVE", "RESERVED", "WEAK", "MISSING_PROOF", "OUTSIDE_CURRENT_HEARING",
)

VERIFIED_STATUSES = ("VERIFIED_PRIMARY", "VERIFIED_SECONDARY")


class FleetRejection(ValueError):
    """A proposal violated a hard prohibition and was refused in full."""


@dataclass
class ValidationReport:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def validate_proposal(payload: dict[str, Any]) -> ValidationReport:
    """Check a Fleet response against the contract and the prohibitions."""
    errors: list[str] = []
    warnings: list[str] = []

    missing = [f for f in REQUIRED_RESPONSE_FIELDS if f not in payload]
    if missing:
        errors.append(f"missing required response fields: {', '.join(missing)}")

    job_type = payload.get("job_type") or payload.get("job")
    if job_type and job_type not in ALLOWED_JOBS:
        errors.append(
            f"job type {job_type!r} is not an allowed Fleet job. "
            f"Allowed: {', '.join(ALLOWED_JOBS)}"
        )

    confidence = payload.get("confidence")
    if confidence is not None:
        try:
            value = float(confidence)
            if not 0.0 <= value <= 1.0:
                errors.append("confidence must be between 0.0 and 1.0")
        except (TypeError, ValueError):
            errors.append("confidence must be a number between 0.0 and 1.0")

    # --- prohibition: no fact marked verified without a source --------------
    for index, fact in enumerate(_as_list(payload.get("proposed_facts"))):
        if not isinstance(fact, dict):
            errors.append(f"proposed_facts[{index}] must be an object")
            continue
        status = (fact.get("verification_status") or "").upper()
        has_source = bool(fact.get("source_document_id") or fact.get("source_doc_uid"))
        has_locator = bool(fact.get("source_page_or_paragraph"))
        if status in VERIFIED_STATUSES and not (has_source and has_locator):
            errors.append(
                f"proposed_facts[{index}] claims {status} without both a source document "
                "and a page/paragraph locator. Fleet may not mark a fact verified "
                "without a source."
            )
        if not has_source and status not in ("UNKNOWN", "MISSING_SOURCE", "INFERENCE", ""):
            warnings.append(
                f"proposed_facts[{index}] has no source; status downgraded to MISSING_SOURCE "
                "on storage."
            )

    # --- prohibition: no issue deletion, no abandonment ---------------------
    for index, update in enumerate(_as_list(payload.get("proposed_issue_updates"))):
        if not isinstance(update, dict):
            errors.append(f"proposed_issue_updates[{index}] must be an object")
            continue
        action = (update.get("action") or "update").lower()
        if action in ("delete", "remove", "drop", "merge"):
            errors.append(
                f"proposed_issue_updates[{index}] requests {action!r}. Fleet may not delete "
                "issues or merge matters."
            )
        status = (update.get("status") or "").upper()
        if status and status not in FLEET_ALLOWED_ISSUE_STATUSES:
            if status in ("SUPERSEDED_BY_AUTHORITY", "DECIDED"):
                errors.append(
                    f"proposed_issue_updates[{index}] sets status {status}. Only a human may "
                    "mark an issue superseded or decided."
                )
            else:
                errors.append(
                    f"proposed_issue_updates[{index}] uses invalid issue status {status!r}."
                )
        for banned in ("abandoned", "waived", "dropped"):
            if banned in json.dumps(update).lower() and "risk" not in json.dumps(update).lower():
                warnings.append(
                    f"proposed_issue_updates[{index}] mentions {banned!r}. Recorded as an "
                    "observation only; Fleet cannot decide an argument is abandoned."
                )

    # --- prohibition: no filing confirmed without proof --------------------
    for index, repair in enumerate(_as_list(payload.get("recommended_repairs"))):
        if not isinstance(repair, dict):
            continue
        target = (repair.get("target_table") or "").lower()
        new_status = (repair.get("filing_status") or repair.get("status") or "").upper()
        if target == "filings" and new_status in CONFIRMED_FILING_STATUSES:
            if not repair.get("proof_type"):
                errors.append(
                    f"recommended_repairs[{index}] sets filing status {new_status} without a "
                    "proof type. Presence in a folder or in Drive is never proof of filing."
                )

    # --- prohibition: no transmission, no overwriting ----------------------
    blob = json.dumps(payload).lower()
    for banned, why in (
        ("\"action\": \"send\"", "Fleet may not send, file, serve, or transmit documents."),
        ("\"action\": \"file\"", "Fleet may not send, file, serve, or transmit documents."),
        ("\"action\": \"serve\"", "Fleet may not send, file, serve, or transmit documents."),
        ("\"action\": \"overwrite\"", "Fleet may not overwrite source files."),
        ("\"action\": \"delete_file\"", "Fleet may not delete source files."),
    ):
        if banned in blob:
            errors.append(why)

    return ValidationReport(ok=not errors, errors=errors, warnings=warnings)


def _resolve_document_id(conn: sqlite3.Connection, item: dict[str, Any]) -> int | None:
    if item.get("source_document_id"):
        return int(item["source_document_id"])
    uid = item.get("source_doc_uid")
    if uid:
        row = conn.execute("SELECT id FROM documents WHERE doc_uid=?", (uid,)).fetchone()
        return int(row["id"]) if row else None
    return None


def submit_proposal(conn: sqlite3.Connection, payload: dict[str, Any], *,
                    agent: str = "fleet") -> dict[str, Any]:
    """Validate and store a Fleet response. Nothing is applied to the record."""
    report = validate_proposal(payload)
    job_id = str(payload.get("job_id") or f"job-{utcnow()}")

    if not report.ok:
        audit.record(conn, actor=agent, action="FLEET_PROPOSAL_REJECTED",
                     summary=job_id, payload={"errors": report.errors})
        raise FleetRejection(
            f"Fleet proposal {job_id} refused:\n  - " + "\n  - ".join(report.errors)
        )

    matter_id = payload.get("matter_id")
    proposal_id = insert(conn, "fleet_proposals", {
        "job_id": job_id,
        "matter_id": matter_id,
        "title": payload.get("title") or f"{payload.get('job_type', 'fleet job')} — {job_id}",
        "job_type": payload.get("job_type") or payload.get("job") or "unspecified",
        "agent": agent,
        "documents_reviewed": json.dumps(_as_list(payload.get("documents_reviewed"))),
        "proposed_facts": json.dumps(_as_list(payload.get("proposed_facts"))),
        "proposed_issue_updates": json.dumps(_as_list(payload.get("proposed_issue_updates"))),
        "conflicts_found": json.dumps(_as_list(payload.get("conflicts_found"))),
        "missing_sources": json.dumps(_as_list(payload.get("missing_sources"))),
        "defense_attacks": json.dumps(_as_list(payload.get("defense_attacks"))),
        "recommended_repairs": json.dumps(_as_list(payload.get("recommended_repairs"))),
        "confidence": payload.get("confidence"),
        "citations": json.dumps(_as_list(payload.get("citations"))),
        # Approval is always required, whatever the agent claims.
        "approval_required": 1,
        "review_status": "PENDING",
        "raw_payload": json.dumps(payload, default=str),
        "verification_status": "INFERENCE",
        "created_by": agent,
        "notes": "; ".join(report.warnings) or None,
    })

    counts: dict[str, int] = {}
    for item_type, key in (
        ("fact", "proposed_facts"),
        ("issue_update", "proposed_issue_updates"),
        ("conflict", "conflicts_found"),
        ("missing_source", "missing_sources"),
        ("defense_attack", "defense_attacks"),
        ("repair", "recommended_repairs"),
    ):
        for item in _as_list(payload.get(key)):
            if not isinstance(item, dict):
                item = {"value": item}
            insert(conn, "fleet_proposal_items", {
                "proposal_id": proposal_id,
                "item_type": item_type,
                "target_table": item.get("target_table"),
                "target_id": item.get("target_id"),
                "payload": json.dumps(item, default=str),
                "source_document_id": _resolve_document_id(conn, item),
                "source_page_or_paragraph": item.get("source_page_or_paragraph"),
                "decision": "PENDING",
            })
            counts[item_type] = counts.get(item_type, 0) + 1

    audit.record(conn, actor=agent, action="FLEET_PROPOSAL_SUBMITTED",
                 target_table="fleet_proposals", target_id=proposal_id,
                 matter_id=matter_id, summary=job_id,
                 payload={"counts": counts, "warnings": report.warnings})

    return {
        "proposal_id": proposal_id,
        "job_id": job_id,
        "item_counts": counts,
        "warnings": report.warnings,
        "review_status": "PENDING",
        "approval_required": True,
    }


def pending_items(conn: sqlite3.Connection, proposal_id: int | None = None) -> list[dict[str, Any]]:
    sql = ("SELECT i.*, p.job_id, p.job_type, p.matter_id FROM fleet_proposal_items i "
           "JOIN fleet_proposals p ON p.id = i.proposal_id WHERE i.decision='PENDING'")
    params: list[Any] = []
    if proposal_id is not None:
        sql += " AND i.proposal_id=?"
        params.append(proposal_id)
    sql += " ORDER BY i.id"
    return [dict(r) for r in conn.execute(sql, params)]


def _apply_fact(conn: sqlite3.Connection, item: sqlite3.Row, data: dict[str, Any],
                matter_id: int | None, reviewer: str) -> int:
    status = (data.get("verification_status") or "UNKNOWN").upper()
    # Second gate: even an approved fact cannot be stored as verified unless a
    # source document and locator actually resolve.
    if status in VERIFIED_STATUSES and not (item["source_document_id"]
                                            and item["source_page_or_paragraph"]):
        status = "MISSING_SOURCE"
    return insert(conn, "facts", {
        "matter_id": data.get("matter_id") or matter_id,
        "title": data.get("title") or (data.get("statement") or "Proposed fact")[:120],
        "statement": data.get("statement"),
        "fact_date": data.get("fact_date"),
        "disputed": 1 if data.get("disputed") else 0,
        "approved": 1,
        "verification_status": status,
        "source_document_id": item["source_document_id"],
        "source_page_or_paragraph": item["source_page_or_paragraph"],
        "created_by": "fleet",
        "last_reviewed_by": reviewer,
        "notes": data.get("notes"),
    })


def _apply_issue_update(conn: sqlite3.Connection, data: dict[str, Any],
                        reviewer: str) -> int | None:
    issue_key = data.get("issue_key")
    issue_id = data.get("issue_id")
    if issue_key and not issue_id:
        row = conn.execute("SELECT id FROM issues WHERE issue_key=?", (issue_key,)).fetchone()
        issue_id = row["id"] if row else None
    if not issue_id:
        return None

    updatable = ("legal_element", "inference", "best_reply", "opponent_defense",
                 "missing_proof", "requested_finding", "requested_relief",
                 "appeal_standard", "risk_rating", "hearing_scope", "notes")
    changes = {k: data[k] for k in updatable if k in data and data[k] is not None}
    if data.get("status") in FLEET_ALLOWED_ISSUE_STATUSES:
        changes["status"] = data["status"]
    if not changes:
        return int(issue_id)
    changes["last_reviewed_by"] = reviewer
    changes["updated_at"] = utcnow()
    assignments = ",".join(f"{k}=?" for k in changes)
    conn.execute(f"UPDATE issues SET {assignments} WHERE id=?",
                 [*changes.values(), issue_id])
    return int(issue_id)


def _apply_conflict(conn: sqlite3.Connection, data: dict[str, Any],
                    matter_id: int | None, reviewer: str) -> int:
    return insert(conn, "contradictions", {
        "matter_id": data.get("matter_id") or matter_id,
        "issue_id": data.get("issue_id"),
        "title": data.get("title") or "Contradiction reported by Fleet",
        "left_statement": data.get("left_statement") or data.get("statement_a"),
        "left_source_document_id": data.get("left_source_document_id"),
        "left_source_locator": data.get("left_source_locator"),
        "right_statement": data.get("right_statement") or data.get("statement_b"),
        "right_source_document_id": data.get("right_source_document_id"),
        "right_source_locator": data.get("right_source_locator"),
        "resolved": 0,
        "verification_status": "DISPUTED",
        "created_by": "fleet",
        "last_reviewed_by": reviewer,
        "notes": data.get("notes"),
    })


def decide_item(conn: sqlite3.Connection, item_id: int, decision: str, *,
                reviewer: str, note: str | None = None) -> dict[str, Any]:
    """Approve or reject one proposed change, applying it only on approval."""
    decision = decision.upper()
    if decision not in ("APPROVED", "REJECTED"):
        raise ValueError("decision must be APPROVED or REJECTED")

    item = conn.execute("SELECT * FROM fleet_proposal_items WHERE id=?", (item_id,)).fetchone()
    if item is None:
        raise ValueError(f"no fleet proposal item {item_id}")
    if item["decision"] != "PENDING":
        raise ValueError(f"item {item_id} was already {item['decision']}")

    proposal = conn.execute("SELECT * FROM fleet_proposals WHERE id=?",
                            (item["proposal_id"],)).fetchone()
    data = json.loads(item["payload"])
    applied_id: int | None = None

    if decision == "APPROVED":
        if item["item_type"] == "fact":
            applied_id = _apply_fact(conn, item, data, proposal["matter_id"], reviewer)
        elif item["item_type"] == "issue_update":
            applied_id = _apply_issue_update(conn, data, reviewer)
        elif item["item_type"] == "conflict":
            applied_id = _apply_conflict(conn, data, proposal["matter_id"], reviewer)
        elif item["item_type"] == "missing_source":
            applied_id = insert(conn, "unknowns", {
                "matter_id": proposal["matter_id"],
                "issue_id": data.get("issue_id"),
                "title": data.get("title") or "Missing source reported by Fleet",
                "question": data.get("question") or data.get("description"),
                "why_it_matters": data.get("why_it_matters"),
                "how_to_resolve": data.get("how_to_resolve"),
                "verification_status": "MISSING_SOURCE",
                "created_by": "fleet",
                "last_reviewed_by": reviewer,
            })
        elif item["item_type"] == "defense_attack":
            applied_id = insert(conn, "defenses", {
                "matter_id": proposal["matter_id"],
                "issue_id": data.get("issue_id"),
                "title": data.get("title") or "Defense attack identified by Fleet",
                "raised_by": data.get("raised_by") or "red-team review",
                "strength": data.get("strength"),
                "best_reply": data.get("best_reply"),
                "verification_status": "INFERENCE",
                "source_document_id": item["source_document_id"],
                "source_page_or_paragraph": item["source_page_or_paragraph"],
                "created_by": "fleet",
                "last_reviewed_by": reviewer,
            })
        else:
            # Repairs are recorded as reviewed notes; they never mutate a record
            # on their own.
            applied_id = insert(conn, "unknowns", {
                "matter_id": proposal["matter_id"],
                "title": data.get("title") or "Recommended repair",
                "question": json.dumps(data)[:900],
                "why_it_matters": "Fleet recommended a repair to the record.",
                "how_to_resolve": "Apply manually after review.",
                "verification_status": "INFERENCE",
                "created_by": "fleet",
                "last_reviewed_by": reviewer,
            })

    conn.execute(
        "UPDATE fleet_proposal_items SET decision=?, decided_by=?, decided_at=?, "
        "applied=?, applied_record_id=?, notes=? WHERE id=?",
        (decision, reviewer, utcnow(), 1 if applied_id else 0, applied_id, note, item_id),
    )

    remaining = conn.execute(
        "SELECT COUNT(*) AS n FROM fleet_proposal_items WHERE proposal_id=? AND decision='PENDING'",
        (item["proposal_id"],),
    ).fetchone()["n"]
    if remaining == 0:
        approved = conn.execute(
            "SELECT COUNT(*) AS n FROM fleet_proposal_items WHERE proposal_id=? AND decision='APPROVED'",
            (item["proposal_id"],),
        ).fetchone()["n"]
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM fleet_proposal_items WHERE proposal_id=?",
            (item["proposal_id"],),
        ).fetchone()["n"]
        status = ("APPROVED" if approved == total
                  else "REJECTED" if approved == 0 else "PARTIALLY_APPROVED")
        conn.execute(
            "UPDATE fleet_proposals SET review_status=?, reviewed_by=?, reviewed_at=? WHERE id=?",
            (status, reviewer, utcnow(), item["proposal_id"]),
        )

    audit.record(conn, actor=reviewer, action=f"FLEET_ITEM_{decision}",
                 target_table="fleet_proposal_items", target_id=item_id,
                 matter_id=proposal["matter_id"],
                 summary=f"{item['item_type']} in {proposal['job_id']}",
                 payload={"applied_record_id": applied_id, "note": note})

    return {"item_id": item_id, "decision": decision, "applied_record_id": applied_id,
            "remaining_pending": remaining}


def issues_before_and_after(conn: sqlite3.Connection) -> dict[str, Any]:
    """Snapshot used to prove that no issue disappeared during Fleet review."""
    rows = conn.execute(
        "SELECT issue_key, title, status FROM issues ORDER BY id").fetchall()
    return {
        "count": len(rows),
        "keys": [r["issue_key"] for r in rows],
        "statuses": {r["issue_key"]: r["status"] for r in rows},
    }
