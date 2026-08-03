"""Ingestion pipeline.

One document goes through these steps, in this order:

    1. SHA-256                    8. classify the matter
    2. duplicate detection        9. identify parties, court, case number, dates,
    3. file type detection           deadlines, judges, ALJs, counsel, rules, exhibits, relief
    4. preserve the original     10. propose timeline events
    5. extract text              11. propose issue links
    6. collect metadata          12. flag conflicts and unknowns
    7. assign a document ID      13. require approval before anything disputed
                                     enters the canonical record

The original file is opened read-only and never moved, renamed, or rewritten.
Everything the pipeline produces is either a cache entry under .case_command or
a database row marked as an unapproved proposal.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import audit, entities as ent
from .classify import Classification, classify_document, unmatched_folder_default
from .config import Config, INBOX, SHARED_EVIDENCE
from .db import atomic_write_text, insert, utcnow
from .extract import ExtractContext, ExtractionResult, detect_kind, extract_file, MIME_BY_KIND
from .hashing import folder_of, sha256_bytes, sha256_file

#: Bumped when extraction or entity logic changes in a way that invalidates
#: cached results. Documents at an older version are re-analyzed; unchanged
#: documents at the current version are never re-extracted or re-OCR'd.
ANALYSIS_VERSION = 1


@dataclass
class IngestResult:
    """What happened to one file. Always returned, even on failure."""

    path: str
    status: str                      # ingested | duplicate | unchanged | failed
    document_id: int | None = None
    doc_uid: str | None = None
    sha256: str | None = None
    duplicate_of: str | None = None
    classification: dict[str, Any] | None = None
    extraction: dict[str, Any] | None = None
    entities: dict[str, Any] = field(default_factory=dict)
    proposed_events: int = 0
    proposed_links: int = 0
    unknowns: int = 0
    approvals_opened: int = 0
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    nested: list["IngestResult"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "path": self.path,
            "status": self.status,
            "document_id": self.document_id,
            "doc_uid": self.doc_uid,
            "sha256": self.sha256,
            "duplicate_of": self.duplicate_of,
            "classification": self.classification,
            "extraction": self.extraction,
            "entity_counts": {k: len(v) for k, v in self.entities.items()},
            "proposed_events": self.proposed_events,
            "proposed_links": self.proposed_links,
            "unknowns": self.unknowns,
            "approvals_opened": self.approvals_opened,
            "error": self.error,
            "warnings": self.warnings,
        }
        if self.nested:
            data["nested"] = [n.to_dict() for n in self.nested]
        return data


def next_doc_uid(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()
    return f"CC-DOC-{int(row['n']) + 1:06d}"


def find_by_hash(conn: sqlite3.Connection, digest: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM documents WHERE sha256=?", (digest,)).fetchone()


def _text_cache_path(config: Config, digest: str) -> Path:
    # Shard by the first two hex characters so the directory stays navigable.
    return config.text_dir / digest[:2] / f"{digest}.txt"


def _cached_extraction(conn: sqlite3.Connection, digest: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM text_cache WHERE sha256=? AND analysis_version>=?",
        (digest, ANALYSIS_VERSION),
    ).fetchone()


def _store_text(config: Config, conn: sqlite3.Connection, digest: str,
                result: ExtractionResult) -> Path:
    """Write extracted text to the cache. Atomic; never overwrites in place."""
    path = _text_cache_path(config, digest)
    payload = result.text
    if result.pages:
        # Page markers let a locator like "p.3" be resolved back to real text.
        payload = "\n".join(
            f"\n<<<PAGE {i + 1}>>>\n{page}" for i, page in enumerate(result.pages)
        )
    atomic_write_text(path, payload)
    conn.execute(
        """
        INSERT INTO text_cache (sha256, text_path, method, confidence, char_count,
                                page_count, analysis_version)
        VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(sha256) DO UPDATE SET
            text_path=excluded.text_path, method=excluded.method,
            confidence=excluded.confidence, char_count=excluded.char_count,
            page_count=excluded.page_count, analysis_version=excluded.analysis_version
        """,
        (digest, str(path), result.method, result.confidence, len(result.text),
         result.page_count, ANALYSIS_VERSION),
    )
    return path


def _open_approval(conn: sqlite3.Connection, *, kind: str, question: str,
                   target_table: str, target_id: int, matter_id: int | None,
                   options: list[str] | None = None,
                   proposed: str | None = None) -> int:
    return insert(conn, "approvals", {
        "kind": kind,
        "target_table": target_table,
        "target_id": target_id,
        "matter_id": matter_id,
        "question": question,
        "options": json.dumps(options) if options else None,
        "proposed": proposed,
        "state": "OPEN",
    })


def _matter_for_folder(conn: sqlite3.Connection, folder: str) -> sqlite3.Row | None:
    """Default matter for a folder, used only as a *proposal*.

    When a folder holds several separate matters (PSC/AEP holds six), no
    automatic assignment is made — the human is asked which one.
    """
    rows = conn.execute(
        "SELECT * FROM matters WHERE folder=? AND status='ACTIVE' ORDER BY id", (folder,)
    ).fetchall()
    return rows[0] if len(rows) == 1 else None


def _matters_in_folder(conn: sqlite3.Connection, folder: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM matters WHERE folder=? AND status='ACTIVE' ORDER BY id", (folder,)
    ).fetchall()


def _boundary_classification(conn: sqlite3.Connection, matter_id: int | None,
                             doc_date: str | None) -> str:
    """Classify a document against its matter's boundary date.

    Post-boundary conduct is never labelled as relitigation of a decided issue;
    it is flagged as new conduct for a human to confirm.
    """
    if not matter_id or not doc_date:
        return "UNKNOWN"
    row = conn.execute("SELECT boundary_date FROM matters WHERE id=?", (matter_id,)).fetchone()
    if not row or not row["boundary_date"]:
        return "NOT_APPLICABLE"
    if doc_date > row["boundary_date"]:
        return "POST_FINAL_ORDER_NEW_CONDUCT"
    return "PRIOR_EVIDENCE_FOR_LIMITED_PURPOSE"


def ingest_path(config: Config, conn: sqlite3.Connection, path: Path, *,
                actor: str = "ingest", allow_ocr: bool = True,
                depth: int = 0, allow_control_path: bool = False) -> IngestResult:
    """Run the full pipeline for one file. Never modifies the original.

    `allow_control_path` is set only when ingesting a container member that Case
    Command itself materialized under .case_command. Files that merely happen to
    live in the control tree are never ingested as evidence.
    """
    path = Path(path)
    result = IngestResult(path=str(path), status="failed")

    if not path.exists():
        result.error = "file does not exist"
        return result
    if config.is_control_path(path) and not allow_control_path:
        result.status = "skipped"
        result.error = "path is inside the .case_command control tree"
        return result

    # --- 1. hash -----------------------------------------------------------
    try:
        digest = sha256_file(path)
    except OSError as exc:
        result.error = f"cannot read file: {exc}"
        audit.record(conn, actor=actor, action="INGEST_FAILED", summary=str(path),
                     payload={"error": result.error})
        return result
    result.sha256 = digest

    # --- 2. duplicate detection -------------------------------------------
    existing = find_by_hash(conn, digest)
    if existing is not None:
        if existing["storage_path"] == str(path):
            result.status = "unchanged"
            result.document_id = existing["id"]
            result.doc_uid = existing["doc_uid"]
            return result
        result.status = "duplicate"
        result.document_id = existing["id"]
        result.doc_uid = existing["doc_uid"]
        result.duplicate_of = existing["doc_uid"]
        # Record where the copy physically lives. Without this the extra
        # location exists only in the audit log, and the triage list cannot
        # answer "where are the copies?" — which is how the wrong copy gets
        # deleted during a cleanup.
        conn.execute(
            "INSERT INTO document_copies (document_id, path, folder, sha256, byte_size) "
            "VALUES (?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET still_present=1",
            (existing["id"], str(path), folder_of(config, path) or "",
             digest, path.stat().st_size),
        )
        # A byte-identical file in a second location is a duplicate, not a new
        # document. Archiving it is proposed, never performed.
        approval_id = _open_approval(
            conn, kind="duplicate_archive",
            question=(f"{path.name} is byte-identical to {existing['doc_uid']} "
                      f"({existing['storage_path']}). Archive this copy to 99_ARCHIVE?"),
            target_table="documents", target_id=existing["id"],
            matter_id=existing["matter_id"],
            options=["Archive the duplicate", "Keep both", "Not a duplicate"],
            proposed="Archive the duplicate",
        )
        result.approvals_opened = 1
        audit.record(conn, actor=actor, action="DUPLICATE_DETECTED",
                     target_table="documents", target_id=existing["id"],
                     summary=f"{path} duplicates {existing['doc_uid']}",
                     payload={"sha256": digest, "approval_id": approval_id})
        return result

    # --- 3. file type ------------------------------------------------------
    kind, _handler = detect_kind(path)
    folder = folder_of(config, path) or INBOX

    # --- 4. the original is preserved: we only ever read it ----------------
    stat = path.stat()

    # --- 5. extract text (cache-first; unchanged content is never re-OCR'd) -
    cached = _cached_extraction(conn, digest)
    if cached is not None:
        text_path = Path(cached["text_path"])
        raw_text = text_path.read_text(encoding="utf-8", errors="replace") if text_path.exists() else ""
        extraction = ExtractionResult(
            text=raw_text, method=cached["method"], confidence=cached["confidence"],
            page_count=cached["page_count"],
        )
        result.warnings.append("Reused cached extraction; document content unchanged.")
    else:
        extraction = extract_file(path, ExtractContext(allow_ocr=allow_ocr, depth=depth))
        text_path = _store_text(config, conn, digest, extraction)
    result.extraction = extraction.to_dict()
    result.warnings.extend(extraction.warnings)

    pages = extraction.pages or None
    text = extraction.text

    # --- 6 & 9. metadata and entity identification -------------------------
    found = ent.extract_entities(text, pages)
    result.entities = {k: [c.to_dict() for c in v] for k, v in found.items()}
    doc_date, date_source = ent.document_date(found, text, pages)
    case_number = ent.primary_case_number(found)

    # --- 8. classify the matter (a proposal, not an assignment) ------------
    classification: Classification = classify_document(path, text, current_folder=folder)
    if classification.folder == INBOX:
        fallback = unmatched_folder_default(text)
        if fallback != INBOX:
            classification.folder = fallback
            classification.rule = "legal_document_no_matter_match"
            classification.reasons.append(
                "Reads as a legal document but matches no configured matter; "
                "proposed for 05_OTHER_CASES."
            )
    result.classification = classification.to_dict()

    candidates = _matters_in_folder(conn, classification.folder)
    proposed_matter = candidates[0] if len(candidates) == 1 else None
    matter_id = proposed_matter["id"] if proposed_matter else None

    # A verbatim line lifted from the document, for the chronological triage
    # list. It is an extract, never a generated summary: no model writes it, so
    # it cannot describe something the document does not say.
    from .triage import extract_line as _extract_line

    snippet, snippet_locator = _extract_line(text, pages)
    if snippet is None:
        snippet, snippet_locator = ("(no text could be extracted)", None)

    # --- 7. canonical document ID and the row itself -----------------------
    doc_uid = next_doc_uid(conn)
    document_id = insert(conn, "documents", {
        "doc_uid": doc_uid,
        "matter_id": matter_id,
        "title": path.stem.replace("_", " ").strip() or path.name,
        "original_filename": path.name,
        "storage_path": str(path),
        "folder": folder,
        "sha256": digest,
        "byte_size": stat.st_size,
        "mime_type": MIME_BY_KIND.get(kind, "application/octet-stream"),
        "file_kind": kind,
        "page_count": extraction.page_count,
        "text_path": str(text_path),
        "text_method": extraction.method,
        "text_confidence": extraction.confidence,
        "text_chars": len(text),
        "ocr_used": 1 if extraction.used_ocr else 0,
        "extraction_error": extraction.error,
        "analysis_version": ANALYSIS_VERSION,
        "document_date": doc_date,
        "date_source": date_source,
        "extract_line": snippet,
        "extract_locator": snippet_locator,
        "triage_status": "UNREVIEWED",
        "classification_rule": classification.rule,
        "classification_confidence": classification.confidence,
        "classification_approved": 0,
        # A document is never verified on arrival. Verification requires a human
        # or a primary-source confirmation.
        "verification_status": "UNKNOWN",
        "status": "ACTIVE",
        "created_by": actor,
        "notes": json.dumps({
            "case_number_candidate": case_number,
            "classification": classification.to_dict(),
            "extraction": extraction.to_dict(),
        }, default=str),
    })
    result.document_id = document_id
    result.doc_uid = doc_uid
    result.status = "ingested"

    # Full-text index for retrieval by matter/issue/date without shipping whole
    # files to a model.
    conn.execute(
        "INSERT INTO document_fts (doc_uid, title, body) VALUES (?,?,?)",
        (doc_uid, path.stem, text[:1_000_000]),
    )

    # --- 13. approval gate for the matter assignment -----------------------
    if classification.needs_human_choice or proposed_matter is None:
        options = [f"{m['slug']} — {m['title']}" for m in candidates] or ["(no matter in folder)"]
        _open_approval(
            conn, kind="matter_assignment",
            question=(f"Which matter does {path.name} belong to? "
                      f"Routing proposes {classification.folder} "
                      f"(confidence {classification.confidence:.0%})."),
            target_table="documents", target_id=document_id, matter_id=matter_id,
            options=options,
            proposed=options[0] if candidates else None,
        )
        result.approvals_opened += 1

    # --- 11. cross-matter links: store once, link many ---------------------
    for cross_folder in classification.cross_reference_folders:
        for matter in _matters_in_folder(conn, cross_folder):
            insert(conn, "document_matter_links", {
                "document_id": document_id,
                "matter_id": matter["id"],
                "relationship": "CROSS_REFERENCE",
                "limited_purpose": (
                    "Proposed by routing: the document mentions this matter. "
                    "Linked, not copied."
                ),
                "boundary_classification": _boundary_classification(conn, matter["id"], doc_date),
                "approved": 0,
                "created_by": actor,
            })
            result.proposed_links += 1

    # Shared evidence is linked to every active matter it could serve, without
    # ever being copied into another folder.
    if classification.folder == SHARED_EVIDENCE:
        for matter in conn.execute(
                "SELECT id FROM matters WHERE status='ACTIVE' AND folder<>?",
                (SHARED_EVIDENCE,)).fetchall():
            insert(conn, "document_matter_links", {
                "document_id": document_id,
                "matter_id": matter["id"],
                "relationship": "SHARED_EVIDENCE",
                "limited_purpose": "Shared evidence available to this matter. Not copied.",
                "approved": 0,
                "created_by": actor,
            })
            result.proposed_links += 1

    # --- 10. proposed timeline events --------------------------------------
    for candidate in found.get("date", [])[:25]:
        insert(conn, "events", {
            "matter_id": matter_id,
            "title": f"Date referenced in {doc_uid}: {candidate.value}",
            "event_date": candidate.value,
            "event_type": "DOCUMENT_REFERENCE",
            "boundary_classification": _boundary_classification(conn, matter_id, candidate.value),
            "approved": 0,
            "verification_status": "UNKNOWN",
            "source_document_id": document_id,
            "source_page_or_paragraph": candidate.locator,
            "created_by": actor,
            "notes": candidate.context[:500],
        })
        result.proposed_events += 1

    # --- 12. unknowns ------------------------------------------------------
    for gap in ent.unknowns_for_missing(found):
        insert(conn, "unknowns", {
            "matter_id": matter_id,
            "title": f"{doc_uid}: missing {gap['field']}",
            "question": gap["question"],
            "why_it_matters": gap["why_it_matters"],
            "how_to_resolve": gap["how_to_resolve"],
            "verification_status": "MISSING_SOURCE",
            "source_document_id": document_id,
            "created_by": actor,
        })
        result.unknowns += 1

    if extraction.error:
        insert(conn, "unknowns", {
            "matter_id": matter_id,
            "title": f"{doc_uid}: text extraction failed",
            "question": "What does this document say?",
            "why_it_matters": "The document is indexed but its contents are unreadable.",
            "how_to_resolve": extraction.error,
            "verification_status": "MISSING_SOURCE",
            "source_document_id": document_id,
            "created_by": actor,
        })
        result.unknowns += 1

    # --- filing-status review ---------------------------------------------
    # Filing language flags a document for review. It NEVER sets a confirmed
    # filing status: folder presence and the word "filed" are not proof.
    if classification.looks_final and not classification.looks_draft:
        filing_id = insert(conn, "filings", {
            "matter_id": matter_id,
            "document_id": document_id,
            "title": path.stem,
            "filed_date": doc_date,
            "filing_status": "FILED_UNCONFIRMED",
            "verification_status": "UNKNOWN",
            "source_document_id": document_id,
            "created_by": actor,
            "notes": "Filing language detected. Confirmation requires docket proof.",
        })
        _open_approval(
            conn, kind="filing_status",
            question=(f"{path.name} contains filing language. Confirm its filing status. "
                      "A confirmed status requires a docket entry, clerk confirmation, "
                      "stamped copy, electronic receipt, official order, or verified "
                      "service receipt."),
            target_table="filings", target_id=filing_id, matter_id=matter_id,
            options=["FILED_CONFIRMED (proof attached)", "DOCKETED (proof attached)",
                     "ENTERED (proof attached)", "Leave FILED_UNCONFIRMED", "It is a draft"],
            proposed="Leave FILED_UNCONFIRMED",
        )
        result.approvals_opened += 1

    if classification.looks_archivable:
        _open_approval(
            conn, kind="archive_proposal",
            question=f"{path.name} reads as superseded or obsolete. Move to 99_ARCHIVE?",
            target_table="documents", target_id=document_id, matter_id=matter_id,
            options=["Archive it", "Keep it active"],
            proposed="Archive it",
        )
        result.approvals_opened += 1

    audit.record(conn, actor=actor, action="DOCUMENT_INGESTED",
                 target_table="documents", target_id=document_id, matter_id=matter_id,
                 summary=f"{doc_uid} {path.name}",
                 payload={
                     "sha256": digest,
                     "folder": folder,
                     "classification": classification.to_dict(),
                     "extraction_method": extraction.method,
                     "page_count": extraction.page_count,
                 })

    # --- nested members (ZIP packets, email attachments) -------------------
    if extraction.members and depth < 3:
        for member_name, blob in extraction.members[:200]:
            nested = _ingest_member(config, conn, document_id, member_name, blob,
                                    actor=actor, allow_ocr=allow_ocr, depth=depth + 1)
            result.nested.append(nested)

    return result


def _ingest_member(config: Config, conn: sqlite3.Connection, parent_document_id: int,
                   member_name: str, blob: bytes, *, actor: str, allow_ocr: bool,
                   depth: int) -> IngestResult:
    """Ingest a file that arrived inside a container.

    Container members are materialized under .case_command (never into a
    litigation folder) so the original packet stays exactly as received.
    """
    digest = sha256_bytes(blob)
    result = IngestResult(path=f"{parent_document_id}!{member_name}", status="failed",
                          sha256=digest)

    existing = find_by_hash(conn, digest)
    if existing is not None:
        result.status = "duplicate"
        result.doc_uid = existing["doc_uid"]
        result.duplicate_of = existing["doc_uid"]
        return result

    safe_name = Path(member_name).name or "member"
    target = config.control_root / "extracted_members" / digest[:2] / f"{digest}_{safe_name}"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        from .db import atomic_write_bytes

        atomic_write_bytes(target, blob)

    nested = ingest_path(config, conn, target, actor=actor, allow_ocr=allow_ocr,
                         depth=depth, allow_control_path=True)
    if nested.document_id:
        # Present the member under its name inside the container, not under the
        # hash-prefixed filename used to materialize it on disk.
        conn.execute(
            "UPDATE documents SET source_document_id=?, original_filename=?, title=?, "
            "notes=? WHERE id=?",
            (parent_document_id, member_name,
             Path(member_name).stem.replace("_", " ").strip() or member_name,
             json.dumps({"container_member": member_name,
                         "parent_document_id": parent_document_id}),
             nested.document_id))
    return nested


def scan_folder(config: Config, conn: sqlite3.Connection, folder: str, *,
                actor: str = "ingest", allow_ocr: bool = True) -> list[IngestResult]:
    """Ingest everything in one approved folder."""
    from .hashing import iter_litigation_files

    results = []
    for path in iter_litigation_files(config, [folder]):
        results.append(ingest_path(config, conn, path, actor=actor, allow_ocr=allow_ocr))
    return results


def scan_all(config: Config, conn: sqlite3.Connection, *, actor: str = "ingest",
             allow_ocr: bool = True) -> list[IngestResult]:
    """Ingest every file in every approved folder."""
    from .config import LITIGATION_FOLDERS
    from .hashing import iter_litigation_files

    results = []
    for path in iter_litigation_files(config, LITIGATION_FOLDERS):
        results.append(ingest_path(config, conn, path, actor=actor, allow_ocr=allow_ocr))
    return results
