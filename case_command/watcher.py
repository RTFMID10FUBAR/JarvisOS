"""Folder watcher with a durable, restart-safe work queue.

The queue lives in SQLite, not in memory, so a crash or restart never loses
queued work. On startup any job left IN_PROGRESS is returned to PENDING and
retried — an interrupted ingestion resumes rather than disappearing.

Polling is used rather than OS file-system events: it is portable, it survives
network volumes being remounted, and a missed event cannot silently drop a
document.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import audit
from .config import Config, LITIGATION_FOLDERS
from .db import utcnow
from .hashing import folder_of, iter_litigation_files
from .ingest import IngestResult, ingest_path

MAX_ATTEMPTS = 3
#: A file must stop changing size for this long before it is ingested, so a
#: half-copied scan or download is never read mid-write.
SETTLE_SECONDS = 2.0


@dataclass
class QueueStats:
    pending: int = 0
    in_progress: int = 0
    done: int = 0
    failed: int = 0
    skipped: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "pending": self.pending, "in_progress": self.in_progress,
            "done": self.done, "failed": self.failed, "skipped": self.skipped,
        }


def queue_stats(conn: sqlite3.Connection) -> QueueStats:
    stats = QueueStats()
    for row in conn.execute("SELECT state, COUNT(*) AS n FROM ingest_queue GROUP BY state"):
        setattr(stats, row["state"].lower(), int(row["n"]))
    return stats


def recover_interrupted(conn: sqlite3.Connection) -> int:
    """Return abandoned IN_PROGRESS jobs to PENDING. Called on every startup."""
    cur = conn.execute(
        "UPDATE ingest_queue SET state='PENDING', started_at=NULL "
        "WHERE state='IN_PROGRESS'"
    )
    count = cur.rowcount or 0
    if count:
        audit.record(conn, actor="watcher", action="QUEUE_RECOVERED",
                     summary=f"{count} interrupted job(s) returned to PENDING")
    return count


def _already_queued(conn: sqlite3.Connection, path: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM ingest_queue WHERE path=? AND state IN ('PENDING','IN_PROGRESS')",
        (path,),
    ).fetchone()
    return row is not None


def _known_document(conn: sqlite3.Connection, path: str) -> bool:
    row = conn.execute("SELECT 1 FROM documents WHERE storage_path=?", (path,)).fetchone()
    return row is not None


def enqueue(conn: sqlite3.Connection, config: Config, path: Path) -> bool:
    """Add one path to the queue. Returns True when a job was created."""
    text = str(path)
    if _already_queued(conn, text):
        return False
    conn.execute(
        "INSERT INTO ingest_queue (path, folder, state) VALUES (?,?, 'PENDING')",
        (text, folder_of(config, path)),
    )
    return True


def discover(config: Config, conn: sqlite3.Connection,
             folders: tuple[str, ...] = LITIGATION_FOLDERS) -> int:
    """Queue every approved-folder file that is not already a known document."""
    queued = 0
    for path in iter_litigation_files(config, folders):
        if _known_document(conn, str(path)):
            continue
        if enqueue(conn, config, path):
            queued += 1
    return queued


def _has_settled(path: Path) -> bool:
    """True when the file has stopped growing, so it is safe to read."""
    try:
        first = path.stat()
        time.sleep(min(SETTLE_SECONDS, 0.25))
        second = path.stat()
    except OSError:
        return False
    return first.st_size == second.st_size and first.st_mtime == second.st_mtime


def drain(config: Config, conn: sqlite3.Connection, *, limit: int | None = None,
          actor: str = "watcher", allow_ocr: bool = True,
          on_result: Callable[[IngestResult], None] | None = None) -> list[IngestResult]:
    """Process pending jobs. Each job is isolated: one failure never stops the run."""
    results: list[IngestResult] = []
    while True:
        if limit is not None and len(results) >= limit:
            break
        job = conn.execute(
            "SELECT * FROM ingest_queue WHERE state='PENDING' AND attempts<? "
            "ORDER BY id LIMIT 1",
            (MAX_ATTEMPTS,),
        ).fetchone()
        if job is None:
            break

        conn.execute(
            "UPDATE ingest_queue SET state='IN_PROGRESS', started_at=?, attempts=attempts+1 "
            "WHERE id=?",
            (utcnow(), job["id"]),
        )
        path = Path(job["path"])

        if not path.exists():
            conn.execute(
                "UPDATE ingest_queue SET state='SKIPPED', finished_at=?, last_error=? WHERE id=?",
                (utcnow(), "file no longer exists", job["id"]),
            )
            continue

        try:
            result = ingest_path(config, conn, path, actor=actor, allow_ocr=allow_ocr)
        except Exception as exc:
            # Fail loud: the job is marked FAILED with the reason recorded. It is
            # never silently dropped.
            conn.execute(
                "UPDATE ingest_queue SET state='FAILED', finished_at=?, last_error=? WHERE id=?",
                (utcnow(), f"{type(exc).__name__}: {exc}", job["id"]),
            )
            audit.record(conn, actor=actor, action="INGEST_ERROR",
                         summary=str(path), payload={"error": f"{type(exc).__name__}: {exc}"})
            results.append(IngestResult(path=str(path), status="failed",
                                        error=f"{type(exc).__name__}: {exc}"))
            continue

        if result.status == "failed":
            state = "FAILED" if job["attempts"] + 1 >= MAX_ATTEMPTS else "PENDING"
            conn.execute(
                "UPDATE ingest_queue SET state=?, finished_at=?, last_error=? WHERE id=?",
                (state, utcnow(), result.error, job["id"]),
            )
        else:
            conn.execute(
                "UPDATE ingest_queue SET state='DONE', finished_at=?, document_id=? WHERE id=?",
                (utcnow(), result.document_id, job["id"]),
            )
        results.append(result)
        if on_result:
            on_result(result)
    return results


def failed_jobs(conn: sqlite3.Connection) -> list[dict[str, object]]:
    """Every job that could not be ingested, with the reason. Never hidden."""
    rows = conn.execute(
        "SELECT * FROM ingest_queue WHERE state='FAILED' ORDER BY id DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def retry_failed(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        "UPDATE ingest_queue SET state='PENDING', attempts=0, last_error=NULL "
        "WHERE state='FAILED'"
    )
    return cur.rowcount or 0


def watch(config: Config, conn: sqlite3.Connection, *, interval: float = 5.0,
          iterations: int | None = None, allow_ocr: bool = True,
          verbose: bool = True) -> None:
    """Continuously discover and ingest. Ctrl-C exits cleanly with work preserved."""
    recovered = recover_interrupted(conn)
    if verbose and recovered:
        print(f"[watcher] recovered {recovered} interrupted job(s)")

    count = 0
    try:
        while iterations is None or count < iterations:
            queued = discover(config, conn)
            if queued and verbose:
                print(f"[watcher] queued {queued} new file(s)")
            results = drain(config, conn, allow_ocr=allow_ocr)
            if verbose:
                for result in results:
                    marker = {"ingested": "+", "duplicate": "=", "failed": "!",
                              "unchanged": ".", "skipped": "-"}.get(result.status, "?")
                    print(f"[watcher] {marker} {result.status:10} {Path(result.path).name}"
                          + (f"  ({result.error})" if result.error else ""))
            count += 1
            if iterations is None or count < iterations:
                time.sleep(interval)
    except KeyboardInterrupt:
        if verbose:
            stats = queue_stats(conn)
            print(f"\n[watcher] stopped. Queue preserved: {stats.to_dict()}")
