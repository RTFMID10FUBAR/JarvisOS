"""Timeline events, what proves them, and adding one by hand.

The timeline is the part of this record that gets read out loud. Someone asks
"when did the power go out, and how do you know" and the answer has to arrive in
one piece. So every event here carries its proof with it, and an event with no
proof says so rather than looking like the others.

Three rules run through this module.

**A recollection is not proof of the fact.** It is a record that Jacob recalls
something, made on a date. Both are worth having. Storing them the same way
would make them look the same everywhere downstream, and the place that
difference gets tested is a hearing. So a recollection is its own proof type,
it never raises an event above `UNKNOWN`, and every view that shows it shows
when it was recorded.

**The gap between the event and the recording of it is a fact.** A memory
written down the same week is a different thing from the same memory written
down two years later. That gap is arithmetic on two dates, not a judgement, so
it is reported. It is never scored.

**Adding proof never marks anything verified.** Proof is necessary for
verification and not sufficient — a human still reads the document and confirms
it says what the event claims. This module will raise an event to
`PARTIALLY_VERIFIED` when documentary proof with a locator exists, and no
higher. `VERIFIED_PRIMARY` is a person's decision, made explicitly.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any

from .audit import record as audit_record
from .db import utcnow

PROOF_TYPES = (
    "DOCUMENT", "PHOTO", "RECORDING", "THIRD_PARTY_RECORD",
    "WITNESS", "RECOLLECTION", "NONE",
)

#: Proof that points at something in the record, which another person could go
#: and read for themselves.
DOCUMENTARY = ("DOCUMENT", "PHOTO", "RECORDING", "THIRD_PARTY_RECORD")

#: Proof that is somebody saying so. Real evidence, different kind.
TESTIMONIAL = ("WITNESS", "RECOLLECTION")

DATE_PRECISIONS = ("EXACT", "APPROXIMATE", "MONTH_ONLY", "YEAR_ONLY", "UNKNOWN")

PROOF_LABELS = {
    "DOCUMENT": "a document in the record",
    "PHOTO": "a photograph in the record",
    "RECORDING": "an audio or video recording in the record",
    "THIRD_PARTY_RECORD": "a record kept by someone else",
    "WITNESS": "a named person who would say so",
    "RECOLLECTION": "recalled, not yet documented",
    "NONE": "nothing yet",
}


class ProofError(ValueError):
    """A proof that could not be recorded as offered."""


# ---------------------------------------------------------------------------
# adding events
# ---------------------------------------------------------------------------
def add_event(conn: sqlite3.Connection, *, title: str, event_date: str | None,
              matter_id: int | None = None, event_type: str | None = None,
              legal_significance: str | None = None,
              boundary_classification: str = "UNKNOWN",
              date_precision: str = "EXACT",
              recalled: bool = False, notes: str | None = None,
              actor_name: str | None = None,
              actor: str = "jacob") -> dict[str, Any]:
    """Record an event a person is adding by hand.

    The event starts at `MISSING_SOURCE`. It is not a lesser event for that —
    it is an accurate one, and attaching proof is a separate, deliberate act.
    Creating it already verified would be the system asserting something nobody
    checked.
    """
    title = (title or "").strip()
    if not title:
        raise ProofError("an event needs a title: what happened, in your words")
    if date_precision not in DATE_PRECISIONS:
        raise ProofError(f"unknown date precision: {date_precision}")
    if not event_date and date_precision != "UNKNOWN":
        raise ProofError(
            "an event with no date must be recorded with date_precision=UNKNOWN, "
            "so the missing date is visible rather than implied")

    cur = conn.execute("""
        INSERT INTO events (matter_id, title, event_date, event_type,
                            legal_significance, boundary_classification,
                            verification_status, origin, recalled, date_precision,
                            actor_name, notes, created_by, updated_at)
        VALUES (?,?,?,?,?,?,'MISSING_SOURCE','MANUAL',?,?,?,?,?,?)
    """, (matter_id, title, event_date, event_type, legal_significance,
          boundary_classification, 1 if recalled else 0, date_precision,
          actor_name, notes, actor, utcnow()))
    event_id = int(cur.lastrowid)
    conn.commit()

    audit_record(conn, actor=actor, action="event.add", target_table="events",
                 target_id=event_id, matter_id=matter_id,
                 summary=f"manual event {title!r} on {event_date or 'no date'} "
                         f"({date_precision.lower()})")
    return get_event(conn, event_id)


def attach_proof(conn: sqlite3.Connection, event_id: int, *, proof_type: str,
                 document_id: int | None = None, locator: str | None = None,
                 asserted_by: str | None = None, detail: str | None = None,
                 notes: str | None = None, actor: str = "jacob") -> dict[str, Any]:
    """Attach one piece of proof to an event.

    Refuses vague proof at the boundary rather than storing it and letting a
    later reader discover it says nothing. Documentary proof without a locator
    is the common case: "it's in the record somewhere" cannot be handed to a
    tribunal, so it is not accepted as documentary proof at all.
    """
    if proof_type not in PROOF_TYPES:
        raise ProofError(f"unknown proof type: {proof_type}")
    if conn.execute("SELECT 1 FROM events WHERE id=?", (event_id,)).fetchone() is None:
        raise ProofError(f"no event {event_id}")

    if proof_type in DOCUMENTARY:
        if document_id is None:
            raise ProofError(
                f"{proof_type} proof must name the document it points at")
        if conn.execute("SELECT 1 FROM documents WHERE id=?",
                        (document_id,)).fetchone() is None:
            raise ProofError(f"no document {document_id}")
        if proof_type == "DOCUMENT" and not (locator or "").strip():
            raise ProofError(
                "documentary proof needs a locator — a page, paragraph, or line. "
                "'It is in the record somewhere' cannot be checked by anyone else.")

    if proof_type in TESTIMONIAL and not (asserted_by or "").strip():
        raise ProofError(f"{proof_type} proof must name who says so")

    cur = conn.execute("""
        INSERT INTO event_proof (event_id, proof_type, document_id, locator,
                                 asserted_by, detail, notes, created_by)
        VALUES (?,?,?,?,?,?,?,?)
    """, (event_id, proof_type, document_id, locator, asserted_by, detail,
          notes, actor))
    proof_id = int(cur.lastrowid)
    conn.commit()

    _resettle_verification(conn, event_id, actor=actor)

    audit_record(conn, actor=actor, action="event.proof.attach",
                 target_table="event_proof", target_id=proof_id,
                 summary=f"{proof_type} proof for event {event_id}"
                         + (f" at {locator}" if locator else ""))
    return get_event(conn, event_id)


def _resettle_verification(conn: sqlite3.Connection, event_id: int, *,
                           actor: str) -> None:
    """Move an event's verification status to match the proof it now has.

    Upward movement stops at PARTIALLY_VERIFIED. Documentary proof means the
    claim can be checked; it does not mean anyone has checked it. Going further
    would be this system marking a fact verified because a row exists, which is
    the specific thing it is built not to do.

    A status a person set deliberately — VERIFIED_PRIMARY, DISPUTED,
    SUPERSEDED — is never overwritten here.
    """
    row = conn.execute("SELECT verification_status FROM events WHERE id=?",
                       (event_id,)).fetchone()
    current = row["verification_status"]
    if current not in ("MISSING_SOURCE", "UNKNOWN", "PARTIALLY_VERIFIED"):
        return

    kinds = {r["proof_type"] for r in conn.execute(
        "SELECT DISTINCT proof_type FROM event_proof WHERE event_id=?", (event_id,))}

    if kinds & set(DOCUMENTARY):
        target = "PARTIALLY_VERIFIED"
    elif kinds & set(TESTIMONIAL):
        # Somebody saying so is evidence. It is not a source in the record, and
        # this system does not treat it as one.
        target = "UNKNOWN"
    else:
        target = "MISSING_SOURCE"

    if target != current:
        conn.execute("UPDATE events SET verification_status=?, updated_at=?, "
                     "last_reviewed_by=? WHERE id=?",
                     (target, utcnow(), actor, event_id))
        conn.commit()


# ---------------------------------------------------------------------------
# reading events back
# ---------------------------------------------------------------------------
def _days_between(earlier: str | None, later: str | None) -> int | None:
    if not earlier or not later:
        return None
    try:
        a = date.fromisoformat(earlier[:10])
        b = date.fromisoformat(later[:10])
    except ValueError:
        return None
    return (b - a).days


def proof_for(conn: sqlite3.Connection, event_id: int) -> list[dict[str, Any]]:
    """Every piece of proof attached to an event, strongest kind first."""
    rows = [dict(r) for r in conn.execute("""
        SELECT p.*, d.doc_uid, d.title AS document_title, d.storage_path
        FROM event_proof p LEFT JOIN documents d ON d.id = p.document_id
        WHERE p.event_id = ? ORDER BY p.id
    """, (event_id,))]

    order = {t: i for i, t in enumerate(PROOF_TYPES)}
    rows.sort(key=lambda r: order.get(r["proof_type"], 99))

    event = conn.execute("SELECT event_date FROM events WHERE id=?",
                         (event_id,)).fetchone()
    event_date = event["event_date"] if event else None

    for row in rows:
        row["label"] = PROOF_LABELS.get(row["proof_type"], row["proof_type"])
        row["is_documentary"] = row["proof_type"] in DOCUMENTARY
        row["is_testimonial"] = row["proof_type"] in TESTIMONIAL
        # How long after the event the assertion was made. A fact, reported,
        # never scored — a reader decides what it is worth.
        row["recorded_after_days"] = _days_between(event_date, row["asserted_at"])
        # A document that is no longer where the record says it is cannot be
        # produced, and a proof row that points at it is worth knowing about.
        row["document_missing"] = bool(
            row["document_id"] and not row["storage_path"])
    return rows


def summarise_proof(proofs: list[dict[str, Any]]) -> dict[str, Any]:
    """One line describing what stands behind an event.

    Never characterises the strength of a case. Says which kinds of proof exist
    and, when there are none, says that plainly.
    """
    if not proofs:
        return {"state": "NONE", "headline": "Nothing in the record proves this yet.",
                "documentary": 0, "testimonial": 0,
                "detail": "This is a statement about the record, not about whether "
                          "the event happened."}

    documentary = [p for p in proofs if p["is_documentary"]]
    testimonial = [p for p in proofs if p["is_testimonial"]]

    if documentary:
        first = documentary[0]
        where = f"{first['doc_uid']}"
        if first["locator"]:
            where += f" at {first['locator']}"
        headline = f"Proved by {where}"
        if len(documentary) > 1:
            headline += f", and {len(documentary) - 1} more in the record"
        state = "DOCUMENTED"
    else:
        who = testimonial[0]["asserted_by"] or "unnamed"
        kind = "Recalled by" if testimonial[0]["proof_type"] == "RECOLLECTION" else "Asserted by"
        headline = f"{kind} {who} — not documented"
        state = "TESTIMONIAL"

    return {
        "state": state,
        "headline": headline,
        "documentary": len(documentary),
        "testimonial": len(testimonial),
        "detail": ("A person's account is evidence. It is not a source in the "
                   "record, and nothing here treats it as one."
                   if state == "TESTIMONIAL" else
                   "Open the document and confirm it says what this event claims "
                   "before marking the event verified."),
    }


def timeline(conn: sqlite3.Connection, *, matter_id: int | None = None,
             limit: int = 500) -> list[dict[str, Any]]:
    """Events in date order, each carrying its proof."""
    sql = ("SELECT e.*, m.slug AS matter_slug FROM events e "
           "LEFT JOIN matters m ON m.id = e.matter_id WHERE e.status='ACTIVE'")
    params: list[Any] = []
    if matter_id is not None:
        sql += " AND e.matter_id = ?"
        params.append(matter_id)
    # Undated events sort last rather than being hidden. An event nobody can
    # date is still an event, and dropping it would be the omission this whole
    # system exists to prevent.
    sql += " ORDER BY (e.event_date IS NULL), e.event_date, e.id LIMIT ?"
    params.append(int(limit))

    out = []
    for row in conn.execute(sql, params):
        event = dict(row)
        proofs = proof_for(conn, event["id"])
        event["proofs"] = proofs
        event["proof"] = summarise_proof(proofs)
        event["is_manual"] = event.get("origin") == "MANUAL"
        out.append(event)
    return out


def get_event(conn: sqlite3.Connection, event_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if row is None:
        raise ProofError(f"no event {event_id}")
    event = dict(row)
    event["proofs"] = proof_for(conn, event_id)
    event["proof"] = summarise_proof(event["proofs"])
    return event


def unproved(conn: sqlite3.Connection, matter_id: int | None = None) -> dict[str, Any]:
    """Which events nothing in the record proves.

    Counts with denominators, so every number can be checked. No score.
    """
    events = timeline(conn, matter_id=matter_id)
    none = [e for e in events if e["proof"]["state"] == "NONE"]
    testimonial = [e for e in events if e["proof"]["state"] == "TESTIMONIAL"]
    documented = [e for e in events if e["proof"]["state"] == "DOCUMENTED"]
    return {
        "total": len(events),
        "documented": len(documented),
        "testimonial_only": len(testimonial),
        "unproved": len(none),
        "label": f"{len(documented)} of {len(events)} events have documentary proof",
        "note": ("A count, not a score. An event with no proof is not a weak "
                 "event; it is an event whose proof is not in the record yet."),
        "unproved_events": [{"id": e["id"], "title": e["title"],
                             "event_date": e["event_date"]} for e in none[:50]],
    }


def proof_index(conn: sqlite3.Connection,
                event_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Proof for many events in one pass.

    The timeline view already has its own filtered query; this lets it attach
    proof without giving up any of those filters, and without one query per row.
    """
    if not event_ids:
        return {}

    marks = ",".join("?" * len(event_ids))
    rows = [dict(r) for r in conn.execute(f"""
        SELECT p.*, d.doc_uid, d.title AS document_title, d.storage_path,
               e.event_date
        FROM event_proof p
        JOIN events e ON e.id = p.event_id
        LEFT JOIN documents d ON d.id = p.document_id
        WHERE p.event_id IN ({marks})
        ORDER BY p.event_id, p.id
    """, tuple(event_ids))]

    order = {t: i for i, t in enumerate(PROOF_TYPES)}
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        row["label"] = PROOF_LABELS.get(row["proof_type"], row["proof_type"])
        row["is_documentary"] = row["proof_type"] in DOCUMENTARY
        row["is_testimonial"] = row["proof_type"] in TESTIMONIAL
        row["recorded_after_days"] = _days_between(row["event_date"], row["asserted_at"])
        row["document_missing"] = bool(row["document_id"] and not row["storage_path"])
        grouped.setdefault(int(row["event_id"]), []).append(row)

    index: dict[int, dict[str, Any]] = {}
    for event_id in event_ids:
        proofs = sorted(grouped.get(event_id, []),
                        key=lambda r: order.get(r["proof_type"], 99))
        index[event_id] = {"proofs": proofs, "summary": summarise_proof(proofs)}
    return index


def documents_for_picker(conn: sqlite3.Connection,
                         matter_id: int | None = None) -> list[dict[str, Any]]:
    """Documents offerable as proof, newest first.

    Shows each document's own date and the verbatim line it was identified by,
    so a person choosing proof is choosing against what the document actually
    says rather than against a filename.
    """
    sql = ("SELECT id, doc_uid, title, document_date, extract_line, matter_id "
           "FROM documents WHERE status='ACTIVE'")
    params: list[Any] = []
    if matter_id is not None:
        sql += " AND (matter_id = ? OR matter_id IS NULL)"
        params.append(matter_id)
    sql += " ORDER BY (document_date IS NULL), document_date DESC, id DESC LIMIT 300"
    return [dict(r) for r in conn.execute(sql, params)]
