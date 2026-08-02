"""Append-only, hash-chained audit log.

Every write that changes the canonical record passes through :func:`record`.
Each entry hashes the previous entry's hash, so removing or editing an entry
after the fact breaks the chain and :func:`verify_chain` reports it.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from .db import utcnow

GENESIS = "0" * 64


def _entry_hash(prev_hash: str, ts: str, actor: str, action: str,
                target_table: str | None, target_id: int | None,
                summary: str | None, payload_json: str | None) -> str:
    material = "\x1f".join([
        prev_hash, ts, actor, action,
        target_table or "", str(target_id or ""),
        summary or "", payload_json or "",
    ])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def last_hash(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT entry_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    return row["entry_hash"] if row else GENESIS


def record(conn: sqlite3.Connection, *, actor: str, action: str,
           target_table: str | None = None, target_id: int | None = None,
           matter_id: int | None = None, summary: str | None = None,
           payload: Any = None) -> int:
    """Append one audit entry. Never raises for a missing optional field."""
    ts = utcnow()
    payload_json = json.dumps(payload, sort_keys=True, default=str) if payload is not None else None
    prev = last_hash(conn)
    digest = _entry_hash(prev, ts, actor, action, target_table, target_id,
                         summary, payload_json)
    cur = conn.execute(
        """
        INSERT INTO audit_log (ts, actor, action, target_table, target_id, matter_id,
                               summary, payload, prev_hash, entry_hash)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (ts, actor, action, target_table, target_id, matter_id, summary,
         payload_json, prev, digest),
    )
    return int(cur.lastrowid)


def verify_chain(conn: sqlite3.Connection) -> tuple[bool, list[str]]:
    """Recompute the whole chain. Returns (ok, list of problems)."""
    problems: list[str] = []
    prev = GENESIS
    for row in conn.execute("SELECT * FROM audit_log ORDER BY id"):
        if row["prev_hash"] != prev:
            problems.append(
                f"entry {row['id']}: prev_hash mismatch "
                f"(stored {row['prev_hash']!r}, expected {prev!r})"
            )
        expected = _entry_hash(row["prev_hash"] or GENESIS, row["ts"], row["actor"],
                               row["action"], row["target_table"], row["target_id"],
                               row["summary"], row["payload"])
        if expected != row["entry_hash"]:
            problems.append(f"entry {row['id']}: entry_hash does not match contents")
        prev = row["entry_hash"]
    return (not problems), problems


def history(conn: sqlite3.Connection, table: str, record_id: int,
            limit: int = 100) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM audit_log WHERE target_table=? AND target_id=? ORDER BY id DESC LIMIT ?",
        (table, record_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def recent(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]
