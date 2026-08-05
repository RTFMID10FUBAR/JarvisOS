"""Versioned JSON API for standalone clients.

This exists so a phone app can be a real application rather than a browser in a
costume. A native client holds its own copy of the record and reconciles with
this API; it does not render server HTML.

Three design choices worth stating.

**Pairing, not accounts.** A device is paired once with a six-character code
shown on the desktop. There is no account, no cloud, and no password to lose.
The two machines are already Jacob's and already on the same network. The token
is shown once and stored only as a hash, so a copied database yields no working
credential.

**Delta sync, not refetch.** `/sync` asks what changed since a cursor. On a bad
connection that is the difference between having the record and not.

**The API never transmits anything outward.** It serves the record to devices
Jacob paired. Nothing here files, serves, or sends to a tribunal — that
prohibition holds on every surface.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import audit
from .db import insert, utcnow

API_VERSION = "v1"

#: Pairing codes are short enough to type on a phone and short-lived enough
#: that a shoulder-surfed code is useless by the time it is used.
PAIRING_CODE_TTL_MINUTES = 10
PAIRING_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # no I/L/O/0/1
PAIRING_CODE_LENGTH = 6

TOKEN_BYTES = 32


class ApiError(Exception):
    """An API failure with an HTTP status attached."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------------------
# pairing and authentication
# ---------------------------------------------------------------------------
def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_pairing_code(conn: sqlite3.Connection, *, actor: str = "jacob") -> dict[str, Any]:
    """Mint a short code to type into the phone. Expires quickly."""
    code = "".join(secrets.choice(PAIRING_ALPHABET) for _ in range(PAIRING_CODE_LENGTH))
    expires = (datetime.now(timezone.utc)
               + timedelta(minutes=PAIRING_CODE_TTL_MINUTES)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    insert(conn, "pairing_codes", {
        "code": code, "expires_at": expires, "created_by": actor,
    })
    audit.record(conn, actor=actor, action="PAIRING_CODE_CREATED",
                 summary=f"code expires {expires}")

    return {"code": code, "expires_at": expires,
            "ttl_minutes": PAIRING_CODE_TTL_MINUTES,
            "note": "Type this into the phone. It expires shortly and works once."}


def redeem_pairing_code(conn: sqlite3.Connection, *, code: str, label: str,
                        platform: str = "unknown",
                        app_version: str | None = None) -> dict[str, Any]:
    """Exchange a code for a device token. The token is returned exactly once."""
    row = conn.execute("SELECT * FROM pairing_codes WHERE code=?",
                       (code.strip().upper(),)).fetchone()
    if row is None:
        raise ApiError("unknown pairing code", 404)
    if row["used_at"]:
        raise ApiError("this pairing code was already used", 409)
    if row["expires_at"] < utcnow():
        raise ApiError("this pairing code has expired; generate a new one", 410)

    token = secrets.token_urlsafe(TOKEN_BYTES)
    device_id = insert(conn, "devices", {
        "device_uid": secrets.token_hex(16),
        "label": label or "Unnamed device",
        "platform": platform,
        "app_version": app_version,
        "token_hash": _hash_token(token),
        "token_prefix": token[:8],
    })
    conn.execute("UPDATE pairing_codes SET used_at=?, device_id=? WHERE id=?",
                 (utcnow(), device_id, row["id"]))

    audit.record(conn, actor="pairing", action="DEVICE_PAIRED",
                 target_table="devices", target_id=device_id,
                 summary=f"{label} ({platform})")

    return {
        "device_uid": conn.execute("SELECT device_uid FROM devices WHERE id=?",
                                   (device_id,)).fetchone()["device_uid"],
        "token": token,
        "label": label,
        "note": ("Store this token securely on the device. It is shown once and "
                 "cannot be recovered — only replaced by pairing again."),
    }


def authenticate(conn: sqlite3.Connection, authorization: str | None) -> sqlite3.Row:
    """Resolve a bearer token to a device, or raise."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError("missing bearer token", 401)
    token = authorization.split(None, 1)[1].strip()
    device = conn.execute("SELECT * FROM devices WHERE token_hash=?",
                          (_hash_token(token),)).fetchone()
    if device is None:
        raise ApiError("unknown device token", 401)
    if device["revoked"]:
        raise ApiError("this device has been revoked", 403)
    conn.execute("UPDATE devices SET last_seen_at=? WHERE id=?", (utcnow(), device["id"]))
    return device


def revoke_device(conn: sqlite3.Connection, device_uid: str, *, reason: str | None = None,
                  actor: str = "jacob") -> dict[str, Any]:
    """Cut a device off. Used the moment a phone is lost."""
    device = conn.execute("SELECT * FROM devices WHERE device_uid=?", (device_uid,)).fetchone()
    if device is None:
        raise ApiError("unknown device", 404)
    conn.execute("UPDATE devices SET revoked=1, revoked_at=?, revoked_reason=? WHERE id=?",
                 (utcnow(), reason, device["id"]))
    audit.record(conn, actor=actor, action="DEVICE_REVOKED",
                 target_table="devices", target_id=device["id"],
                 summary=f"{device['label']}: {reason or 'no reason given'}")
    return {"device_uid": device_uid, "revoked": True,
            "note": "The device keeps whatever it already downloaded; it can fetch nothing more."}


def list_devices(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        "SELECT id, device_uid, label, platform, app_version, token_prefix, paired_at, "
        "last_seen_at, sync_count, revoked, revoked_at, revoked_reason "
        "FROM devices ORDER BY paired_at DESC")]


# ---------------------------------------------------------------------------
# delta sync
# ---------------------------------------------------------------------------
#: Tables a client mirrors, and the columns it needs. Deliberately narrow: a
#: phone does not need the whole schema, and shipping less is faster on a bad
#: connection.
SYNC_TABLES: dict[str, str] = {
    "matters": """
        SELECT change_seq, id, slug, title, caption, case_number, forum, posture, status,
               boundary_date, boundary_label, updated_at
        FROM matters WHERE updated_at > ?
    """,
    "documents": """
        SELECT change_seq, id, doc_uid, matter_id, title, original_filename, folder,
               document_date, date_source, extract_line, extract_locator,
               text_method, text_confidence, ocr_used, page_count, byte_size,
               sha256, verification_status, triage_status, updated_at
        FROM documents WHERE updated_at > ? AND status='ACTIVE'
    """,
    "issues": """
        SELECT change_seq, id, matter_id, issue_key, title, status, verification_status,
               boundary_classification, hearing_scope, legal_element,
               requested_finding, requested_relief, missing_proof,
               appeal_standard, risk_rating, updated_at
        FROM issues WHERE updated_at > ?
    """,
    "deadlines": """
        SELECT change_seq, id, matter_id, issue_id, title, due_date, deadline_type,
               trigger_event, days_allowed, satisfied, verification_status,
               notes, updated_at
        FROM deadlines WHERE updated_at > ? AND status='ACTIVE'
    """,
    "events": """
        SELECT change_seq, id, matter_id, title, event_date, event_type, legal_significance,
               boundary_classification, disputed, verification_status, updated_at
        FROM events WHERE updated_at > ? AND status='ACTIVE'
    """,
    "preservation_items": """
        SELECT change_seq, id, matter_id, issue_id, title, raised, where_raised, date_raised,
               ruling_requested, ruling_issued, ignored, exception_required,
               exception_filed, appeal_deadline, standard_of_review, risk, updated_at
        FROM preservation_items WHERE updated_at > ? AND status='ACTIVE'
    """,
    "access_barriers": """
        SELECT change_seq, id, matter_id, title, incident_date, barrier_type, what_was_blocked,
               deadline_affected, deadline_date, reported_to_tribunal,
               verification_status, updated_at
        FROM access_barriers WHERE updated_at > ? AND status='ACTIVE'
    """,
}

#: A first sync has no cursor. This is early enough to mean "everything".
EPOCH = "1970-01-01T00:00:00.000Z"

#: Rows per table per request. A client may ask for fewer — on a bad
#: connection a small page that arrives beats a large one that times out — and
#: may not ask for more, so one request can never be made to haul the whole
#: record.
DEFAULT_SYNC_LIMIT = 500
MAX_SYNC_LIMIT = 2000

#: Cursors are opaque to clients; both the Python and Kotlin clients store and
#: return them without looking inside. The prefix lets an older bare-timestamp
#: cursor still be recognised and safely discarded.
CURSOR_PREFIX = "v3:"


def _keyed(query: str) -> str:
    """Swap a replicated query's timestamp test for the change-number test."""
    assert "updated_at > ?" in query, query
    return query.replace("updated_at > ?", "change_seq > ?", 1)


def _parse_cursor(since: str | None) -> dict[str, int]:
    """Read a cursor into a per-table change number."""
    if not since:
        return {}
    if since.startswith(CURSOR_PREFIX):
        try:
            return {table: int(seq)
                    for table, seq in json.loads(since[len(CURSOR_PREFIX):]).items()}
        except (ValueError, TypeError, AttributeError):
            return {}
    # A cursor from an older build was a timestamp, which cannot be mapped onto
    # a change number. Start over rather than guess: re-sending rows the client
    # already has is absorbed by its upsert, and guessing would lose them.
    return {}


def _encode_cursor(positions: dict[str, int]) -> str:
    return CURSOR_PREFIX + json.dumps(dict(sorted(positions.items())),
                                      separators=(",", ":"))


def sync(conn: sqlite3.Connection, *, since: str | None = None,
         device: sqlite3.Row | None = None,
         limit_per_table: int = DEFAULT_SYNC_LIMIT) -> dict[str, Any]:
    """Everything that changed after *since*.

    Where the cursor lands is the whole correctness argument here, and the first
    two attempts at it were both wrong the same way.

    It was wall-clock time read at the start of a sync, which loses any row
    written in that same millisecond: the test is strictly greater-than, so the
    row is skipped, and because the client stores the cursor it is skipped again
    on every later sync. Not an error — a permanent, silent hole. CI caught it.

    Making the cursor carry (updated_at, id) helped and was still not exact. An
    UPDATE moves a row to a new position; if that position shares a millisecond
    with the last row already delivered but has a lower id, it sorts behind the
    cursor and is never sent.

    Both have one root: a millisecond timestamp is not a unique, monotonic
    position, so no choice of *which* timestamp can make it one. The cursor is
    now `change_seq` — a counter bumped by a trigger on every insert and update,
    never reused, never going backwards, owing nothing to a clock. `change_seq >
    cursor` is exact. A row is passed over only once it has genuinely been
    handed to the client, and a table that returned nothing keeps its position.

    Because the position is exact, a capped page can stop anywhere and resume
    exactly there — no keeping timestamp groups whole, and the row limit is a
    real limit.
    """
    limit = max(1, int(limit_per_table))
    positions = _parse_cursor(since)

    changed: dict[str, list[dict[str, Any]]] = {}
    counts: dict[str, int] = {}
    next_positions: dict[str, int] = dict(positions)
    truncated: list[str] = []

    for table, query in SYNC_TABLES.items():
        last = positions.get(table, 0)
        rows = [dict(r) for r in conn.execute(
            f"{_keyed(query)} ORDER BY change_seq LIMIT {limit}", (last,))]

        if rows:
            changed[table] = rows
            next_positions[table] = int(rows[-1]["change_seq"])
        counts[table] = len(rows)
        if len(rows) >= limit:
            truncated.append(table)

    if device is not None:
        conn.execute(
            "UPDATE devices SET last_sync_cursor=?, sync_count=sync_count+1 WHERE id=?",
            (_encode_cursor(next_positions), device["id"]))

    return {
        "api_version": API_VERSION,
        "cursor": since,
        "next_cursor": _encode_cursor(next_positions),
        "changed": changed,
        "counts": counts,
        "total": sum(counts.values()),
        # If a table filled its page there is more waiting. Say so rather than
        # letting the client believe it is up to date.
        "more_available": bool(truncated),
        "truncated_tables": sorted(truncated),
        "full_sync": since is None,
    }


# ---------------------------------------------------------------------------
# resources
# ---------------------------------------------------------------------------
def document_detail(conn: sqlite3.Connection, doc_uid: str, *,
                    include_text: bool = True) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM documents WHERE doc_uid=?", (doc_uid,)).fetchone()
    if row is None:
        raise ApiError("unknown document", 404)

    payload = {
        k: row[k] for k in (
            "id", "doc_uid", "matter_id", "title", "original_filename", "folder",
            "document_date", "date_source", "extract_line", "extract_locator",
            "text_method", "text_confidence", "ocr_used", "page_count",
            "byte_size", "sha256", "verification_status", "triage_status",
            "extraction_error",
        )
    }
    payload["has_original"] = bool(row["storage_path"] and Path(row["storage_path"]).exists())

    if include_text and row["text_path"]:
        path = Path(row["text_path"])
        payload["text"] = (path.read_text(encoding="utf-8", errors="replace")[:500_000]
                           if path.exists() else "")
    else:
        payload["text"] = ""

    payload["links"] = [dict(r) for r in conn.execute("""
        SELECT l.relationship, l.limited_purpose, l.boundary_classification,
               m.slug, m.title AS matter_title
        FROM document_matter_links l JOIN matters m ON m.id = l.matter_id
        WHERE l.document_id = ?
    """, (row["id"],))]

    payload["copies"] = [dict(r) for r in conn.execute(
        "SELECT path, folder, disposition FROM document_copies "
        "WHERE document_id=? AND still_present=1", (row["id"],))]

    return payload


def document_original(conn: sqlite3.Connection, doc_uid: str) -> tuple[bytes, str, str]:
    """The original bytes, its filename, and a content type.

    Read-only, like everywhere else: the API serves originals and never writes
    to them.
    """
    row = conn.execute("SELECT * FROM documents WHERE doc_uid=?", (doc_uid,)).fetchone()
    if row is None:
        raise ApiError("unknown document", 404)
    path = Path(row["storage_path"])
    if not path.exists():
        raise ApiError("the original file is no longer at its recorded path", 410)
    return (path.read_bytes(), row["original_filename"],
            row["mime_type"] or "application/octet-stream")


def matter_detail(conn: sqlite3.Connection, matter_id: int) -> dict[str, Any]:
    from . import atlas, views

    data = views.matter_view(conn, matter_id)
    if not data:
        raise ApiError("unknown matter", 404)
    return {
        "matter": data["matter"],
        "issues": data["issues"],
        "deadlines": data["deadlines"],
        "filings": data["filings"],
        "orders": data["orders"],
        "evidence": data["evidence"],
        "preservation": data["preservation_summary"],
        "coverage": atlas.coverage(conn, matter_id),
        "atlas": atlas.build_atlas(conn, matter_id),
    }


def index() -> dict[str, Any]:
    """Endpoint list, so a client can be written against the API alone."""
    return {
        "api_version": API_VERSION,
        "endpoints": {
            "POST /api/v1/pair": "redeem a pairing code -> device token",
            "GET  /api/v1/sync?since=<cursor>": "delta sync of the mirrored tables",
            "GET  /api/v1/matters": "matter list",
            "GET  /api/v1/matters/<id>": "matter detail, coverage, path atlas",
            "GET  /api/v1/documents/<doc_uid>": "document metadata and text",
            "GET  /api/v1/documents/<doc_uid>/original": "original bytes",
            "GET  /api/v1/hearing/<matter_id>": "hearing pack payload",
            "GET  /api/v1/offline/bundle": "pinned documents plus hearing context",
            "POST /api/v1/captures": "multipart upload of captured evidence",
            "GET  /api/v1/health": "health report",
        },
        "auth": "Authorization: Bearer <device token>, except /pair and /health.",
        "guarantees": [
            "Read-only with respect to originals.",
            "Nothing here files, serves, or transmits to a tribunal.",
            "Every date carries the provenance of how it was read.",
            "A computed deadline is INFERENCE and names the authority to confirm.",
        ],
    }
