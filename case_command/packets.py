"""Token-efficient context packets.

Whole case files are never shipped to a model. A Fleet request receives only:
the canonical issue summary, the relevant facts, the relevant sources, the
specific task, and the expected output schema.

Retrieval is available by matter, issue, date range, document ID, event ID,
authority, and evidence type. Extracted text is read from the on-disk cache
keyed by content hash, so nothing is re-extracted, re-OCR'd, or re-summarized.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .fleet import ALLOWED_JOBS, REQUIRED_RESPONSE_FIELDS

#: Hard cap on characters of source text placed in one packet.
DEFAULT_TEXT_BUDGET = 12_000
#: Per-document excerpt cap, so one long filing cannot crowd out the rest.
PER_DOCUMENT_CHARS = 3_000


def _row_dicts(rows) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


def _load_text(text_path: str | None, limit: int) -> str:
    if not text_path:
        return ""
    path = Path(text_path)
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# retrieval
# ---------------------------------------------------------------------------
def by_matter(conn: sqlite3.Connection, matter_id: int, limit: int = 50) -> list[dict[str, Any]]:
    return _row_dicts(conn.execute(
        """
        SELECT DISTINCT d.* FROM documents d
        LEFT JOIN document_matter_links l ON l.document_id = d.id
        WHERE (d.matter_id=? OR l.matter_id=?) AND d.status='ACTIVE'
        ORDER BY COALESCE(d.document_date, d.created_at) DESC LIMIT ?
        """,
        (matter_id, matter_id, limit),
    ))


def by_issue(conn: sqlite3.Connection, issue_id: int) -> list[dict[str, Any]]:
    return _row_dicts(conn.execute(
        """
        SELECT d.* FROM documents d
        JOIN issue_links l ON l.linked_id = d.id AND l.linked_type='document'
        WHERE l.issue_id=? AND d.status='ACTIVE'
        """,
        (issue_id,),
    ))


def by_date_range(conn: sqlite3.Connection, start: str, end: str,
                  matter_id: int | None = None) -> list[dict[str, Any]]:
    sql = ("SELECT * FROM documents WHERE document_date BETWEEN ? AND ? AND status='ACTIVE'")
    params: list[Any] = [start, end]
    if matter_id is not None:
        sql += " AND matter_id=?"
        params.append(matter_id)
    return _row_dicts(conn.execute(sql + " ORDER BY document_date", params))


def by_doc_uid(conn: sqlite3.Connection, doc_uid: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM documents WHERE doc_uid=?", (doc_uid,)).fetchone()
    return dict(row) if row else None


def by_event(conn: sqlite3.Connection, event_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    return dict(row) if row else None


def by_authority(conn: sqlite3.Connection, citation: str) -> list[dict[str, Any]]:
    return _row_dicts(conn.execute(
        "SELECT * FROM authorities WHERE citation LIKE ? OR title LIKE ?",
        (f"%{citation}%", f"%{citation}%"),
    ))


def by_evidence_type(conn: sqlite3.Connection, evidence_type: str,
                     matter_id: int | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM evidence WHERE evidence_type=? AND status='ACTIVE'"
    params: list[Any] = [evidence_type]
    if matter_id is not None:
        sql += " AND matter_id=?"
        params.append(matter_id)
    return _row_dicts(conn.execute(sql, params))


def search(conn: sqlite3.Connection, query: str, limit: int = 25) -> list[dict[str, Any]]:
    """Full-text search over cached document text. Never re-reads originals."""
    try:
        rows = conn.execute(
            """
            SELECT f.doc_uid, f.title, snippet(document_fts, 2, '[', ']', '…', 20) AS excerpt
            FROM document_fts f WHERE document_fts MATCH ? LIMIT ?
            """,
            (query, limit),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        return [{"error": f"search failed: {exc}"}]
    return _row_dicts(rows)


# ---------------------------------------------------------------------------
# packet assembly
# ---------------------------------------------------------------------------
def issue_summary(conn: sqlite3.Connection, issue_id: int) -> dict[str, Any]:
    """The canonical issue summary: the only issue context Fleet ever receives."""
    issue = conn.execute("SELECT * FROM issues WHERE id=?", (issue_id,)).fetchone()
    if issue is None:
        return {}
    return {
        "issue_key": issue["issue_key"],
        "title": issue["title"],
        "status": issue["status"],
        "legal_element": issue["legal_element"],
        "boundary_classification": issue["boundary_classification"],
        "hearing_scope": issue["hearing_scope"],
        "opponent_defense": issue["opponent_defense"],
        "missing_proof": issue["missing_proof"],
        "requested_finding": issue["requested_finding"],
        "requested_relief": issue["requested_relief"],
        "appeal_standard": issue["appeal_standard"],
        "risk_rating": issue["risk_rating"],
        "verification_status": issue["verification_status"],
    }


def relevant_facts(conn: sqlite3.Connection, issue_id: int | None,
                   matter_id: int | None, limit: int = 25) -> list[dict[str, Any]]:
    if issue_id:
        rows = conn.execute(
            """
            SELECT f.id, f.title, f.statement, f.fact_date, f.verification_status,
                   f.source_document_id, f.source_page_or_paragraph
            FROM facts f
            JOIN issue_links l ON l.linked_id=f.id AND l.linked_type='fact'
            WHERE l.issue_id=? AND f.status='ACTIVE' LIMIT ?
            """,
            (issue_id, limit),
        ).fetchall()
        if rows:
            return _row_dicts(rows)
    if matter_id is None:
        return []
    return _row_dicts(conn.execute(
        """
        SELECT id, title, statement, fact_date, verification_status,
               source_document_id, source_page_or_paragraph
        FROM facts WHERE matter_id=? AND status='ACTIVE'
        ORDER BY COALESCE(fact_date, created_at) LIMIT ?
        """,
        (matter_id, limit),
    ))


OUTPUT_SCHEMA = {
    "type": "object",
    "required": list(REQUIRED_RESPONSE_FIELDS),
    "properties": {
        "job_id": {"type": "string"},
        "matter_id": {"type": ["integer", "null"]},
        "documents_reviewed": {"type": "array", "items": {"type": "string"}},
        "proposed_facts": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["statement", "verification_status"],
                "properties": {
                    "title": {"type": "string"},
                    "statement": {"type": "string"},
                    "fact_date": {"type": ["string", "null"]},
                    "verification_status": {"type": "string"},
                    "source_doc_uid": {"type": ["string", "null"]},
                    "source_page_or_paragraph": {"type": ["string", "null"]},
                },
            },
        },
        "proposed_issue_updates": {"type": "array", "items": {"type": "object"}},
        "conflicts_found": {"type": "array", "items": {"type": "object"}},
        "missing_sources": {"type": "array", "items": {"type": "object"}},
        "defense_attacks": {"type": "array", "items": {"type": "object"}},
        "recommended_repairs": {"type": "array", "items": {"type": "object"}},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "citations": {"type": "array", "items": {"type": "string"}},
        "approval_required": {"const": True},
    },
}


def build_packet(conn: sqlite3.Connection, *, task: str, job_type: str,
                 matter_id: int | None = None, issue_id: int | None = None,
                 doc_uids: list[str] | None = None,
                 text_budget: int = DEFAULT_TEXT_BUDGET) -> dict[str, Any]:
    """Assemble the smallest packet that can answer *task*.

    Raises ValueError for a job type outside the allowed set, so an out-of-scope
    Fleet request cannot be constructed in the first place.
    """
    if job_type not in ALLOWED_JOBS:
        raise ValueError(
            f"{job_type!r} is not an allowed Fleet job. Allowed: {', '.join(ALLOWED_JOBS)}"
        )

    if issue_id and matter_id is None:
        row = conn.execute("SELECT matter_id FROM issues WHERE id=?", (issue_id,)).fetchone()
        matter_id = row["matter_id"] if row else None

    matter = None
    if matter_id:
        row = conn.execute(
            "SELECT id, slug, title, caption, case_number, forum, posture, "
            "boundary_date, boundary_label FROM matters WHERE id=?", (matter_id,)
        ).fetchone()
        matter = dict(row) if row else None

    # Sources: explicitly named documents first, then the matter's most recent.
    documents: list[dict[str, Any]] = []
    if doc_uids:
        for uid in doc_uids:
            doc = by_doc_uid(conn, uid)
            if doc:
                documents.append(doc)
    elif matter_id:
        documents = by_matter(conn, matter_id, limit=8)

    sources: list[dict[str, Any]] = []
    spent = 0
    for doc in documents:
        if spent >= text_budget:
            break
        allowance = min(PER_DOCUMENT_CHARS, text_budget - spent)
        excerpt = _load_text(doc.get("text_path"), allowance)
        spent += len(excerpt)
        sources.append({
            "doc_uid": doc["doc_uid"],
            "title": doc["title"],
            "document_date": doc.get("document_date"),
            "sha256": doc["sha256"],
            "text_method": doc.get("text_method"),
            "text_confidence": doc.get("text_confidence"),
            "page_count": doc.get("page_count"),
            "excerpt": excerpt,
            "excerpt_is_partial": bool(doc.get("text_chars") or 0) > len(excerpt),
        })

    packet = {
        "task": task,
        "job_type": job_type,
        "matter": matter,
        "issue": issue_summary(conn, issue_id) if issue_id else None,
        "facts": relevant_facts(conn, issue_id, matter_id),
        "sources": sources,
        "expected_output_schema": OUTPUT_SCHEMA,
        "rules": [
            "Return every required field, even when empty.",
            "Never mark a fact verified without a source document and a page or "
            "paragraph locator.",
            "Never propose deleting an issue or merging matters.",
            "Never treat folder presence as proof that a document was filed.",
            "Never decide that an argument is abandoned.",
            "approval_required must be true.",
        ],
        "budget": {"text_chars_used": spent, "text_chars_allowed": text_budget},
    }
    return packet


def packet_size(packet: dict[str, Any]) -> int:
    """Serialized size in characters — the number that actually drives cost."""
    return len(json.dumps(packet, default=str))
