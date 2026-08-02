"""Appeal-preservation workflows and deadline generation.

Three triggers create work automatically:

* a Recommended Decision   -> an exception-deadline workflow
* a final order            -> an appeal-deadline workflow
* a motion left unruled    -> a standing preservation warning that never clears
                              itself

About the day counts below: every computed date is provisional. It is stored
with verification_status='INFERENCE' and carries the authority that must be
checked. Case Command will not present a computed deadline as a verified legal
deadline — a missed deadline caused by a confidently wrong default would be
worse than a date marked "confirm this".
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from . import audit
from .db import insert, utcnow


@dataclass(frozen=True)
class DeadlineRule:
    """A default interval that must be confirmed against the cited authority."""

    key: str
    label: str
    days: int
    authority: str
    counts_from: str
    note: str


#: Provisional defaults. `authority` names what to verify them against.
DEADLINE_RULES: dict[str, DeadlineRule] = {
    "psc_exceptions": DeadlineRule(
        key="psc_exceptions",
        label="Exceptions to Recommended Decision",
        days=15,
        authority="W. Va. PSC Rules of Practice and Procedure — confirm the exception period",
        counts_from="date the Recommended Decision was issued",
        note="Provisional. Confirm the period and the counting method before relying on it.",
    ),
    "psc_appeal_wvsca": DeadlineRule(
        key="psc_appeal_wvsca",
        label="Appeal to the WVSCA from a PSC final order",
        days=30,
        authority="W. Va. Code § 24-5-1 and the W. Va. R. App. P. — confirm the appeal period",
        counts_from="date the final order was entered",
        note="Provisional. Confirm the period, the trigger date, and any tolling.",
    ),
    "civil_appeal": DeadlineRule(
        key="civil_appeal",
        label="Notice of appeal from a civil judgment",
        days=30,
        authority="Applicable rules of appellate procedure — confirm the appeal period",
        counts_from="date of entry of the judgment appealed from",
        note="Provisional. Confirm against the governing rule for this forum.",
    ),
    "response": DeadlineRule(
        key="response",
        label="Response to a motion",
        days=20,
        authority="Local rule or scheduling order — confirm",
        counts_from="date of service",
        note="Provisional. Confirm against the governing rule or order.",
    ),
}


def add_days(iso_date: str, days: int) -> str | None:
    """Calendar-day arithmetic. Does not account for weekends, holidays, or
    service extensions — which is exactly why the result is INFERENCE."""
    try:
        year, month, day = (int(part) for part in iso_date.split("-")[:3])
        return (date(year, month, day) + timedelta(days=days)).isoformat()
    except (ValueError, AttributeError):
        return None


def _create_deadline(conn: sqlite3.Connection, *, matter_id: int | None,
                     issue_id: int | None, title: str, due_date: str | None,
                     deadline_type: str, rule: DeadlineRule,
                     trigger_event: str, trigger_order_id: int | None,
                     source_document_id: int | None, actor: str) -> int:
    return insert(conn, "deadlines", {
        "matter_id": matter_id,
        "issue_id": issue_id,
        "title": title,
        "due_date": due_date,
        "deadline_type": deadline_type,
        "trigger_event": trigger_event,
        "trigger_order_id": trigger_order_id,
        "days_allowed": rule.days,
        "satisfied": 0,
        # Never VERIFIED: the interval itself is an unconfirmed default.
        "verification_status": "INFERENCE",
        "source_document_id": source_document_id,
        "created_by": actor,
        "notes": (f"{rule.note} Authority to confirm: {rule.authority}. "
                  f"Counted from the {rule.counts_from}."),
    })


def on_recommended_decision(conn: sqlite3.Connection, order_id: int, *,
                            actor: str = "preservation") -> dict[str, Any]:
    """A Recommended Decision starts the exception workflow for every live issue."""
    order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if order is None:
        raise ValueError(f"no order {order_id}")

    rule = DEADLINE_RULES["psc_exceptions"]
    due = add_days(order["entered_date"], rule.days) if order["entered_date"] else None

    deadline_id = _create_deadline(
        conn, matter_id=order["matter_id"], issue_id=None,
        title=f"Exceptions due — {order['title']}",
        due_date=due, deadline_type="exception", rule=rule,
        trigger_event="RECOMMENDED_DECISION", trigger_order_id=order_id,
        source_document_id=order["document_id"], actor=actor,
    )
    conn.execute("UPDATE orders SET exception_deadline=?, is_recommended_decision=1 WHERE id=?",
                 (due, order_id))

    # Every active issue in the matter now needs an exception decision.
    updated = 0
    for issue in conn.execute(
        "SELECT * FROM issues WHERE matter_id=? AND status IN ('ACTIVE','RESERVED','MISSING_PROOF')",
        (order["matter_id"],),
    ).fetchall():
        row = conn.execute(
            "SELECT id FROM preservation_items WHERE issue_id=? AND status='ACTIVE'",
            (issue["id"],)).fetchone()
        if row:
            conn.execute(
                "UPDATE preservation_items SET exception_required=1, appeal_deadline=?, "
                "final_order_treatment=?, updated_at=? WHERE id=?",
                (due, "Recommended Decision issued; exceptions required to preserve.",
                 utcnow(), row["id"]),
            )
        else:
            insert(conn, "preservation_items", {
                "matter_id": order["matter_id"], "issue_id": issue["id"],
                "title": f"Preservation: {issue['title']}",
                "exception_required": 1, "appeal_deadline": due,
                "final_order_treatment": "Recommended Decision issued; exceptions required.",
                "verification_status": "INFERENCE", "created_by": actor,
            })
        updated += 1

    audit.record(conn, actor=actor, action="RECOMMENDED_DECISION_WORKFLOW",
                 target_table="orders", target_id=order_id, matter_id=order["matter_id"],
                 summary=f"exception deadline {due} for {updated} issue(s)",
                 payload={"deadline_id": deadline_id, "provisional": True})

    return {"deadline_id": deadline_id, "due_date": due, "issues_flagged": updated,
            "provisional": True, "confirm_against": rule.authority}


def on_final_order(conn: sqlite3.Connection, order_id: int, *,
                   rule_key: str = "psc_appeal_wvsca",
                   actor: str = "preservation") -> dict[str, Any]:
    """A final order starts the appeal workflow and freezes preservation state."""
    order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if order is None:
        raise ValueError(f"no order {order_id}")

    rule = DEADLINE_RULES.get(rule_key, DEADLINE_RULES["civil_appeal"])
    due = add_days(order["entered_date"], rule.days) if order["entered_date"] else None

    deadline_id = _create_deadline(
        conn, matter_id=order["matter_id"], issue_id=None,
        title=f"Appeal deadline — {order['title']}",
        due_date=due, deadline_type="appeal", rule=rule,
        trigger_event="FINAL_ORDER", trigger_order_id=order_id,
        source_document_id=order["document_id"], actor=actor,
    )
    conn.execute("UPDATE orders SET appeal_deadline=?, is_final=1 WHERE id=?", (due, order_id))

    flagged = 0
    for issue in conn.execute(
        "SELECT * FROM issues WHERE matter_id=?", (order["matter_id"],)
    ).fetchall():
        row = conn.execute(
            "SELECT * FROM preservation_items WHERE issue_id=? AND status='ACTIVE'",
            (issue["id"],)).fetchone()
        treatment = ("Issue was raised; confirm whether the final order addressed it."
                     if row and row["raised"]
                     else "Issue not recorded as raised before the final order.")
        if row:
            conn.execute(
                "UPDATE preservation_items SET appeal_deadline=?, final_order_treatment=?, "
                "updated_at=? WHERE id=?",
                (due, treatment, utcnow(), row["id"]))
        else:
            insert(conn, "preservation_items", {
                "matter_id": order["matter_id"], "issue_id": issue["id"],
                "title": f"Preservation: {issue['title']}",
                "appeal_deadline": due, "final_order_treatment": treatment,
                "verification_status": "INFERENCE", "created_by": actor,
            })
        flagged += 1

    audit.record(conn, actor=actor, action="FINAL_ORDER_WORKFLOW",
                 target_table="orders", target_id=order_id, matter_id=order["matter_id"],
                 summary=f"appeal deadline {due} for {flagged} issue(s)",
                 payload={"deadline_id": deadline_id, "provisional": True})

    return {"deadline_id": deadline_id, "due_date": due, "issues_flagged": flagged,
            "provisional": True, "confirm_against": rule.authority}


def on_motion_ignored(conn: sqlite3.Connection, motion_id: int, *,
                      actor: str = "preservation") -> dict[str, Any]:
    """Mark a motion as ignored, producing a warning that stays visible."""
    motion = conn.execute("SELECT * FROM motions WHERE id=?", (motion_id,)).fetchone()
    if motion is None:
        raise ValueError(f"no motion {motion_id}")

    row = conn.execute(
        "SELECT * FROM preservation_items WHERE issue_id=? AND status='ACTIVE'",
        (motion["issue_id"],)).fetchone() if motion["issue_id"] else None

    if row:
        # Filing the motion is itself the act of raising the issue, so `raised`
        # is set here too. Without it the item stalls at "never raised" and the
        # ignored-motion warning is never reached.
        conn.execute(
            "UPDATE preservation_items SET raised=1, where_raised=COALESCE(where_raised, ?), "
            "date_raised=COALESCE(date_raised, ?), ignored=1, ruling_requested=1, "
            "ruling_issued=0, risk=?, updated_at=? WHERE id=?",
            (motion["title"], motion["filed_date"],
             "Motion left unruled. Without an exception or a renewed request on the record, "
             "the issue may be treated as abandoned.", utcnow(), row["id"]))
        item_id = row["id"]
    else:
        item_id = insert(conn, "preservation_items", {
            "matter_id": motion["matter_id"], "issue_id": motion["issue_id"],
            "title": f"Preservation: {motion['title']}",
            "raised": 1, "ruling_requested": 1, "ruling_issued": 0, "ignored": 1,
            "where_raised": motion["title"], "date_raised": motion["filed_date"],
            "risk": "Motion left unruled. Preserve by renewing the request or filing an exception.",
            "verification_status": "UNKNOWN", "created_by": actor,
        })

    audit.record(conn, actor=actor, action="MOTION_IGNORED",
                 target_table="motions", target_id=motion_id, matter_id=motion["matter_id"],
                 summary=motion["title"], payload={"preservation_item_id": item_id})

    return {"preservation_item_id": item_id, "warning": True,
            "detail": "Ignored motion recorded. The warning stays until a ruling or "
                      "an exception is recorded."}


def preservation_matrix(conn: sqlite3.Connection, matter_id: int) -> list[dict[str, Any]]:
    """The Appeal Preservation view: every issue and its full preservation state."""
    rows = conn.execute(
        """
        SELECT i.issue_key, i.title AS issue_title, i.status AS issue_status,
               i.appeal_standard, p.*
        FROM issues i
        LEFT JOIN preservation_items p ON p.issue_id = i.id AND p.status='ACTIVE'
        WHERE i.matter_id=?
        ORDER BY i.issue_key
        """,
        (matter_id,),
    ).fetchall()

    matrix: list[dict[str, Any]] = []
    for row in rows:
        data = dict(row)
        risks: list[str] = []
        if not data.get("raised"):
            risks.append("not raised")
        if data.get("ruling_requested") and not data.get("ruling_issued"):
            risks.append("no ruling")
        if data.get("ignored") and not data.get("exception_filed"):
            risks.append("ignored, no exception")
        if data.get("exception_required") and not data.get("exception_filed"):
            risks.append("exception due")
        data["risk_flags"] = risks
        data["at_risk"] = bool(risks)
        matrix.append(data)
    return matrix


def upcoming_deadlines(conn: sqlite3.Connection, matter_id: int | None = None,
                       limit: int = 20) -> list[dict[str, Any]]:
    sql = ("SELECT d.*, m.slug AS matter_slug FROM deadlines d "
           "LEFT JOIN matters m ON m.id = d.matter_id "
           "WHERE d.satisfied=0 AND d.status='ACTIVE' AND d.due_date IS NOT NULL")
    params: list[Any] = []
    if matter_id is not None:
        sql += " AND d.matter_id=?"
        params.append(matter_id)
    sql += " ORDER BY d.due_date LIMIT ?"
    params.append(limit)
    return [dict(r) for r in conn.execute(sql, params)]
