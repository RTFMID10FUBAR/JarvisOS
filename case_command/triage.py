"""Chronological triage.

The problem this solves: a large document set accumulated across several
competing folder schemes, with copies, drafts, and irrelevant material mixed in,
and no way to see it in order.

The answer is a single chronological list where every row shows:

    date  |  what it is (extracted verbatim)  |  matter  |  flags  |  decision

Two rules govern this module.

**The description is an extract, never a summary.** It is a line lifted verbatim
out of the document, with the locator it came from. No model writes it. A
generated summary could describe something the document does not say, and a
triage list is exactly where that error would be invisible.

**Triage never deletes.** IRRELEVANT and DUPLICATE are statuses on a document
that stays in the record, still searchable and still linked.
"""

from __future__ import annotations

import csv
import io
import re
import sqlite3
from pathlib import Path
from typing import Any

from . import audit
from .db import utcnow

TRIAGE_STATUSES = (
    "UNREVIEWED",      # not yet looked at
    "KEEP",            # real, relevant, stays
    "DUPLICATE",       # byte-identical or superseded copy of another document
    "SUPERSEDED",      # an earlier version of something later
    "IRRELEVANT",      # not related to any matter
    "ARCHIVE_PROPOSED",  # proposed for 99_ARCHIVE, awaiting a move decision
)

#: Document types worth naming on sight, in rough order of how much they matter
#: at a glance. Matched case-insensitively against a line of the document.
DOCUMENT_TYPE_PATTERNS = (
    (r"\bfinal order\b", "FINAL ORDER"),
    (r"\brecommended decision\b", "RECOMMENDED DECISION"),
    (r"\border\b", "ORDER"),
    (r"\bformal complaint\b", "FORMAL COMPLAINT"),
    (r"\bcomplaint\b", "COMPLAINT"),
    (r"\banswer\b", "ANSWER"),
    (r"\bmotion (?:to|for)\b", "MOTION"),
    (r"\bpetition\b", "PETITION"),
    (r"\bnotice of appeal\b", "NOTICE OF APPEAL"),
    (r"\bexceptions?\b", "EXCEPTIONS"),
    (r"\bwrit of mandamus\b|\bmandamus\b", "MANDAMUS"),
    (r"\bdeclaration\b|\baffidavit\b", "DECLARATION"),
    (r"\bcertificate of service\b", "CERTIFICATE OF SERVICE"),
    (r"\bfiling receipt\b|\bconfirmation number\b", "FILING RECEIPT"),
    (r"\bqualified written request\b", "QUALIFIED WRITTEN REQUEST"),
    (r"\bnotice of error\b", "NOTICE OF ERROR"),
    (r"\bnotice\b", "NOTICE"),
    (r"\btranscript\b", "TRANSCRIPT"),
    (r"\bexhibit\b", "EXHIBIT"),
    (r"\bletter\b|\bdear\b", "LETTER"),
    (r"\binvoice\b|\bstatement\b|\breceipt\b", "STATEMENT/RECEIPT"),
)

#: Lines that carry no information at a glance.
_NOISE = re.compile(
    r"^(page \d+|\d+|[-_=*\s]+|confidential|draft|\W{0,3})$", re.IGNORECASE)


def extract_line(text: str, pages: list[str] | None = None) -> tuple[str | None, str | None]:
    """Pull one informative line verbatim out of *text*.

    Returns ``(line, locator)``. Nothing is paraphrased: the line is returned
    exactly as it appears, so it can always be found in the source.
    """
    if not text or not text.strip():
        return (None, None)

    from .entities import HEADER_LINES

    lines = [(index, raw.strip()) for index, raw in enumerate(text.splitlines())]
    lines = [(i, line) for i, line in lines if line and not _NOISE.match(line)]
    if not lines:
        return (None, None)

    def locator_for(line_index: int) -> str:
        return f"p.1 line {line_index + 1}" if pages else f"line {line_index + 1}"

    # 1. A line in the header that names a document type wins outright. Court
    #    and agency filings put their title in the caption block, so the top of
    #    page one is where a document says what it is.
    header = [(i, line) for i, line in lines if i < HEADER_LINES]
    for source in (header, lines[:80]):
        for index, line in source:
            if len(line) > 200:
                continue
            lowered = line.lower()
            for pattern, _label in DOCUMENT_TYPE_PATTERNS:
                if re.search(pattern, lowered):
                    return (line[:180], locator_for(index))

    # 2. Otherwise the first substantive line.
    for index, line in lines:
        if len(line) >= 15:
            return (line[:180], locator_for(index))

    index, line = lines[0]
    return (line[:180], locator_for(index))


def document_type_hint(text: str, filename: str = "",
                       pages: list[str] | None = None) -> str | None:
    """A coarse label such as ORDER or MOTION, or None when nothing matches.

    The header is checked before the body: a filing names itself at the top, and
    a document that merely *discusses* an order should not be typed as one.
    """
    from .entities import header_zone

    for haystack in (f"{filename}\n{header_zone(text, pages)}".lower(),
                     f"{filename}\n{text[:4000]}".lower()):
        for pattern, label in DOCUMENT_TYPE_PATTERNS:
            if re.search(pattern, haystack):
                return label
    return None


def _read_text(text_path: str | None, limit: int = 20_000) -> str:
    if not text_path:
        return ""
    path = Path(text_path)
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def backfill_extracts(conn: sqlite3.Connection, *, force: bool = False) -> int:
    """Populate extract_line/extract_locator for documents that lack one."""
    sql = "SELECT id, text_path, original_filename FROM documents"
    if not force:
        sql += " WHERE extract_line IS NULL"
    updated = 0
    for row in conn.execute(sql).fetchall():
        text = _read_text(row["text_path"])
        line, locator = extract_line(text)
        if line is None:
            # No readable text: say so plainly rather than leaving it blank,
            # so an unreadable file is visible in the list instead of empty.
            line, locator = ("(no text could be extracted)", None)
        conn.execute(
            "UPDATE documents SET extract_line=?, extract_locator=? WHERE id=?",
            (line, locator, row["id"]))
        updated += 1
    return updated


def _date_for(row: dict[str, Any]) -> tuple[str | None, str]:
    """Best known date and where it came from.

    The provenance recorded at ingestion is preserved verbatim — "signature
    block" and "inferred (latest date in document)" are not the same claim, and
    flattening them to a generic label would hide which dates are guesses.
    """
    if row.get("filed_date"):
        return (row["filed_date"], "filed date (record)")
    if row.get("document_date"):
        return (row["document_date"], row.get("date_source") or "date in document")
    return (None, "no date found")


def chronology(conn: sqlite3.Connection, *, matter_id: int | None = None,
               folder: str | None = None, status: str | None = None,
               include_duplicates: bool = True,
               verification: str | None = None,
               ocr: bool | None = None,
               has_date: bool | None = None,
               keyword: str | None = None,
               no_matter: bool = False) -> dict[str, Any]:
    """Every document in date order, with flags for triage.

    Undated documents are returned in a separate list rather than being sorted
    to the top or dropped — an unknown date is not a date.

    ``has_date`` narrows to the dated list (True) or the undated list (False);
    left None, both are returned. ``keyword`` matches, case-insensitively,
    against the verbatim extract line only — never against a generated field,
    because there isn't one.
    """
    sql = ["""
        SELECT d.*, m.slug AS matter_slug, m.title AS matter_title,
               f.filing_status, f.proof_type,
               (SELECT COUNT(*) FROM document_copies c
                 WHERE c.document_id = d.id AND c.still_present = 1) AS copy_count
        FROM documents d
        LEFT JOIN matters m ON m.id = d.matter_id
        LEFT JOIN filings f ON f.document_id = d.id
        WHERE 1=1
    """]
    params: list[Any] = []
    if matter_id is not None:
        sql.append("AND (d.matter_id=? OR EXISTS (SELECT 1 FROM document_matter_links l "
                   "WHERE l.document_id=d.id AND l.matter_id=?))")
        params.extend([matter_id, matter_id])
    if folder:
        sql.append("AND d.folder=?")
        params.append(folder)
    if status:
        sql.append("AND d.triage_status=?")
        params.append(status)
    if verification:
        sql.append("AND d.verification_status=?")
        params.append(verification)
    if ocr is not None:
        sql.append("AND d.ocr_used=?")
        params.append(1 if ocr else 0)
    if no_matter:
        sql.append("AND d.matter_id IS NULL")

    rows = [dict(r) for r in conn.execute("\n".join(sql), params)]

    # Where each canonical document's extra physical copies live.
    copies_by_document: dict[int, list[dict[str, Any]]] = {}
    for copy in conn.execute(
        "SELECT * FROM document_copies WHERE still_present=1 ORDER BY path"
    ).fetchall():
        copies_by_document.setdefault(copy["document_id"], []).append(dict(copy))

    dated: list[dict[str, Any]] = []
    undated: list[dict[str, Any]] = []

    for row in rows:
        date, date_source = _date_for(row)
        copies = copies_by_document.get(row["id"], [])

        flags: list[str] = []
        if copies:
            flags.append(f"{len(copies)} COPY" + ("" if len(copies) == 1 else " LOCATIONS"))
        if row.get("duplicate_of_id"):
            flags.append("DUPLICATE")
        if (row.get("extraction_error")):
            flags.append("UNREADABLE")
        if row.get("ocr_used"):
            flags.append("OCR")
        if not row.get("classification_approved"):
            flags.append("MATTER UNCONFIRMED")
        if row.get("filing_status") and not row.get("proof_type"):
            flags.append("FILING UNPROVEN")
        if row.get("source_document_id"):
            flags.append("FROM CONTAINER")

        entry = {
            "id": row["id"],
            "doc_uid": row["doc_uid"],
            "title": row.get("title") or row["original_filename"],
            "date": date,
            "date_source": date_source,
            "extract": row.get("extract_line") or "(not yet extracted)",
            "extract_locator": row.get("extract_locator"),
            "filename": row["original_filename"],
            "folder": row["folder"],
            "matter": row.get("matter_slug"),
            "matter_title": row.get("matter_title"),
            "triage_status": row.get("triage_status") or "UNREVIEWED",
            "triage_note": row.get("triage_note"),
            "filing_status": row.get("filing_status"),
            "verification_status": row["verification_status"],
            "flags": flags,
            "copy_count": len(copies),
            "copies": [{"path": c["path"], "folder": c["folder"],
                        "disposition": c["disposition"]} for c in copies],
            "sha256_short": row["sha256"][:12],
            "storage_path": row["storage_path"],
            "byte_size": row["byte_size"],
            "ocr_used": bool(row.get("ocr_used")),
            "text_method": row.get("text_method"),
        }

        if not include_duplicates and copies:
            continue
        if keyword and keyword.lower() not in entry["extract"].lower():
            continue
        (dated if date else undated).append(entry)

    if has_date is True:
        undated = []
    elif has_date is False:
        dated = []

    dated.sort(key=lambda e: (e["date"], e["doc_uid"]))
    undated.sort(key=lambda e: e["filename"].lower())

    counts: dict[str, int] = {}
    for entry in dated + undated:
        counts[entry["triage_status"]] = counts.get(entry["triage_status"], 0) + 1

    return {
        "dated": dated,
        "undated": undated,
        "total": len(dated) + len(undated),
        "undated_count": len(undated),
        "duplicate_groups": sum(1 for copies in copies_by_document.values() if copies),
        "redundant_copies": sum(len(copies) for copies in copies_by_document.values()),
        "status_counts": counts,
        "unreviewed": counts.get("UNREVIEWED", 0),
        "filters": {"matter_id": matter_id, "folder": folder, "status": status,
                    "verification": verification, "ocr": ocr, "has_date": has_date,
                    "keyword": keyword, "no_matter": no_matter,
                    "hide_copies": ("1" if not include_duplicates else "")},
    }


def overview_counts(conn: sqlite3.Connection) -> dict[str, Any]:
    """Record-wide counts for the triage inspector — never a filtered subset.

    Every value here is a count with the same denominator (the whole document
    set), so it can be checked against the record. No percentage, no rating.
    """
    total = conn.execute("SELECT COUNT(*) c FROM documents").fetchone()["c"]
    no_date = conn.execute(
        "SELECT COUNT(*) c FROM documents WHERE filed_date IS NULL AND document_date IS NULL"
    ).fetchone()["c"]
    no_matter = conn.execute(
        "SELECT COUNT(*) c FROM documents WHERE matter_id IS NULL"
    ).fetchone()["c"]
    duplicate_groups = conn.execute(
        "SELECT COUNT(DISTINCT document_id) c FROM document_copies WHERE still_present=1"
    ).fetchone()["c"]
    redundant_copies = conn.execute(
        "SELECT COUNT(*) c FROM document_copies WHERE still_present=1"
    ).fetchone()["c"]
    extraction_failed = conn.execute(
        "SELECT COUNT(*) c FROM documents WHERE extraction_error IS NOT NULL"
    ).fetchone()["c"]
    return {
        "total": total,
        "no_date": no_date,
        "no_matter": no_matter,
        "duplicate_groups": duplicate_groups,
        "redundant_copies": redundant_copies,
        "extraction_failed": extraction_failed,
    }


def set_status(conn: sqlite3.Connection, document_id: int, status: str, *,
               reviewer: str = "jacob", note: str | None = None) -> dict[str, Any]:
    """Record a triage decision. Never deletes or moves the document."""
    status = status.upper()
    if status not in TRIAGE_STATUSES:
        raise ValueError(f"{status!r} is not a triage status. "
                         f"Allowed: {', '.join(TRIAGE_STATUSES)}")

    row = conn.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
    if row is None:
        raise ValueError(f"no document {document_id}")

    conn.execute(
        "UPDATE documents SET triage_status=?, triage_note=?, triage_by=?, triage_at=?, "
        "updated_at=? WHERE id=?",
        (status, note, reviewer, utcnow(), utcnow(), document_id))

    audit.record(conn, actor=reviewer, action="TRIAGE_DECISION",
                 target_table="documents", target_id=document_id,
                 matter_id=row["matter_id"],
                 summary=f"{row['doc_uid']} -> {status}",
                 payload={"previous": row["triage_status"], "note": note})

    return {
        "document_id": document_id, "doc_uid": row["doc_uid"], "triage_status": status,
        "note": ("Recorded. The document remains in the record and stays searchable. "
                 "Nothing was moved or deleted."),
    }


def set_status_bulk(conn: sqlite3.Connection, document_ids: list[int], status: str, *,
                    reviewer: str = "jacob", note: str | None = None) -> dict[str, Any]:
    """Apply one triage decision to many documents.

    Each document is written through :func:`set_status`, so a bulk decision is
    audit-logged exactly the way a single-document decision is — one entry per
    document, not one summary entry standing in for all of them. A status
    rejected up front stops the whole batch before anything is written; a
    document id that turns out not to exist is skipped and reported, so one
    bad id in a batch does not silently swallow the rest.
    """
    status = status.upper()
    if status not in TRIAGE_STATUSES:
        raise ValueError(f"{status!r} is not a triage status. "
                         f"Allowed: {', '.join(TRIAGE_STATUSES)}")

    updated: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for document_id in document_ids:
        try:
            updated.append(set_status(conn, document_id, status, reviewer=reviewer, note=note))
        except ValueError as exc:
            errors.append({"document_id": document_id, "error": str(exc)})

    return {
        "status": status,
        "requested": len(document_ids),
        "updated_count": len(updated),
        "updated": updated,
        "errors": errors,
    }


def copy_locations(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Every known redundant physical copy, grouped by the document it copies.

    This is the "what is a copy" answer: one canonical document, and the other
    places the identical bytes are sitting.
    """
    groups: dict[int, dict[str, Any]] = {}
    for row in conn.execute("""
        SELECT c.*, d.doc_uid, d.storage_path AS canonical_path, d.original_filename,
               d.extract_line, d.document_date
        FROM document_copies c
        JOIN documents d ON d.id = c.document_id
        WHERE c.still_present = 1
        ORDER BY d.doc_uid, c.path
    """).fetchall():
        entry = groups.setdefault(row["document_id"], {
            "document_id": row["document_id"],
            "doc_uid": row["doc_uid"],
            "date": row["document_date"],
            "what_it_is": row["extract_line"],
            "canonical_path": row["canonical_path"],
            "copies": [],
        })
        entry["copies"].append({
            "path": row["path"], "folder": row["folder"],
            "disposition": row["disposition"], "byte_size": row["byte_size"],
            "discovered_at": row["discovered_at"],
        })
    return list(groups.values())


def propose_copy_archive(conn: sqlite3.Connection, *,
                         reviewer: str = "system") -> dict[str, Any]:
    """Mark redundant copy locations as ARCHIVE_PROPOSED. Proposes only.

    Nothing is moved and nothing is deleted. The canonical document keeps its
    own path; only the extra locations are proposed for 99_ARCHIVE, and a human
    still decides. A copy already given a disposition is left alone.
    """
    proposed = 0
    for row in conn.execute(
        "SELECT id, path, document_id FROM document_copies "
        "WHERE still_present=1 AND disposition='UNREVIEWED'"
    ).fetchall():
        conn.execute(
            "UPDATE document_copies SET disposition='ARCHIVE_PROPOSED', notes=? WHERE id=?",
            ("Redundant copy of the canonical document. Proposed for 99_ARCHIVE. "
             "Not moved.", row["id"]))
        proposed += 1

    if proposed:
        audit.record(conn, actor=reviewer, action="COPY_ARCHIVE_PROPOSED",
                     summary=f"{proposed} redundant copy location(s) proposed for archive",
                     payload={"moved": False, "deleted": False})

    return {
        "proposed": proposed,
        "moved": 0,
        "deleted": 0,
        "note": ("Proposal only. Run `migrate plan` then `migrate execute --approve` "
                 "to actually relocate anything, which writes a rollback manifest first."),
    }


def to_csv(report: dict[str, Any]) -> str:
    """Export the chronology as CSV, for working through it in a spreadsheet."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "date", "date_source", "doc_id", "what_it_is_extract", "extract_locator",
        "filename", "folder", "matter", "triage_status", "filing_status",
        "flags", "copies", "sha256", "path",
    ])
    for entry in report["dated"] + report["undated"]:
        writer.writerow([
            entry["date"] or "", entry["date_source"], entry["doc_uid"],
            entry["extract"], entry["extract_locator"] or "",
            entry["filename"], entry["folder"], entry["matter"] or "",
            entry["triage_status"], entry["filing_status"] or "",
            "; ".join(entry["flags"]), entry["copy_count"],
            entry["sha256_short"], entry["storage_path"],
        ])
    return buffer.getvalue()


def format_table(report: dict[str, Any], width: int = 62) -> str:
    """Plain-text chronological table for the terminal."""
    lines = [
        f"{report['total']} document(s) · {report['unreviewed']} unreviewed · "
        f"{report['duplicate_groups']} duplicate group(s) · "
        f"{report['undated_count']} undated",
        "",
        f"{'DATE':<12} {'ID':<14} {'WHAT IT IS':<{width}} {'MATTER':<14} FLAGS",
        "-" * (12 + 14 + width + 14 + 20),
    ]
    for entry in report["dated"]:
        lines.append(
            f"{entry['date']:<12} {entry['doc_uid']:<14} "
            f"{entry['extract'][:width]:<{width}} "
            f"{(entry['matter'] or '—')[:13]:<14} "
            f"{','.join(entry['flags'])}"
        )
    if report["undated"]:
        lines.append("")
        lines.append(f"--- NO DATE FOUND ({len(report['undated'])}) "
                     "— an unknown date is not a date, so these are listed separately ---")
        for entry in report["undated"]:
            lines.append(
                f"{'—':<12} {entry['doc_uid']:<14} "
                f"{entry['extract'][:width]:<{width}} "
                f"{(entry['matter'] or '—')[:13]:<14} "
                f"{','.join(entry['flags'])}"
            )
    return "\n".join(lines)
