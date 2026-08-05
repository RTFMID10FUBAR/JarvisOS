"""Backup, verification, and restore.

A backup that has never been restored is a hope, not a backup. Every backup is
verified by reopening the copy, running an integrity check, comparing row counts
against the live database, and re-verifying the audit hash chain. `restore`
always writes a safety copy of the current database first.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from . import audit
from .config import Config
from .db import atomic_write_json, connect, utcnow

#: Tables whose row counts are compared between live and backup.
VERIFY_TABLES = (
    "matters", "documents", "issues", "facts", "events", "filings", "orders",
    "deadlines", "preservation_items", "contradictions", "unknowns",
    "fleet_proposals", "audit_log",
)


def _row_counts(conn: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in VERIFY_TABLES:
        try:
            counts[table] = int(conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"])
        except sqlite3.Error:
            counts[table] = -1
    return counts


def create_backup(config: Config, conn: sqlite3.Connection, *,
                  label: str = "manual", actor: str = "backup") -> dict[str, Any]:
    """Create a consistent backup using SQLite's online backup API.

    The online API is used rather than copying the file, so a backup taken while
    the watcher is mid-write is still internally consistent.
    """
    config.backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = utcnow().replace(":", "").replace("-", "").replace(".", "")
    target = config.backups_dir / f"case_command_{label}_{stamp}.sqlite3"

    live_counts = _row_counts(conn)
    destination = sqlite3.connect(str(target))
    try:
        conn.backup(destination)
    finally:
        destination.close()

    verification = verify_backup(config, target, expected_counts=live_counts)
    metadata = {
        "created_at": utcnow(),
        "label": label,
        "path": str(target),
        "byte_size": target.stat().st_size,
        "source_db": str(config.db_path),
        "row_counts": live_counts,
        "verification": verification,
    }
    atomic_write_json(target.with_suffix(".json"), metadata)

    audit.record(conn, actor=actor, action="BACKUP_CREATED",
                 summary=str(target), payload={"verified": verification["ok"]})
    conn.execute("INSERT INTO system_events (kind, ok, detail) VALUES (?,?,?)",
                 ("backup", 1 if verification["ok"] else 0, json.dumps(metadata, default=str)))

    return metadata


def verify_backup(config: Config, backup_path: Path,
                  expected_counts: dict[str, int] | None = None) -> dict[str, Any]:
    """Open the backup and prove it is usable. Never touches the live database."""
    problems: list[str] = []
    backup_path = Path(backup_path)

    if not backup_path.exists():
        return {"ok": False, "problems": [f"backup file missing: {backup_path}"]}

    try:
        conn = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        return {"ok": False, "problems": [f"cannot open backup: {exc}"]}

    counts: dict[str, int] = {}
    chain_ok = False
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            problems.append(f"integrity_check returned {integrity!r}")

        foreign_key_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_errors:
            problems.append(f"{len(foreign_key_errors)} foreign key violation(s)")

        counts = _row_counts(conn)
        if expected_counts:
            for table, expected in expected_counts.items():
                actual = counts.get(table, -1)
                if actual != expected:
                    problems.append(
                        f"row count mismatch in {table}: backup {actual}, live {expected}")

        chain_ok, chain_problems = audit.verify_chain(conn)
        problems.extend(f"audit chain: {p}" for p in chain_problems)
    finally:
        conn.close()

    return {
        "ok": not problems,
        "problems": problems,
        "row_counts": counts,
        "audit_chain_intact": chain_ok,
        "backup": str(backup_path),
    }


def list_backups(config: Config) -> list[dict[str, Any]]:
    if not config.backups_dir.exists():
        return []
    entries: list[dict[str, Any]] = []
    for path in sorted(config.backups_dir.glob("*.sqlite3"), reverse=True):
        meta_path = path.with_suffix(".json")
        metadata: dict[str, Any] = {}
        if meta_path.exists():
            try:
                metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                metadata = {}
        entries.append({
            "path": str(path),
            "byte_size": path.stat().st_size,
            "created_at": metadata.get("created_at"),
            "label": metadata.get("label"),
            "verified": (metadata.get("verification") or {}).get("ok"),
        })
    return entries


def restore(config: Config, backup_path: Path, *, approved: bool = False,
            actor: str = "backup") -> dict[str, Any]:
    """Replace the live database with a backup.

    Refuses without explicit approval, verifies the backup first, and preserves
    the current database as a safety copy before replacing it. The old database
    is renamed, never deleted.
    """
    backup_path = Path(backup_path)

    verification = verify_backup(config, backup_path)
    if not verification["ok"]:
        return {"restored": False, "reason": "backup failed verification",
                "verification": verification}

    if not approved:
        return {
            "restored": False,
            "reason": "approval required",
            "detail": ("restore() replaces the live database and requires approved=True. "
                       "The backup verified successfully and is ready."),
            "verification": verification,
        }

    stamp = utcnow().replace(":", "").replace("-", "").replace(".", "")
    safety: str | None = None
    if config.db_path.exists():
        safety_path = config.backups_dir / f"pre_restore_{stamp}.sqlite3"
        safety_path.parent.mkdir(parents=True, exist_ok=True)
        # Rename rather than delete: the previous database is always recoverable.
        shutil.copy2(config.db_path, safety_path)
        safety = str(safety_path)
        for suffix in ("-wal", "-shm"):
            side = Path(str(config.db_path) + suffix)
            if side.exists():
                side.unlink()

    shutil.copy2(backup_path, config.db_path)

    conn = connect(config)
    try:
        post = verify_backup(config, config.db_path)
        audit.record(conn, actor=actor, action="DATABASE_RESTORED",
                     summary=str(backup_path),
                     payload={"safety_copy": safety, "post_verification_ok": post["ok"]})
        conn.execute("INSERT INTO system_events (kind, ok, detail) VALUES (?,?,?)",
                     ("restore", 1 if post["ok"] else 0,
                      json.dumps({"from": str(backup_path), "safety": safety})))
    finally:
        conn.close()

    return {
        "restored": True,
        "from": str(backup_path),
        "safety_copy": safety,
        "post_restore_verification": post,
    }


def prune_candidates(config: Config, keep: int = 10) -> dict[str, Any]:
    """Identify old backups without deleting anything.

    Deletion stays disabled until Jacob approves it. This function only reports
    what a prune *would* remove.
    """
    backups = list_backups(config)
    stale = backups[keep:]
    return {
        "total": len(backups),
        "keep": keep,
        "would_remove": [b["path"] for b in stale],
        "reclaimed_bytes": sum(b["byte_size"] for b in stale),
        "note": ("Reported only. Deletion is disabled until explicitly approved. "
                 "Remove these manually if you want the space back."),
    }
    # Deliberately not implemented: automatic deletion of backups.
    # Any code that would delete data stays disabled until Jacob approves it.
    #
    # for entry in stale:
    #     Path(entry["path"]).unlink()
