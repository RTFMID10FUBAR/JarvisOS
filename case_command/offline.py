"""Offline availability and phone capture.

Two problems, both of which show up at the worst moment.

**Reading the record with no network.** A hearing room in a basement, or a
house with the power cut. Pinning marks specific documents as must-be-readable
offline; the service worker caches exactly those and nothing else. Phone storage
is finite, so this never guesses — it keeps what was chosen, reports the size in
advance, and says plainly when a pin cannot be honoured.

**Capturing evidence with no network.** A photograph of a meter being pulled, or
a shutoff notice on the porch, is evidence that will never exist again. It is
accepted on the device with no connection, queued, and reconciled into the
record when a connection returns. A failed upload never discards the capture.

The hearing pack is the case this was really built for: one action that pins
everything needed to argue a specific hearing — exhibits, in-scope issues, rule
elements, requested findings, the scope statement, the objection checklist.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from . import audit
from .db import insert, utcnow

PIN_REASONS = ("MANUAL", "EXHIBIT", "HEARING_PACK", "DEADLINE", "EVIDENCE")

#: Rough phone budget. Not enforced — reported, so the choice stays Jacob's.
DEFAULT_BUDGET_BYTES = 250 * 1024 * 1024

#: Text is what you argue from and costs almost nothing. Originals are opt-in
#: because a scanned exhibit can be tens of megabytes.
TEXT_OVERHEAD_BYTES = 2_048


# ---------------------------------------------------------------------------
# pinning
# ---------------------------------------------------------------------------
def _estimate_bytes(document: sqlite3.Row, *, include_text: bool,
                    include_original: bool, include_preview: bool) -> int:
    total = TEXT_OVERHEAD_BYTES
    if include_text:
        total += int(document["text_chars"] or 0)
    if include_original:
        total += int(document["byte_size"] or 0)
    if include_preview:
        total += 120 * 1024   # a rendered page image, roughly
    return total


def pin(conn: sqlite3.Connection, document_id: int, *, reason: str = "MANUAL",
        include_text: bool = True, include_original: bool = False,
        include_preview: bool = True, hearing_event_id: int | None = None,
        priority: int = 100, actor: str = "jacob",
        note: str | None = None) -> dict[str, Any]:
    """Mark a document to be kept readable with no network."""
    reason = reason.upper()
    if reason not in PIN_REASONS:
        raise ValueError(f"{reason!r} is not a pin reason. Allowed: {', '.join(PIN_REASONS)}")

    document = conn.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
    if document is None:
        raise ValueError(f"no document {document_id}")

    est = _estimate_bytes(document, include_text=include_text,
                          include_original=include_original,
                          include_preview=include_preview)

    existing = conn.execute(
        "SELECT id FROM offline_pins WHERE document_id=? AND reason=?",
        (document_id, reason)).fetchone()

    if existing:
        conn.execute(
            "UPDATE offline_pins SET include_text=?, include_original=?, include_preview=?, "
            "est_bytes=?, priority=?, sync_state='PENDING', hearing_event_id=?, notes=? "
            "WHERE id=?",
            (1 if include_text else 0, 1 if include_original else 0,
             1 if include_preview else 0, est, priority, hearing_event_id, note,
             existing["id"]))
        pin_id = int(existing["id"])
        action = "OFFLINE_PIN_UPDATED"
    else:
        pin_id = insert(conn, "offline_pins", {
            "document_id": document_id,
            "matter_id": document["matter_id"],
            "reason": reason,
            "hearing_event_id": hearing_event_id,
            "include_text": 1 if include_text else 0,
            "include_original": 1 if include_original else 0,
            "include_preview": 1 if include_preview else 0,
            "est_bytes": est,
            "priority": priority,
            "pinned_by": actor,
            "sync_state": "PENDING",
            "notes": note,
        })
        action = "OFFLINE_PINNED"

    # A pin that cannot be honoured is stated now, not discovered in the hearing.
    if include_text and not (document["text_path"] and Path(document["text_path"]).exists()):
        conn.execute(
            "UPDATE offline_pins SET sync_state='UNAVAILABLE', sync_error=? WHERE id=?",
            ("No extracted text exists for this document, so there is nothing to read "
             "offline. Re-run extraction, or pin the original instead.", pin_id))

    audit.record(conn, actor=actor, action=action, target_table="offline_pins",
                 target_id=pin_id, matter_id=document["matter_id"],
                 summary=f"{document['doc_uid']} pinned offline ({reason})",
                 payload={"est_bytes": est, "include_original": include_original})

    return {"pin_id": pin_id, "doc_uid": document["doc_uid"], "reason": reason,
            "est_bytes": est, "est_mb": round(est / 1_048_576, 2)}


def unpin(conn: sqlite3.Connection, document_id: int, *, reason: str | None = None,
          actor: str = "jacob") -> dict[str, Any]:
    """Release a pin. The document stays in the record; only the phone copy goes."""
    if reason:
        cur = conn.execute("DELETE FROM offline_pins WHERE document_id=? AND reason=?",
                           (document_id, reason.upper()))
    else:
        cur = conn.execute("DELETE FROM offline_pins WHERE document_id=?", (document_id,))
    removed = cur.rowcount or 0
    audit.record(conn, actor=actor, action="OFFLINE_UNPINNED",
                 target_table="documents", target_id=document_id,
                 summary=f"{removed} pin(s) released")
    return {"released": removed,
            "note": "The document remains in the record. Only its offline copy is released."}


def list_pins(conn: sqlite3.Connection, matter_id: int | None = None) -> list[dict[str, Any]]:
    sql = ["""
        SELECT p.*, d.doc_uid, d.title, d.original_filename, d.document_date,
               d.text_chars, d.byte_size, d.extract_line, m.slug AS matter_slug
        FROM offline_pins p
        JOIN documents d ON d.id = p.document_id
        LEFT JOIN matters m ON m.id = p.matter_id
        WHERE 1=1
    """]
    params: list[Any] = []
    if matter_id is not None:
        sql.append("AND p.matter_id=?")
        params.append(matter_id)
    sql.append("ORDER BY p.priority, p.pinned_at")
    return [dict(r) for r in conn.execute("\n".join(sql), params)]


def storage_report(conn: sqlite3.Connection,
                   budget_bytes: int = DEFAULT_BUDGET_BYTES) -> dict[str, Any]:
    """What the pinned set costs, before it is downloaded."""
    pins = list_pins(conn)
    total = sum(int(p["est_bytes"] or 0) for p in pins)
    unavailable = [p for p in pins if p["sync_state"] == "UNAVAILABLE"]

    by_reason: dict[str, dict[str, int]] = {}
    for p in pins:
        entry = by_reason.setdefault(p["reason"], {"count": 0, "bytes": 0})
        entry["count"] += 1
        entry["bytes"] += int(p["est_bytes"] or 0)

    return {
        "pin_count": len(pins),
        "total_bytes": total,
        "total_mb": round(total / 1_048_576, 2),
        "budget_bytes": budget_bytes,
        "budget_mb": round(budget_bytes / 1_048_576, 1),
        "over_budget": total > budget_bytes,
        "by_reason": by_reason,
        "unavailable": [
            {"doc_uid": p["doc_uid"], "reason": p["sync_error"]} for p in unavailable
        ],
        "note": ("An estimate made before download. It is reported rather than enforced: "
                 "what to keep on the phone is your decision, not the system's."),
    }


# ---------------------------------------------------------------------------
# hearing pack
# ---------------------------------------------------------------------------
def build_hearing_pack(conn: sqlite3.Connection, matter_id: int, *,
                       hearing_event_id: int | None = None,
                       include_originals: bool = False,
                       actor: str = "jacob") -> dict[str, Any]:
    """Pin everything needed to argue one hearing, in a single action.

    Exhibits first, then anything linked to an in-scope issue, then filings and
    orders for the matter. Priority ordering means the exhibits land on the
    device first if the connection dies partway through.
    """
    matter = conn.execute("SELECT * FROM matters WHERE id=?", (matter_id,)).fetchone()
    if matter is None:
        raise ValueError(f"no matter {matter_id}")

    pinned: list[dict[str, Any]] = []
    seen: set[int] = set()

    def add(document_id: int, priority: int, note: str) -> None:
        if document_id in seen or document_id is None:
            return
        seen.add(document_id)
        pinned.append(pin(conn, document_id, reason="HEARING_PACK",
                          include_original=include_originals,
                          hearing_event_id=hearing_event_id,
                          priority=priority, actor=actor, note=note))

    # 1. Exhibits — what gets handed up.
    for row in conn.execute("""
        SELECT e.document_id, e.exhibit_number, e.title FROM evidence e
        WHERE e.matter_id=? AND e.status='ACTIVE' AND e.document_id IS NOT NULL
        ORDER BY CASE WHEN e.exhibit_number IS NULL THEN 1 ELSE 0 END, e.exhibit_number
    """, (matter_id,)):
        add(row["document_id"], 10, f"Exhibit {row['exhibit_number'] or '—'}")

    # 2. Documents backing an in-scope issue.
    for row in conn.execute("""
        SELECT DISTINCT l.linked_id AS document_id, i.issue_key FROM issue_links l
        JOIN issues i ON i.id = l.issue_id
        WHERE l.linked_type='document' AND i.matter_id=? AND i.status='ACTIVE'
          AND (i.hearing_scope IS NULL OR i.hearing_scope <> 'OUTSIDE_CURRENT_HEARING')
    """, (matter_id,)):
        add(row["document_id"], 20, f"Supports {row['issue_key']}")

    # 3. Filings and orders in the matter.
    for row in conn.execute("""
        SELECT document_id, title FROM filings
        WHERE matter_id=? AND document_id IS NOT NULL AND status='ACTIVE'
        UNION
        SELECT document_id, title FROM orders
        WHERE matter_id=? AND document_id IS NOT NULL AND status='ACTIVE'
    """, (matter_id, matter_id)):
        add(row["document_id"], 30, row["title"] or "Filing or order")

    # 4. Everything else assigned to or linked to the matter.
    #
    # Early in a matter nothing is marked as an exhibit yet and no document is
    # linked to an issue, so the tiers above find nothing — which is exactly
    # when walking in with an empty phone would hurt most. Anything belonging to
    # the matter is worth having, at the lowest priority so it syncs last.
    for row in conn.execute("""
        SELECT DISTINCT d.id AS document_id, d.title FROM documents d
        LEFT JOIN document_matter_links l ON l.document_id = d.id
        WHERE (d.matter_id=? OR l.matter_id=?) AND d.status='ACTIVE'
        ORDER BY COALESCE(d.document_date, d.created_at)
    """, (matter_id, matter_id)):
        add(row["document_id"], 40, row["title"] or "Matter document")

    report = storage_report(conn)
    audit.record(conn, actor=actor, action="HEARING_PACK_BUILT",
                 target_table="matters", target_id=matter_id, matter_id=matter_id,
                 summary=f"{len(pinned)} document(s) pinned for hearing",
                 payload={"total_mb": report["total_mb"]})

    return {
        "matter": matter["title"],
        "pinned": len(pinned),
        "documents": pinned,
        "storage": report,
        "note": ("Exhibits sync first, then issue support, then filings — so the most "
                 "important material lands even if the connection drops."
                 if pinned else
                 "Nothing was pinned: this matter has no exhibits, issue-linked "
                 "documents, filings, or orders with a document attached yet."),
    }


# ---------------------------------------------------------------------------
# the offline bundle
# ---------------------------------------------------------------------------
def _read_text(text_path: str | None, limit: int = 400_000) -> str:
    if not text_path:
        return ""
    path = Path(text_path)
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def build_bundle(conn: sqlite3.Connection, matter_id: int | None = None) -> dict[str, Any]:
    """The payload the service worker caches. Self-contained and readable offline."""
    pins = list_pins(conn, matter_id)
    documents = []
    for p in pins:
        if p["sync_state"] == "UNAVAILABLE":
            continue
        document = conn.execute("SELECT * FROM documents WHERE id=?",
                                (p["document_id"],)).fetchone()
        if document is None:
            continue
        documents.append({
            "id": document["id"],
            "doc_uid": document["doc_uid"],
            "title": document["title"],
            "filename": document["original_filename"],
            "date": document["document_date"],
            "date_source": document["date_source"],
            "matter": p["matter_slug"],
            "extract": document["extract_line"],
            "text": _read_text(document["text_path"]) if p["include_text"] else "",
            "text_method": document["text_method"],
            "sha256": document["sha256"],
            "reason": p["reason"],
            "priority": p["priority"],
        })

    # Hearing-mode context travels with the documents: exhibits and questions are
    # useless without the scope statement and the rule elements.
    hearing: dict[str, Any] = {}
    if matter_id is not None:
        from . import views

        payload = views.hearing_mode(conn, matter_id)
        if payload:
            hearing = {
                "matter": payload["matter"]["title"],
                "scope_statement": payload["scope_statement"],
                "scope_objection": payload["scope_objection"],
                "opening_statement": payload["opening_statement"],
                "in_scope_issues": [
                    {"key": i["issue_key"], "title": i["title"],
                     "requested_finding": i["requested_finding"]}
                    for i in payload["in_scope_issues"]
                ],
                "out_of_scope_issues": [
                    {"key": i["issue_key"], "title": i["title"]}
                    for i in payload["out_of_scope_issues"]
                ],
                "rule_elements": payload["rule_elements"],
                "objections": payload["objections"],
                "exhibit_sequence": [
                    {"number": e["exhibit_number"], "title": e["title"],
                     "doc_uid": e["doc_uid"]}
                    for e in payload["exhibit_sequence"]
                ],
                "closing_outline": payload["closing_outline"],
                "witness_questions": payload["witness_questions"],
            }

    from . import preservation as pres

    return {
        "built_at": utcnow(),
        "matter_id": matter_id,
        "documents": documents,
        "hearing": hearing,
        "deadlines": pres.upcoming_deadlines(conn, matter_id, limit=25),
        "document_count": len(documents),
        "note": "Cached for offline reading. Every date shown carries its provenance.",
    }


def mark_synced(conn: sqlite3.Connection, document_ids: list[int]) -> int:
    if not document_ids:
        return 0
    marks = ",".join("?" for _ in document_ids)
    cur = conn.execute(
        f"UPDATE offline_pins SET sync_state='SYNCED', last_synced_at=? "
        f"WHERE document_id IN ({marks}) AND sync_state<>'UNAVAILABLE'",
        [utcnow(), *document_ids])
    return cur.rowcount or 0


# ---------------------------------------------------------------------------
# capture queue
# ---------------------------------------------------------------------------
def accept_capture(conn: sqlite3.Connection, config, *, client_uid: str,
                   filename: str, data: bytes, capture_kind: str = "PHOTO",
                   matter_id: int | None = None, captured_at: str | None = None,
                   device_note: str | None = None, latitude: float | None = None,
                   longitude: float | None = None,
                   actor: str = "phone") -> dict[str, Any]:
    """Take evidence captured on the device and put it into the record.

    `client_uid` is generated on the phone, so a retry after a dropped
    connection is recognised as the same capture rather than a second one.
    """
    from .db import atomic_write_bytes
    from .hashing import sha256_bytes
    from .ingest import ingest_path

    existing = conn.execute("SELECT * FROM capture_queue WHERE client_uid=?",
                            (client_uid,)).fetchone()
    if existing is not None:
        return {"client_uid": client_uid, "state": existing["state"],
                "duplicate": True,
                "note": "This capture was already received; the retry was ignored."}

    digest = sha256_bytes(data)
    safe = Path(filename).name or "capture"
    target = config.control_root / "captures" / digest[:2] / f"{digest}_{safe}"
    atomic_write_bytes(target, data)

    queue_id = insert(conn, "capture_queue", {
        "client_uid": client_uid,
        "matter_id": matter_id,
        "capture_kind": capture_kind.upper(),
        "captured_at": captured_at,
        "device_note": device_note,
        "latitude": latitude,
        "longitude": longitude,
        "filename": safe,
        "byte_size": len(data),
        "sha256": digest,
        "stored_path": str(target),
        "state": "RECEIVED",
    })

    # Run it through the ordinary pipeline. A capture is a document like any
    # other: hashed, deduped, extracted, and classified by the same code.
    try:
        result = ingest_path(config, conn, target, actor=actor, allow_control_path=True)
    except Exception as exc:
        conn.execute("UPDATE capture_queue SET state='FAILED', error=? WHERE id=?",
                     (f"{type(exc).__name__}: {exc}", queue_id))
        audit.record(conn, actor=actor, action="CAPTURE_INGEST_FAILED",
                     target_table="capture_queue", target_id=queue_id,
                     summary=safe, payload={"error": str(exc)})
        return {"client_uid": client_uid, "state": "FAILED", "error": str(exc),
                "note": "The capture is stored and visible; only the ingestion failed."}

    state = "DUPLICATE" if result.status == "duplicate" else (
        "INGESTED" if result.document_id else "FAILED")
    conn.execute("UPDATE capture_queue SET state=?, document_id=?, error=? WHERE id=?",
                 (state, result.document_id, result.error, queue_id))

    if result.document_id and captured_at:
        # The time it was taken is the fact that matters. Preserve it over any
        # date the extractor infers from the file.
        conn.execute(
            "UPDATE documents SET document_date=?, date_source='captured on device' "
            "WHERE id=? AND document_date IS NULL",
            (captured_at[:10], result.document_id))

    audit.record(conn, actor=actor, action="CAPTURE_RECEIVED",
                 target_table="capture_queue", target_id=queue_id, matter_id=matter_id,
                 summary=f"{capture_kind} {safe}",
                 payload={"sha256": digest, "state": state,
                          "captured_at": captured_at, "doc_uid": result.doc_uid})

    return {"client_uid": client_uid, "state": state, "doc_uid": result.doc_uid,
            "document_id": result.document_id, "duplicate": state == "DUPLICATE"}


def capture_log(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute("""
        SELECT c.*, d.doc_uid FROM capture_queue c
        LEFT JOIN documents d ON d.id = c.document_id
        ORDER BY c.id DESC LIMIT ?
    """, (limit,))]
