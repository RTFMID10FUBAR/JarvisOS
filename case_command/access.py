"""Access-barrier log: what prevented a filing, recorded as it happened.

A tribunal that requires hand delivery or mail requires printing, which requires
electricity. When the loss of electricity is the subject of the proceeding, the
filing requirement and the injury are the same fact.

That is prejudice to the right to be heard, and it is what issues PSC-020 (loss
of electric service during the appeal perfection period) and PSC-021 (actual
prejudice to judicial review) already exist to carry. What those issues lack is
proof, and proof of this kind has to be recorded when it happens.

**This module invents nothing.** It provides the structure and the linking. Every
incident is entered by Jacob. `summarize` counts and arranges what was entered;
it does not characterize, argue, or conclude.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from . import audit
from .db import insert, utcnow

BARRIER_TYPES = (
    "NO_ELECTRICITY", "NO_PRINTER", "NO_INTERNET", "NO_TRANSPORT",
    "NO_FUNDS", "DISABILITY", "HEALTH", "NO_NOTICE", "OTHER",
)

BARRIER_LABELS = {
    "NO_ELECTRICITY": "Electric service was off",
    "NO_PRINTER": "No working printer or supplies",
    "NO_INTERNET": "No connectivity to e-file or email",
    "NO_TRANSPORT": "Could not travel to file, serve, or appear",
    "NO_FUNDS": "Could not pay postage, copying, or fees",
    "DISABILITY": "Disability-related barrier",
    "HEALTH": "Medical event prevented action",
    "NO_NOTICE": "Notice not received in time to act",
    "OTHER": "Other barrier",
}

#: Issues an access barrier bears on. These are the preloaded PSC/AEP issues
#: about service loss during the appeal period and prejudice to review — the
#: places where this evidence actually does work.
PREJUDICE_ISSUE_KEYS = ("PSC-020", "PSC-021")


def log_barrier(conn: sqlite3.Connection, *, incident_date: str, barrier_type: str,
                what_was_blocked: str, matter_id: int | None = None,
                deadline_affected: str | None = None, deadline_date: str | None = None,
                workaround_attempted: str | None = None,
                workaround_result: str | None = None,
                hours_lost: float | None = None, cost_incurred: float | None = None,
                reported_to_tribunal: bool = False, how_reported: str | None = None,
                reported_date: str | None = None,
                evidence_document_id: int | None = None,
                notes: str | None = None, actor: str = "jacob") -> dict[str, Any]:
    """Record one incident, and link it to the issues it bears on.

    The entry is stored as UNKNOWN verification. It becomes VERIFIED only when a
    supporting document (a shutoff notice, a receipt, a failed-filing
    confirmation) is attached — the same rule that governs every other fact.
    """
    barrier_type = barrier_type.upper()
    if barrier_type not in BARRIER_TYPES:
        raise ValueError(f"{barrier_type!r} is not a barrier type. "
                         f"Allowed: {', '.join(BARRIER_TYPES)}")
    if not what_was_blocked or not what_was_blocked.strip():
        raise ValueError("what_was_blocked is required: a general assertion of hardship "
                         "is not evidence, a specific blocked filing is")

    title = f"{incident_date or 'undated'}: {BARRIER_LABELS[barrier_type]}"

    barrier_id = insert(conn, "access_barriers", {
        "matter_id": matter_id,
        "title": title,
        "incident_date": incident_date,
        "barrier_type": barrier_type,
        "what_was_blocked": what_was_blocked.strip(),
        "deadline_affected": deadline_affected,
        "deadline_date": deadline_date,
        "workaround_attempted": workaround_attempted,
        "workaround_result": workaround_result,
        "hours_lost": hours_lost,
        "cost_incurred": cost_incurred,
        "reported_to_tribunal": 1 if reported_to_tribunal else 0,
        "how_reported": how_reported,
        "reported_date": reported_date,
        "evidence_document_id": evidence_document_id,
        # Supporting proof is what makes this verified. Without it the entry is
        # a contemporaneous statement, which is worth recording and worth
        # labelling honestly.
        "verification_status": "VERIFIED_SECONDARY" if evidence_document_id else "UNKNOWN",
        "source_document_id": evidence_document_id,
        "created_by": actor,
        "notes": notes,
    })

    linked = _link_to_prejudice_issues(conn, barrier_id, matter_id)

    audit.record(conn, actor=actor, action="ACCESS_BARRIER_LOGGED",
                 target_table="access_barriers", target_id=barrier_id,
                 matter_id=matter_id, summary=title,
                 payload={"barrier_type": barrier_type,
                          "what_was_blocked": what_was_blocked,
                          "linked_issues": linked,
                          "has_supporting_document": bool(evidence_document_id)})

    return {
        "barrier_id": barrier_id,
        "title": title,
        "linked_issues": linked,
        "verification_status": "VERIFIED_SECONDARY" if evidence_document_id else "UNKNOWN",
        "next_step": (
            "Attach a supporting document (shutoff notice, receipt, failed-filing "
            "confirmation) to move this from UNKNOWN to verified."
            if not evidence_document_id else
            "Supporting document attached."
        ),
    }


def _link_to_prejudice_issues(conn: sqlite3.Connection, barrier_id: int,
                              matter_id: int | None) -> list[str]:
    """Link the barrier to the issues about service loss and prejudice."""
    linked: list[str] = []
    for key in PREJUDICE_ISSUE_KEYS:
        row = conn.execute("SELECT id, issue_key FROM issues WHERE issue_key=?",
                           (key,)).fetchone()
        if row is None:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO issue_links (issue_id, linked_type, linked_id, role, "
            "approved, created_by, notes) VALUES (?,?,?,?,?,?,?)",
            (row["id"], "access_barrier", barrier_id, "supports", 0, "access-log",
             "Access barrier bearing on prejudice to the right to be heard."),
        )
        linked.append(row["issue_key"])
    return linked


def attach_evidence(conn: sqlite3.Connection, barrier_id: int, document_id: int, *,
                    locator: str | None = None, actor: str = "jacob") -> dict[str, Any]:
    """Attach supporting proof, upgrading the entry's verification status."""
    row = conn.execute("SELECT * FROM access_barriers WHERE id=?", (barrier_id,)).fetchone()
    if row is None:
        raise ValueError(f"no access barrier {barrier_id}")
    document = conn.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
    if document is None:
        raise ValueError(f"no document {document_id}")

    conn.execute(
        "UPDATE access_barriers SET evidence_document_id=?, source_document_id=?, "
        "source_page_or_paragraph=?, verification_status='VERIFIED_SECONDARY', "
        "last_reviewed_by=?, updated_at=? WHERE id=?",
        (document_id, document_id, locator, actor, utcnow(), barrier_id))

    audit.record(conn, actor=actor, action="ACCESS_BARRIER_EVIDENCE_ATTACHED",
                 target_table="access_barriers", target_id=barrier_id,
                 matter_id=row["matter_id"], summary=f"{row['title']} <- {document['doc_uid']}")

    return {"barrier_id": barrier_id, "document": document["doc_uid"],
            "verification_status": "VERIFIED_SECONDARY"}


def list_barriers(conn: sqlite3.Connection, matter_id: int | None = None,
                  barrier_type: str | None = None) -> list[dict[str, Any]]:
    sql = ["""
        SELECT b.*, m.slug AS matter_slug, d.doc_uid AS evidence_uid
        FROM access_barriers b
        LEFT JOIN matters m ON m.id = b.matter_id
        LEFT JOIN documents d ON d.id = b.evidence_document_id
        WHERE b.status='ACTIVE'
    """]
    params: list[Any] = []
    if matter_id is not None:
        sql.append("AND b.matter_id=?")
        params.append(matter_id)
    if barrier_type:
        sql.append("AND b.barrier_type=?")
        params.append(barrier_type.upper())
    sql.append("ORDER BY COALESCE(b.incident_date, b.created_at)")
    return [dict(r) for r in conn.execute("\n".join(sql), params)]


def summarize(conn: sqlite3.Connection, matter_id: int | None = None) -> dict[str, Any]:
    """Arrange the log into countable form.

    This counts and groups. It does not characterize the incidents, draw a legal
    conclusion, or assert that prejudice occurred — those are arguments, and this
    system does not make arguments. It supplies the record they would rest on.
    """
    barriers = list_barriers(conn, matter_id)
    if not barriers:
        return {
            "count": 0,
            "note": ("No access barriers recorded. If a filing was ever prevented or "
                     "delayed, log it — a contemporaneous entry carries weight that a "
                     "later reconstruction does not."),
        }

    by_type: dict[str, int] = {}
    for barrier in barriers:
        by_type[barrier["barrier_type"]] = by_type.get(barrier["barrier_type"], 0) + 1

    dated = [b["incident_date"] for b in barriers if b["incident_date"]]
    with_deadline = [b for b in barriers if b["deadline_affected"]]
    with_evidence = [b for b in barriers if b["evidence_document_id"]]
    reported = [b for b in barriers if b["reported_to_tribunal"]]

    return {
        "count": len(barriers),
        "by_type": by_type,
        "date_range": (f"{min(dated)} to {max(dated)}" if dated else None),
        "undated_entries": len(barriers) - len(dated),
        "deadlines_affected": len(with_deadline),
        "deadline_list": [
            {"date": b["deadline_date"], "deadline": b["deadline_affected"],
             "blocked": b["what_was_blocked"], "barrier": b["barrier_type"]}
            for b in with_deadline
        ],
        "total_hours_lost": sum(b["hours_lost"] or 0 for b in barriers),
        "total_cost_incurred": sum(b["cost_incurred"] or 0 for b in barriers),
        "with_supporting_document": len(with_evidence),
        "without_supporting_document": len(barriers) - len(with_evidence),
        "reported_to_tribunal": len(reported),
        "not_reported_to_tribunal": len(barriers) - len(reported),
        "gaps": _gaps(barriers, with_evidence, reported),
        "linked_issues": list(PREJUDICE_ISSUE_KEYS),
    }


def _gaps(barriers: list[dict[str, Any]], with_evidence: list[dict[str, Any]],
          reported: list[dict[str, Any]]) -> list[str]:
    """What would weaken this record if it were relied on tomorrow."""
    gaps: list[str] = []
    missing_proof = len(barriers) - len(with_evidence)
    if missing_proof:
        gaps.append(
            f"{missing_proof} of {len(barriers)} entries have no supporting document. "
            "Each is a contemporaneous statement, not corroborated proof.")
    unreported = len(barriers) - len(reported)
    if unreported:
        gaps.append(
            f"{unreported} of {len(barriers)} entries were never reported to the tribunal. "
            "A barrier raised for the first time on appeal is harder to rely on than one "
            "the record already shows.")
    undated = sum(1 for b in barriers if not b["incident_date"])
    if undated:
        gaps.append(f"{undated} entries have no date. An undated incident cannot be tied "
                    "to a deadline.")
    no_deadline = sum(1 for b in barriers if not b["deadline_affected"])
    if no_deadline:
        gaps.append(f"{no_deadline} entries name no affected deadline. A barrier that "
                    "blocked nothing specific is weaker than one that missed a date.")
    return gaps


def format_log(conn: sqlite3.Connection, matter_id: int | None = None) -> str:
    """Plain-text chronological log for the terminal."""
    barriers = list_barriers(conn, matter_id)
    summary = summarize(conn, matter_id)

    if not barriers:
        return summary["note"]

    lines = [
        f"{summary['count']} access barrier(s) recorded"
        + (f" · {summary['date_range']}" if summary["date_range"] else ""),
        f"{summary['deadlines_affected']} affected a deadline · "
        f"{summary['with_supporting_document']} have supporting documents · "
        f"{summary['reported_to_tribunal']} were reported to the tribunal",
        "",
    ]
    for barrier in barriers:
        lines.append(f"{barrier['incident_date'] or '(no date)':<12} "
                     f"{barrier['barrier_type']:<16} "
                     f"[{barrier['verification_status']}]")
        lines.append(f"             blocked: {barrier['what_was_blocked']}")
        if barrier["deadline_affected"]:
            lines.append(f"             deadline: {barrier['deadline_affected']}"
                         + (f" (due {barrier['deadline_date']})"
                            if barrier["deadline_date"] else ""))
        if barrier["workaround_attempted"]:
            lines.append(f"             tried: {barrier['workaround_attempted']}"
                         + (f" -> {barrier['workaround_result']}"
                            if barrier["workaround_result"] else ""))
        if barrier["evidence_uid"]:
            lines.append(f"             proof: {barrier['evidence_uid']}")
        else:
            lines.append("             proof: NONE ATTACHED")
        lines.append("")

    if summary["gaps"]:
        lines.append("Gaps in this record:")
        lines.extend(f"  - {gap}" for gap in summary["gaps"])
    lines.append("")
    lines.append(f"Linked to issues: {', '.join(summary['linked_issues'])}")
    return "\n".join(lines)
