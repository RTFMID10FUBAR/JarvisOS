"""Database connection, migrations, and safe write primitives.

Everything that touches the SQLite file goes through here so that WAL mode,
foreign keys, atomic file writes, and the audit trail are applied uniformly.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

from .config import Config

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

VERIFICATION_STATUSES = (
    "VERIFIED_PRIMARY",
    "VERIFIED_SECONDARY",
    "PARTIALLY_VERIFIED",
    "DISPUTED",
    "INFERENCE",
    "UNKNOWN",
    "MISSING_SOURCE",
    "SUPERSEDED",
)

FILING_STATUSES = (
    "DRAFT",
    "READY_FOR_REVIEW",
    "APPROVED",
    "SENT",
    "FILED_UNCONFIRMED",
    "FILED_CONFIRMED",
    "DOCKETED",
    "ENTERED",
    "REJECTED",
    "SUPERSEDED",
)

#: Statuses that assert a document really is on file somewhere official.
CONFIRMED_FILING_STATUSES = ("FILED_CONFIRMED", "DOCKETED", "ENTERED")

PROOF_TYPES = (
    "DOCKET_ENTRY",
    "CLERK_CONFIRMATION",
    "STAMPED_COPY",
    "ELECTRONIC_RECEIPT",
    "OFFICIAL_ORDER",
    "VERIFIED_SERVICE_RECEIPT",
)

ISSUE_STATUSES = (
    "ACTIVE",
    "RESERVED",
    "WEAK",
    "MISSING_PROOF",
    "OUTSIDE_CURRENT_HEARING",
    "SUPERSEDED_BY_AUTHORITY",
    "DECIDED",
)

BOUNDARY_CLASSIFICATIONS = (
    "CASE_1_DECIDED_ISSUE",
    "POST_FINAL_ORDER_NEW_CONDUCT",
    "PRIOR_EVIDENCE_FOR_LIMITED_PURPOSE",
    "PROCEDURAL_HISTORY",
    "UNKNOWN",
    "NOT_APPLICABLE",
)

#: Trust order, highest first. Index 0 is the most authoritative source.
TRUST_HIERARCHY = (
    "FILED_OR_ENTERED_PRIMARY_SOURCE",
    "CERTIFIED_DOCKET_OR_OFFICIAL_RECORD",
    "ORIGINAL_EVIDENCE",
    "APPROVED_CASE_COMMAND_FACT",
    "APPROVED_LEGAL_ANALYSIS",
    "FLEET_PROPOSAL",
    "AI_GENERATED_SUMMARY",
    "CHAT_HISTORY",
)


def trust_rank(source_kind: str) -> int:
    """Lower is more trustworthy. Unknown kinds sort below everything known."""
    try:
        return TRUST_HIERARCHY.index(source_kind)
    except ValueError:
        return len(TRUST_HIERARCHY)


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# ---------------------------------------------------------------------------
# atomic file writes
# ---------------------------------------------------------------------------
def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write *data* to *path* so a crash mid-write can never truncate the target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    atomic_write_bytes(path, text.encode(encoding, errors="replace"))


def atomic_write_json(path: Path, obj: Any) -> None:
    atomic_write_text(path, json.dumps(obj, indent=2, sort_keys=True, default=str))


# ---------------------------------------------------------------------------
# connection + migrations
# ---------------------------------------------------------------------------
def connect(config: Config, *, readonly: bool = False) -> sqlite3.Connection:
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    if readonly:
        uri = f"file:{config.db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=30.0)
    else:
        conn = sqlite3.connect(str(config.db_path), timeout=30.0,
                               isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if not readonly:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = FULL")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Explicit transaction. Rolls back on any exception — no partial writes."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL,
            checksum   TEXT NOT NULL
        )
        """
    )


def applied_migrations(conn: sqlite3.Connection) -> list[str]:
    _ensure_migrations_table(conn)
    return [r["version"] for r in conn.execute(
        "SELECT version FROM schema_migrations ORDER BY version")]


def pending_migrations(conn: sqlite3.Connection) -> list[Path]:
    done = set(applied_migrations(conn))
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    return [f for f in files if f.stem not in done]


def migrate(conn: sqlite3.Connection) -> list[str]:
    """Apply pending migrations in order. Each runs in its own transaction."""
    import hashlib

    _ensure_migrations_table(conn)
    applied: list[str] = []
    for path in pending_migrations(conn):
        sql = path.read_text(encoding="utf-8")
        checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        version = path.stem
        for value in (version, checksum):
            if "'" in value:
                raise ValueError(f"unsafe migration identifier: {value!r}")
        # executescript() implicitly commits any open transaction before running,
        # so the BEGIN/COMMIT must live inside the script itself for the schema
        # change and its bookkeeping row to land atomically.
        script = (
            "BEGIN;\n"
            + sql
            + "\nINSERT INTO schema_migrations (version, applied_at, checksum) VALUES "
            + f"('{version}', '{utcnow()}', '{checksum}');\n"
            + "COMMIT;\n"
        )
        try:
            conn.executescript(script)
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass  # nothing to roll back; SQLite already unwound the script
            raise
        applied.append(version)
    return applied


def verify_migration_checksums(conn: sqlite3.Connection) -> list[str]:
    """Return versions whose on-disk SQL no longer matches what was applied."""
    import hashlib

    _ensure_migrations_table(conn)
    drift: list[str] = []
    for row in conn.execute("SELECT version, checksum FROM schema_migrations"):
        path = MIGRATIONS_DIR / f"{row['version']}.sql"
        if not path.exists():
            drift.append(f"{row['version']} (file missing)")
            continue
        current = hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
        if current != row["checksum"]:
            drift.append(f"{row['version']} (checksum changed)")
    return drift


def open_database(config: Config, *, migrate_if_needed: bool = True) -> sqlite3.Connection:
    conn = connect(config)
    if migrate_if_needed:
        migrate(conn)
    return conn


# ---------------------------------------------------------------------------
# generic record helpers
# ---------------------------------------------------------------------------
def insert(conn: sqlite3.Connection, table: str, values: Mapping[str, Any]) -> int:
    cols = list(values.keys())
    placeholders = ",".join("?" for _ in cols)
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
    cur = conn.execute(sql, [values[c] for c in cols])
    return int(cur.lastrowid)


def update(conn: sqlite3.Connection, table: str, record_id: int,
           values: Mapping[str, Any]) -> None:
    payload = dict(values)
    payload["updated_at"] = utcnow()
    assignments = ",".join(f"{c}=?" for c in payload)
    conn.execute(f"UPDATE {table} SET {assignments} WHERE id=?",
                 [*payload.values(), record_id])


def fetch_one(conn: sqlite3.Connection, sql: str,
              params: Sequence[Any] = ()) -> sqlite3.Row | None:
    return conn.execute(sql, params).fetchone()


def fetch_all(conn: sqlite3.Connection, sql: str,
              params: Sequence[Any] = ()) -> list[sqlite3.Row]:
    return conn.execute(sql, params).fetchall()


def get_record(conn: sqlite3.Connection, table: str, record_id: int) -> sqlite3.Row | None:
    return fetch_one(conn, f"SELECT * FROM {table} WHERE id=?", (record_id,))


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


def table_names(conn: sqlite3.Connection) -> list[str]:
    return [r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
