"""Filing Studio — prepares a filing against the record without ever sending it.

This module answers five questions about a matter's current filing posture,
each backed by a table that already exists in the record:

    PROCEDURAL PATH MATRIX  the same options atlas.build_atlas evaluates,
                             tabulated: can it be prepared now, what named
                             prerequisite is missing, what deadline the record
                             holds, what it preserves, what authority a human
                             must still confirm.
    STAGED PACKET           the documents assigned to a draft filing — a
                             `filings` row with filing_status='DRAFT' — with
                             whatever role the record holds for each one.
    SMART CHECKLIST         the five anti-omission checks in checks.py, run
                             for real against this matter's record and, where
                             a draft document's extracted text exists, against
                             that text.
    DRAFT QUEUE             every filing for the matter that has not reached
                             a confirmed, rejected, or superseded resting
                             state.
    STATUS TRACKER          the full filing lifecycle for the matter, with
                             the proof behind any confirmed status — and a
                             loud flag on any confirmed status that has none.

**What this module will not do.** It has no function that files, serves, or
transmits anything — there is no such function to call, deliberately. It
never predicts how a filing will be received: no likelihood, no grant/deny
forecast, no score. A path is available or it names what blocks it. A filing
is confirmed with proof, or it is flagged. Folder presence is never proof of
filing; the FILING_STATUSES/CONFIRMED_FILING_STATUSES/PROOF_TYPES vocabulary
and the database CHECK constraint that enforces this live in db.py.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from . import atlas, checks
from .db import CONFIRMED_FILING_STATUSES, FILING_STATUSES, PROOF_TYPES

#: Filing statuses that mean a filing has not reached a confirmed, rejected,
#: or superseded resting state — still moving through preparation.
UNFILED_STATUSES = ("DRAFT", "READY_FOR_REVIEW", "APPROVED", "SENT", "FILED_UNCONFIRMED")

#: Bound on how much extracted text is read for the completeness check, so one
#: enormous filing cannot blow up the page.
MAX_DRAFT_TEXT_CHARS = 200_000


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(sql, params)]


def _one(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> dict[str, Any] | None:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# 1. procedural path matrix
# ---------------------------------------------------------------------------
def path_matrix(conn: sqlite3.Connection, matter_id: int) -> list[dict[str, Any]]:
    """Every path atlas.build_atlas can evaluate, flattened into table rows.

    This reuses atlas.build_atlas rather than re-deriving prerequisites, so
    the Path Atlas and Filing Studio can never disagree about what blocks a
    path. There is deliberately no ranking column beyond deadline pressure —
    see atlas.py for why a probability or a likely-outcome column is refused.
    """
    data = atlas.build_atlas(conn, matter_id)
    if not data:
        return []
    rows = list(data["available"]) + list(data["blocked"])

    def sort_key(p: dict[str, Any]) -> tuple[int, int, str]:
        if not p["available"]:
            return (0, 0, p["label"])
        days = p["days_left"]
        return (1, days if days is not None else 10_000, p["label"])

    return sorted(rows, key=sort_key)


# ---------------------------------------------------------------------------
# 2. staged packet
# ---------------------------------------------------------------------------
def staged_packet(conn: sqlite3.Connection, matter_id: int) -> list[dict[str, Any]]:
    """Documents assigned to a draft filing for this matter.

    A draft filing is a `filings` row with filing_status='DRAFT'. Its role
    (motion, declaration, exhibit, certificate of service, or anything else)
    comes straight from filing_type — a free-text field already in the
    schema. When it is unset, that is shown as a gap, not guessed at.
    """
    return _rows(conn, """
        SELECT f.id AS filing_id, f.title AS filing_title, f.filing_type,
               f.filed_by, f.filing_status, f.created_at, f.updated_at,
               f.notes,
               d.id AS document_id, d.doc_uid, d.title AS document_title,
               d.folder, d.triage_status
        FROM filings f
        LEFT JOIN documents d ON d.id = f.document_id
        WHERE f.matter_id=? AND f.filing_status='DRAFT' AND f.status='ACTIVE'
        ORDER BY (f.filing_type IS NULL), f.filing_type, f.id
    """, (matter_id,))


# ---------------------------------------------------------------------------
# 3. smart checklist
# ---------------------------------------------------------------------------
def _draft_text(conn: sqlite3.Connection,
                 matter_id: int) -> tuple[str, dict[str, Any] | None]:
    """Extracted text of the most recently touched staged draft document.

    Returns the text (possibly empty) and the document record it came from,
    so the caller can say plainly which document — if any — the completeness
    check actually read. No text is invented when none is on record.
    """
    doc = _one(conn, """
        SELECT d.* FROM filings f JOIN documents d ON d.id = f.document_id
        WHERE f.matter_id=? AND f.filing_status='DRAFT' AND f.status='ACTIVE'
              AND d.text_path IS NOT NULL
        ORDER BY f.updated_at DESC LIMIT 1
    """, (matter_id,))
    if doc is None:
        return "", None
    path = Path(doc["text_path"])
    if not path.exists():
        return "", doc
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:MAX_DRAFT_TEXT_CHARS]
    except OSError:
        return "", doc
    return text, doc


def smart_checklist(conn: sqlite3.Connection, matter_id: int) -> dict[str, Any]:
    """Run the real anti-omission checks for this matter.

    Every finding here is produced by checks.py against the actual record —
    nothing on this screen writes its own checklist items.
    """
    draft_text, draft_document = _draft_text(conn, matter_id)
    report = checks.run_all(conn, matter_id, draft_text)
    return {
        "ok": report.ok,
        "blockers": [f.to_dict() for f in report.blockers],
        "advisory": [f.to_dict() for f in report.findings if f.severity != "BLOCKER"],
        "finding_count": len(report.findings),
        "draft_document": draft_document,
        "draft_text_used": bool(draft_text),
    }


# ---------------------------------------------------------------------------
# 4. draft queue
# ---------------------------------------------------------------------------
def draft_queue(conn: sqlite3.Connection, matter_id: int) -> list[dict[str, Any]]:
    """Filings for this matter still moving through preparation.

    "Draft/unfiled" means every status before a confirmed filing and short of
    REJECTED or SUPERSEDED — see UNFILED_STATUSES above.
    """
    placeholders = ",".join("?" * len(UNFILED_STATUSES))
    return _rows(conn, f"""
        SELECT f.*, d.doc_uid, d.title AS document_title
        FROM filings f LEFT JOIN documents d ON d.id = f.document_id
        WHERE f.matter_id=? AND f.status='ACTIVE' AND f.filing_status IN ({placeholders})
        ORDER BY f.updated_at DESC
    """, (matter_id, *UNFILED_STATUSES))


# ---------------------------------------------------------------------------
# 5. status tracker
# ---------------------------------------------------------------------------
def status_tracker(conn: sqlite3.Connection, matter_id: int) -> list[dict[str, Any]]:
    """The full filing lifecycle for the matter, stage by stage.

    A filing that claims FILED_CONFIRMED, DOCKETED, or ENTERED without proof
    is flagged here, never hidden. The database CHECK constraint (see
    migrations/0001_initial.sql) already blocks writing such a row through
    this application; this flag exists for any record that reaches the
    database by another path.
    """
    rows = _rows(conn, """
        SELECT f.*, d.doc_uid, d.title AS document_title
        FROM filings f LEFT JOIN documents d ON d.id = f.document_id
        WHERE f.matter_id=? AND f.status='ACTIVE'
        ORDER BY COALESCE(f.filed_date, f.updated_at) DESC
    """, (matter_id,))
    order = {status: i for i, status in enumerate(FILING_STATUSES)}
    for row in rows:
        row["stage_index"] = order.get(row["filing_status"], len(FILING_STATUSES) - 1)
        row["stage_count"] = len(FILING_STATUSES)
        row["is_confirmed"] = row["filing_status"] in CONFIRMED_FILING_STATUSES
        row["has_proof"] = bool(row["proof_type"]) and bool(
            row["proof_document_id"] or row["proof_reference"])
        row["unproven_confirmation"] = row["is_confirmed"] and not row["has_proof"]
    return rows


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------
def build_filing_studio(conn: sqlite3.Connection, matter_id: int) -> dict[str, Any]:
    """Assemble every panel Filing Studio needs for one matter."""
    matter = _one(conn, "SELECT * FROM matters WHERE id=?", (matter_id,))
    if matter is None:
        return {}

    tracker = status_tracker(conn, matter_id)
    matrix = path_matrix(conn, matter_id)
    return {
        "matter": matter,
        "path_matrix": matrix,
        "path_counts": {
            "available": sum(1 for p in matrix if p["available"]),
            "blocked": sum(1 for p in matrix if not p["available"]),
        },
        "staged_packet": staged_packet(conn, matter_id),
        "checklist": smart_checklist(conn, matter_id),
        "draft_queue": draft_queue(conn, matter_id),
        "status_tracker": tracker,
        "unproven_count": sum(1 for f in tracker if f["unproven_confirmation"]),
        "filing_statuses": FILING_STATUSES,
        "confirmed_statuses": CONFIRMED_FILING_STATUSES,
        "proof_types": PROOF_TYPES,
        "disclaimer": (
            "Filing Studio prepares a filing against the record. It has no "
            "affordance to file, serve, or send anything, and a status shows "
            "as confirmed only when the record already holds docket proof."
        ),
    }
