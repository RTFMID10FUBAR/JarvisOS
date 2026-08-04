"""Data assembly for the Case Command views.

Each function returns plain dictionaries so the same data drives the web UI, the
CLI, and the tests. Nothing here mutates the record.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from typing import Any

from . import checks, preservation as pres
from .db import CONFIRMED_FILING_STATUSES


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(sql, params)]


def _one(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> dict[str, Any] | None:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def days_until(due: str | None) -> int | None:
    if not due:
        return None
    try:
        year, month, day = (int(p) for p in due.split("-")[:3])
        return (date(year, month, day) - datetime.now(timezone.utc).date()).days
    except (ValueError, AttributeError):
        return None


def list_matters(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    matters = _rows(conn, """
        SELECT m.*,
               (SELECT COUNT(*) FROM issues i WHERE i.matter_id=m.id) AS issue_count,
               (SELECT COUNT(*) FROM issues i WHERE i.matter_id=m.id AND i.status='ACTIVE')
                   AS active_issue_count,
               (SELECT COUNT(*) FROM documents d WHERE d.matter_id=m.id AND d.status='ACTIVE')
                   AS document_count
        FROM matters m WHERE m.status='ACTIVE' ORDER BY m.folder, m.id
    """)
    return matters


# ---------------------------------------------------------------------------
# Command Dashboard
# ---------------------------------------------------------------------------
def dashboard(conn: sqlite3.Connection) -> dict[str, Any]:
    deadlines = pres.upcoming_deadlines(conn, limit=25)
    for item in deadlines:
        item["days_until"] = days_until(item.get("due_date"))

    # An already-passed date is reported separately. Showing it as "the next
    # deadline" would be actively misleading.
    overdue = [d for d in deadlines if (d["days_until"] or 0) < 0]
    upcoming = [d for d in deadlines if (d["days_until"] or 0) >= 0]
    next_deadline = upcoming[0] if upcoming else None
    next_hearing = _one(conn, """
        SELECT e.*, m.slug AS matter_slug FROM events e
        LEFT JOIN matters m ON m.id=e.matter_id
        WHERE e.event_type IN ('HEARING','TRIAL') AND e.status='ACTIVE'
          AND e.event_date >= ? ORDER BY e.event_date LIMIT 1
    """, (today(),))

    urgent = [d for d in upcoming
              if d["days_until"] is not None and d["days_until"] <= 7]

    return {
        "next_deadline": next_deadline,
        "overdue_deadlines": overdue,
        "next_hearing": next_hearing,
        "urgent_filings": urgent,
        "unresolved_motions": _rows(conn, """
            SELECT mo.*, m.slug AS matter_slug FROM motions mo
            LEFT JOIN matters m ON m.id=mo.matter_id
            WHERE mo.ruled_on=0 AND mo.status='ACTIVE'
            ORDER BY mo.threshold_motion DESC, mo.filed_date
        """),
        "missing_rulings": _rows(conn, """
            SELECT p.*, i.issue_key, i.title AS issue_title, m.slug AS matter_slug
            FROM preservation_items p
            LEFT JOIN issues i ON i.id=p.issue_id
            LEFT JOIN matters m ON m.id=p.matter_id
            WHERE p.ruling_requested=1 AND p.ruling_issued=0 AND p.status='ACTIVE'
        """),
        "missing_evidence": _rows(conn, """
            SELECT i.issue_key, i.title, i.missing_proof, m.slug AS matter_slug
            FROM issues i LEFT JOIN matters m ON m.id=i.matter_id
            WHERE (i.status='MISSING_PROOF' OR i.missing_proof IS NOT NULL)
              AND i.status<>'DECIDED'
        """),
        "unverified_facts": _rows(conn, """
            SELECT f.*, m.slug AS matter_slug FROM facts f
            LEFT JOIN matters m ON m.id=f.matter_id
            WHERE f.status='ACTIVE' AND f.verification_status IN
                  ('UNKNOWN','MISSING_SOURCE','INFERENCE','PARTIALLY_VERIFIED')
            ORDER BY f.created_at DESC LIMIT 50
        """),
        "waiver_risks": [
            row for row in _rows(conn, """
                SELECT p.*, i.issue_key, i.title AS issue_title, m.slug AS matter_slug
                FROM preservation_items p
                LEFT JOIN issues i ON i.id=p.issue_id
                LEFT JOIN matters m ON m.id=p.matter_id
                WHERE p.status='ACTIVE' AND (
                      (p.ignored=1 AND p.exception_filed=0)
                   OR (p.exception_required=1 AND p.exception_filed=0)
                   OR (p.ruling_requested=1 AND p.ruling_issued=0))
            """)
        ],
        "open_contradictions": _rows(conn, """
            SELECT c.*, m.slug AS matter_slug FROM contradictions c
            LEFT JOIN matters m ON m.id=c.matter_id
            WHERE c.resolved=0 AND c.status='ACTIVE'
        """),
        "strongest_argument": _one(conn, """
            SELECT i.*, m.slug AS matter_slug FROM issues i
            LEFT JOIN matters m ON m.id=i.matter_id
            WHERE i.status='ACTIVE' AND i.verification_status IN
                  ('VERIFIED_PRIMARY','VERIFIED_SECONDARY')
            ORDER BY CASE i.risk_rating WHEN 'LOW' THEN 0 WHEN 'MEDIUM' THEN 1 ELSE 2 END,
                     i.issue_key LIMIT 1
        """),
        "strongest_defense": _one(conn, """
            SELECT d.*, m.slug AS matter_slug FROM defenses d
            LEFT JOIN matters m ON m.id=d.matter_id
            WHERE d.status='ACTIVE'
            ORDER BY CASE d.strength WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 ELSE 2 END LIMIT 1
        """),
        "open_approvals": _rows(conn,
            "SELECT * FROM approvals WHERE state='OPEN' ORDER BY id DESC LIMIT 25"),
        "fleet_pending": _rows(conn, """
            SELECT p.job_id, p.job_type, p.confidence, p.created_at,
                   COUNT(i.id) AS pending_items
            FROM fleet_proposals p
            JOIN fleet_proposal_items i ON i.proposal_id=p.id AND i.decision='PENDING'
            GROUP BY p.id ORDER BY p.created_at DESC
        """),
        "access_barriers": _access_barrier_summary(conn),
        "coverage": _coverage(conn),
        "todays_actions": _todays_actions(conn, deadlines),
        "matters": list_matters(conn),
        "counts": {
            "documents": conn.execute(
                "SELECT COUNT(*) n FROM documents WHERE status='ACTIVE'").fetchone()["n"],
            "issues": conn.execute("SELECT COUNT(*) n FROM issues").fetchone()["n"],
            "unknowns": conn.execute(
                "SELECT COUNT(*) n FROM unknowns WHERE resolved=0 AND status='ACTIVE'"
            ).fetchone()["n"],
        },
    }


def _coverage(conn: sqlite3.Connection) -> dict[str, Any]:
    """Record coverage as counts. Never a single "health" percentage."""
    from . import atlas

    return atlas.coverage(conn)


def _access_barrier_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    """Barriers that prevented a filing — evidence of prejudice, not a complaint."""
    from . import access

    return access.summarize(conn)


def _todays_actions(conn: sqlite3.Connection, deadlines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """What actually needs doing, ordered by consequence."""
    actions: list[dict[str, Any]] = []

    for item in deadlines:
        days = item.get("days_until")
        if days is None:
            continue
        if days < 0:
            # An expired deadline is not "urgent, act now" — it is a date that
            # has already passed, and it must never read like an upcoming one.
            actions.append({
                "priority": "MISSED",
                "action": (f"{item['title']} — date passed {item['due_date']} "
                           f"({abs(days)} day(s) ago)"),
                "why": ("This date has already passed. Confirm whether it was met, whether "
                        "the interval was computed correctly, and whether relief from the "
                        "deadline is available."),
                "link": f"/preservation?matter_id={item.get('matter_id') or ''}",
            })
        elif days <= 14:
            actions.append({
                "priority": "URGENT" if days <= 3 else "SOON",
                "action": f"{item['title']} — due {item['due_date']} ({days} day(s))",
                "why": "Deadline. The interval is provisional; confirm the governing rule.",
                "link": f"/preservation?matter_id={item.get('matter_id') or ''}",
            })

    for row in conn.execute("""
        SELECT p.*, i.issue_key FROM preservation_items p
        LEFT JOIN issues i ON i.id=p.issue_id
        WHERE p.status='ACTIVE' AND p.ignored=1 AND p.exception_filed=0
    """):
        actions.append({
            "priority": "URGENT",
            "action": f"{row['issue_key'] or row['title']}: motion ignored, no exception filed",
            "why": "An unruled request can be treated as abandoned without an exception.",
            "link": f"/preservation?matter_id={row['matter_id']}",
        })

    open_approvals = conn.execute(
        "SELECT COUNT(*) n FROM approvals WHERE state='OPEN'").fetchone()["n"]
    if open_approvals:
        actions.append({
            "priority": "NORMAL",
            "action": f"Review {open_approvals} pending decision(s)",
            "why": "New documents are waiting on a matter assignment or filing status.",
            "link": "/approvals",
        })

    pending_fleet = conn.execute(
        "SELECT COUNT(*) n FROM fleet_proposal_items WHERE decision='PENDING'").fetchone()["n"]
    if pending_fleet:
        actions.append({
            "priority": "NORMAL",
            "action": f"Review {pending_fleet} Fleet proposal item(s)",
            "why": "Fleet output stays outside the record until approved.",
            "link": "/fleet",
        })

    order = {"MISSED": 0, "URGENT": 1, "SOON": 2, "NORMAL": 3}
    actions.sort(key=lambda a: order.get(a["priority"], 4))
    return actions


# ---------------------------------------------------------------------------
# Matter View
# ---------------------------------------------------------------------------
def matter_view(conn: sqlite3.Connection, matter_id: int) -> dict[str, Any]:
    matter = _one(conn, "SELECT * FROM matters WHERE id=?", (matter_id,))
    if matter is None:
        return {}

    return {
        "matter": matter,
        "related": _rows(conn, """
            SELECT l.relationship, l.notes, m.* FROM matter_links l
            JOIN matters m ON m.id=l.related_matter_id WHERE l.matter_id=?
            UNION
            SELECT l.relationship, l.notes, m.* FROM matter_links l
            JOIN matters m ON m.id=l.matter_id WHERE l.related_matter_id=?
        """, (matter_id, matter_id)),
        "parties": _rows(conn,
            "SELECT * FROM actors WHERE matter_id=? AND status='ACTIVE'", (matter_id,)),
        "counsel": _rows(conn,
            "SELECT * FROM counsel WHERE matter_id=? AND status='ACTIVE'", (matter_id,)),
        "judges": _rows(conn,
            "SELECT * FROM judges WHERE matter_id=? AND status='ACTIVE'", (matter_id,)),
        "aljs": _rows(conn,
            "SELECT * FROM aljs WHERE matter_id=? AND status='ACTIVE'", (matter_id,)),
        "filings": _rows(conn, """
            SELECT f.*, d.doc_uid FROM filings f
            LEFT JOIN documents d ON d.id=f.document_id
            WHERE f.matter_id=? AND f.status='ACTIVE'
            ORDER BY COALESCE(f.filed_date, f.created_at) DESC
        """, (matter_id,)),
        "orders": _rows(conn,
            "SELECT * FROM orders WHERE matter_id=? AND status='ACTIVE' "
            "ORDER BY entered_date DESC", (matter_id,)),
        "timeline": timeline(conn, matter_id=matter_id)["events"][:50],
        "issues": _rows(conn,
            "SELECT * FROM issues WHERE matter_id=? ORDER BY issue_key", (matter_id,)),
        "claims": _rows(conn,
            "SELECT * FROM claims WHERE matter_id=? AND status='ACTIVE'", (matter_id,)),
        "defenses": _rows(conn,
            "SELECT * FROM defenses WHERE matter_id=? AND status='ACTIVE'", (matter_id,)),
        "evidence": _rows(conn,
            "SELECT * FROM evidence WHERE matter_id=? AND status='ACTIVE'", (matter_id,)),
        "deadlines": pres.upcoming_deadlines(conn, matter_id),
        "relief": _rows(conn,
            "SELECT * FROM relief WHERE matter_id=? AND status='ACTIVE'", (matter_id,)),
        "preservation_summary": _preservation_summary(conn, matter_id),
        "documents": _rows(conn, """
            SELECT DISTINCT d.* FROM documents d
            LEFT JOIN document_matter_links l ON l.document_id=d.id
            WHERE (d.matter_id=? OR l.matter_id=?) AND d.status='ACTIVE'
            ORDER BY COALESCE(d.document_date, d.created_at) DESC LIMIT 200
        """, (matter_id, matter_id)),
    }


def _preservation_summary(conn: sqlite3.Connection, matter_id: int) -> dict[str, Any]:
    matrix = pres.preservation_matrix(conn, matter_id)
    at_risk = [row for row in matrix if row["at_risk"]]
    return {
        "total": len(matrix),
        "at_risk": len(at_risk),
        "risks": at_risk[:10],
        "status": "AT_RISK" if at_risk else "OK",
    }


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------
def timeline(conn: sqlite3.Connection, *, matter_id: int | None = None,
             start: str | None = None, end: str | None = None,
             actor: str | None = None, filing_type: str | None = None,
             boundary: str | None = None, verification: str | None = None,
             disputed: bool | None = None,
             significance: str | None = None) -> dict[str, Any]:
    """The timeline with every filter the specification requires."""
    sql = ["""
        SELECT e.*, m.slug AS matter_slug, m.boundary_date, d.doc_uid
        FROM events e
        LEFT JOIN matters m ON m.id=e.matter_id
        LEFT JOIN documents d ON d.id=e.source_document_id
        WHERE e.status='ACTIVE'
    """]
    params: list[Any] = []

    if matter_id is not None:
        sql.append("AND e.matter_id=?")
        params.append(matter_id)
    if start:
        sql.append("AND e.event_date >= ?")
        params.append(start)
    if end:
        sql.append("AND e.event_date <= ?")
        params.append(end)
    if actor:
        sql.append("AND (e.actor_name LIKE ? OR e.title LIKE ?)")
        params.extend([f"%{actor}%", f"%{actor}%"])
    if filing_type:
        sql.append("AND e.event_type=?")
        params.append(filing_type)
    if boundary:
        sql.append("AND e.boundary_classification=?")
        params.append(boundary)
    if verification:
        sql.append("AND e.verification_status=?")
        params.append(verification)
    if disputed is not None:
        sql.append("AND e.disputed=?")
        params.append(1 if disputed else 0)
    if significance:
        sql.append("AND e.legal_significance LIKE ?")
        params.append(f"%{significance}%")

    sql.append("ORDER BY COALESCE(e.event_date, e.created_at), e.id")
    events = _rows(conn, "\n".join(sql), tuple(params))

    # Mark each event relative to its matter's boundary date so pre/post order
    # filtering is meaningful in the UI.
    for event in events:
        boundary_date = event.get("boundary_date")
        event_date = event.get("event_date")
        if boundary_date and event_date:
            event["relative_to_order"] = "POST_ORDER" if event_date > boundary_date else "PRE_ORDER"
        else:
            event["relative_to_order"] = "UNKNOWN"

    return {
        "events": events,
        "filters": {
            "matter_id": matter_id, "start": start, "end": end, "actor": actor,
            "filing_type": filing_type, "boundary": boundary,
            "verification": verification, "disputed": disputed,
            "significance": significance,
        },
        "available": {
            "event_types": [r["event_type"] for r in _rows(conn,
                "SELECT DISTINCT event_type FROM events WHERE event_type IS NOT NULL")],
            "boundary_classifications": [r["boundary_classification"] for r in _rows(conn,
                "SELECT DISTINCT boundary_classification FROM events")],
            "actors": [r["actor_name"] for r in _rows(conn,
                "SELECT DISTINCT actor_name FROM events WHERE actor_name IS NOT NULL")],
        },
        "count": len(events),
    }


# ---------------------------------------------------------------------------
# Filing and Order Comparison
# ---------------------------------------------------------------------------
COMPARISON_MODES = {
    "complaint_answer": ("Complaint", "Answer"),
    "motion_order": ("Motion", "Order"),
    "relief_disposition": ("Requested relief", "Disposition"),
    "statement_contradiction": ("Party statement", "Later contradiction"),
    "proposed_entered": ("Proposed order", "Entered order"),
}


def _document_text(conn: sqlite3.Connection, document_id: int | None,
                   limit: int = 40_000) -> str:
    if not document_id:
        return ""
    row = conn.execute("SELECT text_path FROM documents WHERE id=?", (document_id,)).fetchone()
    if not row or not row["text_path"]:
        return ""
    from pathlib import Path

    path = Path(row["text_path"])
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def comparison(conn: sqlite3.Connection, *, mode: str, left_id: int | None = None,
               right_id: int | None = None, matter_id: int | None = None) -> dict[str, Any]:
    """Side-by-side review of two documents or two record positions."""
    left_label, right_label = COMPARISON_MODES.get(mode, ("Left", "Right"))

    left = _one(conn, "SELECT * FROM documents WHERE id=?", (left_id,)) if left_id else None
    right = _one(conn, "SELECT * FROM documents WHERE id=?", (right_id,)) if right_id else None

    left_text = _document_text(conn, left_id)
    right_text = _document_text(conn, right_id)

    differences: list[dict[str, Any]] = []
    if left_text and right_text:
        import difflib

        left_lines = [line.strip() for line in left_text.splitlines() if line.strip()]
        right_lines = [line.strip() for line in right_text.splitlines() if line.strip()]
        matcher = difflib.SequenceMatcher(None, left_lines, right_lines, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            differences.append({
                "type": tag,
                "left": left_lines[i1:i2][:8],
                "right": right_lines[j1:j2][:8],
            })

    if mode == "relief_disposition" and matter_id:
        rows = _rows(conn, """
            SELECT r.title, r.relief_type, r.disposition, r.granted, r.verification_status
            FROM relief r WHERE r.matter_id=? AND r.status='ACTIVE'
        """, (matter_id,))
        for row in rows:
            differences.append({
                "type": "relief",
                "left": [row["title"]],
                "right": [row["disposition"] or "NO DISPOSITION RECORDED"],
                "granted": row["granted"],
            })

    return {
        "mode": mode,
        "left_label": left_label,
        "right_label": right_label,
        "left": left,
        "right": right,
        "left_text": left_text[:20_000],
        "right_text": right_text[:20_000],
        "differences": differences[:200],
        "difference_count": len(differences),
        "candidates": _rows(conn, """
            SELECT id, doc_uid, title, document_date, folder FROM documents
            WHERE status='ACTIVE' """ + ("AND matter_id=?" if matter_id else "") + """
            ORDER BY COALESCE(document_date, created_at) DESC LIMIT 200
        """, (matter_id,) if matter_id else ()),
        "modes": COMPARISON_MODES,
    }


# ---------------------------------------------------------------------------
# Issue Matrix
# ---------------------------------------------------------------------------
def issue_matrix(conn: sqlite3.Connection, matter_id: int | None = None) -> dict[str, Any]:
    """Every issue with every column the specification requires.

    A blank column is displayed as an explicit gap, never as an implied answer.
    """
    sql = """
        SELECT i.*, m.slug AS matter_slug, m.title AS matter_title
        FROM issues i LEFT JOIN matters m ON m.id=i.matter_id
    """
    params: tuple = ()
    if matter_id is not None:
        sql += " WHERE i.matter_id=?"
        params = (matter_id,)
    sql += " ORDER BY i.issue_key, i.id"

    matrix: list[dict[str, Any]] = []
    for issue in _rows(conn, sql, params):
        issue_id = issue["id"]

        verified_facts = _rows(conn, """
            SELECT f.* FROM facts f
            JOIN issue_links l ON l.linked_id=f.id AND l.linked_type='fact'
            WHERE l.issue_id=? AND f.verification_status IN
                  ('VERIFIED_PRIMARY','VERIFIED_SECONDARY') AND f.status='ACTIVE'
        """, (issue_id,))
        disputed_facts = _rows(conn, """
            SELECT f.* FROM facts f
            JOIN issue_links l ON l.linked_id=f.id AND l.linked_type='fact'
            WHERE l.issue_id=? AND (f.disputed=1 OR f.verification_status='DISPUTED')
              AND f.status='ACTIVE'
        """, (issue_id,))
        authorities = _rows(conn, """
            SELECT a.* FROM authorities a
            JOIN issue_links l ON l.linked_id=a.id AND l.linked_type='authority'
            WHERE l.issue_id=? AND a.status='ACTIVE'
        """, (issue_id,))
        evidence = _rows(conn, """
            SELECT e.* FROM evidence e
            JOIN issue_links l ON l.linked_id=e.id AND l.linked_type='evidence'
            WHERE l.issue_id=? AND e.status='ACTIVE'
        """, (issue_id,))
        defenses = _rows(conn,
            "SELECT * FROM defenses WHERE issue_id=? AND status='ACTIVE'", (issue_id,))
        preservation = _one(conn,
            "SELECT * FROM preservation_items WHERE issue_id=? AND status='ACTIVE' LIMIT 1",
            (issue_id,))
        open_unknowns = _rows(conn,
            "SELECT * FROM unknowns WHERE issue_id=? AND resolved=0 AND status='ACTIVE'",
            (issue_id,))

        gaps: list[str] = []
        if not issue["legal_element"]:
            gaps.append("legal element")
        if not verified_facts:
            gaps.append("verified facts")
        if not authorities:
            gaps.append("authority")
        if not evidence:
            gaps.append("evidence")
        if not defenses:
            gaps.append("opponent defense")
        if not issue["best_reply"]:
            gaps.append("best reply")
        if not issue["requested_finding"]:
            gaps.append("requested finding")
        if not issue["requested_relief"]:
            gaps.append("requested relief")
        if not issue["appeal_standard"]:
            gaps.append("appeal standard")
        if not preservation:
            gaps.append("preservation record")

        matrix.append({
            "issue": issue,
            "legal_element": issue["legal_element"],
            "verified_facts": verified_facts,
            "disputed_facts": disputed_facts,
            "inference": issue["inference"],
            "authority": authorities,
            "evidence": evidence,
            "opponent_defense": defenses or ([{"title": issue["opponent_defense"]}]
                                             if issue["opponent_defense"] else []),
            "best_reply": issue["best_reply"],
            "missing_proof": issue["missing_proof"] or (
                "; ".join(u["title"] for u in open_unknowns) if open_unknowns else None),
            "requested_finding": issue["requested_finding"],
            "requested_relief": issue["requested_relief"],
            "preservation": preservation,
            "preservation_status": _preservation_label(preservation),
            "appeal_standard": issue["appeal_standard"],
            "risk_rating": issue["risk_rating"] or _implied_risk(gaps),
            "gaps": gaps,
            "unknowns": open_unknowns,
        })

    return {
        "matrix": matrix,
        "matter_id": matter_id,
        "count": len(matrix),
        "matters": list_matters(conn),
        "complete": sum(1 for row in matrix if not row["gaps"]),
    }


def _preservation_label(preservation: dict[str, Any] | None) -> str:
    if not preservation:
        return "NO RECORD"
    if preservation.get("ignored") and not preservation.get("exception_filed"):
        return "AT RISK — ignored, no exception"
    if preservation.get("exception_required") and not preservation.get("exception_filed"):
        return "AT RISK — exception due"
    if preservation.get("ruling_requested") and not preservation.get("ruling_issued"):
        return "AT RISK — no ruling"
    if preservation.get("raised"):
        return "RAISED"
    return "NOT RAISED"


def _implied_risk(gaps: list[str]) -> str:
    if len(gaps) >= 6:
        return "HIGH (implied by gaps)"
    if len(gaps) >= 3:
        return "MEDIUM (implied by gaps)"
    return "LOW (implied by gaps)"


# ---------------------------------------------------------------------------
# Hearing Mode
# ---------------------------------------------------------------------------
def hearing_mode(conn: sqlite3.Connection, matter_id: int,
                 hearing_date: str | None = None) -> dict[str, Any]:
    """Everything needed at the podium, scoped to the noticed hearing."""
    matter = _one(conn, "SELECT * FROM matters WHERE id=?", (matter_id,))
    if matter is None:
        return {}

    in_scope = _rows(conn, """
        SELECT * FROM issues WHERE matter_id=? AND status='ACTIVE'
          AND (hearing_scope IS NULL OR hearing_scope <> 'OUTSIDE_CURRENT_HEARING')
        ORDER BY issue_key
    """, (matter_id,))
    out_of_scope = _rows(conn, """
        SELECT * FROM issues WHERE matter_id=?
          AND (status='OUTSIDE_CURRENT_HEARING' OR hearing_scope='OUTSIDE_CURRENT_HEARING')
        ORDER BY issue_key
    """, (matter_id,))

    rules = _rows(conn, "SELECT * FROM rules WHERE matter_id=? AND status='ACTIVE'", (matter_id,))
    rule_elements: list[dict[str, Any]] = []
    for rule in rules:
        elements = []
        if rule.get("elements"):
            try:
                elements = json.loads(rule["elements"])
            except (json.JSONDecodeError, TypeError):
                elements = [rule["elements"]]
        rule_elements.append({"rule": rule, "elements": elements})

    exhibits = _rows(conn, """
        SELECT e.*, d.doc_uid, d.storage_path FROM evidence e
        LEFT JOIN documents d ON d.id=e.document_id
        WHERE e.matter_id=? AND e.status='ACTIVE'
        ORDER BY CASE WHEN e.exhibit_number IS NULL THEN 1 ELSE 0 END, e.exhibit_number
    """, (matter_id,))

    # Source-record questions: for each issue whose proof rests on the opponent's
    # own documents, the question is where that assertion comes from.
    source_questions: list[dict[str, Any]] = []
    for issue in in_scope:
        source_questions.append({
            "issue_key": issue["issue_key"],
            "issue": issue["title"],
            "questions": [
                f"What document in the record establishes {issue['title']}?",
                "Who prepared it, and when?",
                "Is that the complete record, or an excerpt?",
                "What was omitted from the chronology provided?",
            ],
        })

    boundary = matter.get("boundary_date")
    scope_statement = (
        f"This hearing concerns {matter['title']}"
        + (f" ({matter['case_number']})" if matter.get("case_number") else "")
        + ". "
        + (f"Conduct on or before {boundary} was addressed in the prior proceeding. "
           f"Conduct after {boundary} is new conduct and is properly before this tribunal. "
           if boundary else "")
        + "Prior-proceeding evidence is offered for a limited purpose only."
    )

    return {
        "matter": matter,
        "hearing_date": hearing_date,
        "scope_statement": scope_statement,
        "opening_statement": _opening_statement(matter, in_scope),
        "scope_objection": (
            "Objection: that question goes to conduct decided in "
            f"{matter.get('case_number') or 'the prior proceeding'} and is outside the scope "
            "of this hearing. If offered for a limited purpose, I ask that the limited "
            "purpose be stated on the record."
        ),
        "in_scope_issues": in_scope,
        "out_of_scope_issues": out_of_scope,
        "rule_elements": rule_elements,
        "witness_questions": source_questions,
        "exhibit_sequence": exhibits,
        "objections": _objection_checklist(),
        "proposed_findings": [
            {"issue_key": i["issue_key"], "finding": i["requested_finding"],
             "has_finding": bool(i["requested_finding"])}
            for i in in_scope
        ],
        "requested_relief": _rows(conn,
            "SELECT * FROM relief WHERE matter_id=? AND status='ACTIVE'", (matter_id,)),
        "closing_outline": [
            "Restate the scope and the boundary date.",
            "Walk each rule element to the evidence that satisfies it.",
            "Identify each requested finding and the record support for it.",
            "Address the strongest defense directly.",
            "State the relief requested and the authority for it.",
            "Preserve every issue not ruled on, on the record.",
        ],
        "preservation_at_risk": [
            row for row in pres.preservation_matrix(conn, matter_id) if row["at_risk"]
        ],
        "readiness": checks.run_all(conn, matter_id).to_dict(),
    }


def _opening_statement(matter: dict[str, Any], issues: list[dict[str, Any]]) -> list[str]:
    lines = [
        f"This matter is {matter['title']}"
        + (f", {matter['case_number']}" if matter.get("case_number") else "") + ".",
    ]
    if matter.get("boundary_date"):
        lines.append(
            f"The prior proceeding concluded with a final order on {matter['boundary_date']}. "
            "What is before the tribunal today is conduct that occurred after that date."
        )
    if issues:
        lines.append(f"There are {len(issues)} issues in scope:")
        lines.extend(f"  {i['issue_key']}. {i['title']}" for i in issues[:12])
    lines.append("Each is supported by the record, or is identified as requiring proof.")
    return lines


def _objection_checklist() -> list[dict[str, str]]:
    return [
        {"ground": "Scope", "when": "Question concerns conduct decided in the prior case.",
         "say": "Objection, outside the scope of the noticed hearing."},
        {"ground": "Foundation", "when": "A document is used without establishing its source.",
         "say": "Objection, no foundation — who prepared this and when?"},
        {"ground": "Completeness", "when": "An excerpt is offered as the full chronology.",
         "say": "Objection, the rule of completeness; I ask for the entire record."},
        {"ground": "Hearsay", "when": "An out-of-court statement is offered for its truth.",
         "say": "Objection, hearsay."},
        {"ground": "Relevance", "when": "Billing or account history unrelated to the issue.",
         "say": "Objection, relevance — this hearing concerns notice and process."},
        {"ground": "Preservation", "when": "A request is passed over without a ruling.",
         "say": "I renew the request and ask for a ruling on the record."},
    ]


# ---------------------------------------------------------------------------
# Appeal Preservation
# ---------------------------------------------------------------------------
def preservation_view(conn: sqlite3.Connection, matter_id: int | None = None) -> dict[str, Any]:
    matters = list_matters(conn)
    target_ids = [matter_id] if matter_id is not None else [m["id"] for m in matters]

    sections: list[dict[str, Any]] = []
    for mid in target_ids:
        matter = _one(conn, "SELECT * FROM matters WHERE id=?", (mid,))
        if not matter:
            continue
        matrix = pres.preservation_matrix(conn, mid)
        sections.append({
            "matter": matter,
            "rows": matrix,
            "at_risk": sum(1 for row in matrix if row["at_risk"]),
            "deadlines": pres.upcoming_deadlines(conn, mid),
        })

    return {
        "sections": sections,
        "matters": matters,
        "matter_id": matter_id,
        "total_at_risk": sum(s["at_risk"] for s in sections),
    }


# ---------------------------------------------------------------------------
# supporting views
# ---------------------------------------------------------------------------
def approvals_view(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = _rows(conn, "SELECT * FROM approvals WHERE state='OPEN' ORDER BY id DESC")
    for row in rows:
        if row.get("options"):
            try:
                row["option_list"] = json.loads(row["options"])
            except (json.JSONDecodeError, TypeError):
                row["option_list"] = []
        else:
            row["option_list"] = []
        if row["target_table"] == "documents":
            row["document"] = _one(conn, "SELECT * FROM documents WHERE id=?",
                                   (row["target_id"],))
    return {"approvals": rows, "matters": list_matters(conn)}


def fleet_view(conn: sqlite3.Connection) -> dict[str, Any]:
    proposals = _rows(conn, "SELECT * FROM fleet_proposals ORDER BY id DESC LIMIT 50")
    for proposal in proposals:
        # Deliberately not called "items": Jinja resolves attributes before keys,
        # so `proposal.items` would return dict.items rather than this list.
        proposal["proposal_items"] = _rows(conn,
            "SELECT * FROM fleet_proposal_items WHERE proposal_id=? ORDER BY id",
            (proposal["id"],))
        for item in proposal["proposal_items"]:
            try:
                item["data"] = json.loads(item["payload"])
            except (json.JSONDecodeError, TypeError):
                item["data"] = {}
    return {
        "proposals": proposals,
        "pending_count": conn.execute(
            "SELECT COUNT(*) n FROM fleet_proposal_items WHERE decision='PENDING'"
        ).fetchone()["n"],
    }


def document_view(conn: sqlite3.Connection, document_id: int) -> dict[str, Any]:
    document = _one(conn, "SELECT * FROM documents WHERE id=?", (document_id,))
    if not document:
        return {}
    try:
        document["notes_parsed"] = json.loads(document["notes"] or "{}")
    except (json.JSONDecodeError, TypeError):
        document["notes_parsed"] = {}
    return {
        "document": document,
        "text": _document_text(conn, document_id, limit=200_000),
        "links": _rows(conn, """
            SELECT l.*, m.slug, m.title AS matter_title FROM document_matter_links l
            JOIN matters m ON m.id=l.matter_id WHERE l.document_id=?
        """, (document_id,)),
        "events": _rows(conn,
            "SELECT * FROM events WHERE source_document_id=? ORDER BY event_date",
            (document_id,)),
        "filings": _rows(conn, "SELECT * FROM filings WHERE document_id=?", (document_id,)),
        "audit": _rows(conn,
            "SELECT * FROM audit_log WHERE target_table='documents' AND target_id=? "
            "ORDER BY id DESC LIMIT 25", (document_id,)),
        "duplicates": _rows(conn,
            "SELECT id, doc_uid, storage_path FROM documents WHERE sha256=? AND id<>?",
            (document["sha256"], document_id)),
    }
