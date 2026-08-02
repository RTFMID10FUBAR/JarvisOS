"""Health checks.

Everything that could be silently broken is checked explicitly and reported,
including degraded states that still "work": missing OCR, a stalled queue, an
unverified backup, folder sprawl, or an issue whose source no longer exists.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from . import audit, backup as backup_mod
from .config import Config, LITIGATION_FOLDERS, unexpected_top_level_folders
from .db import (
    CONFIRMED_FILING_STATUSES,
    applied_migrations,
    pending_migrations,
    verify_migration_checksums,
)
from .extract import dependency_report
from .watcher import failed_jobs, queue_stats

OK, WARN, FAIL = "OK", "WARN", "FAIL"


def _check(name: str, status: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {"check": name, "status": status, "detail": detail, **extra}


def run_health_checks(config: Config, conn: sqlite3.Connection) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    # --- filesystem --------------------------------------------------------
    missing = [name for name in LITIGATION_FOLDERS if not (config.data_root / name).exists()]
    checks.append(_check(
        "folder_structure",
        OK if not missing else FAIL,
        "All nine approved folders present." if not missing
        else f"Missing folders: {', '.join(missing)}. Run `case-command init`.",
        missing=missing,
    ))

    sprawl = unexpected_top_level_folders(config)
    checks.append(_check(
        "folder_sprawl",
        OK if not sprawl else WARN,
        "No folders outside the approved structure." if not sprawl
        else (f"{len(sprawl)} unexpected top-level folder(s): {', '.join(sprawl[:10])}. "
              "Nothing was moved; consolidating them is a decision, not an automation."),
        folders=sprawl,
    ))

    missing_control = [str(p) for p in config.control_dirs if not p.exists()]
    checks.append(_check(
        "control_directories",
        OK if not missing_control else FAIL,
        "Control directories present." if not missing_control
        else f"Missing: {', '.join(missing_control)}",
    ))

    # --- database ----------------------------------------------------------
    pending = [p.stem for p in pending_migrations(conn)]
    checks.append(_check(
        "migrations",
        OK if not pending else WARN,
        f"{len(applied_migrations(conn))} migration(s) applied." if not pending
        else f"Pending migrations: {', '.join(pending)}",
        applied=applied_migrations(conn), pending=pending,
    ))

    drift = verify_migration_checksums(conn)
    checks.append(_check(
        "migration_integrity",
        OK if not drift else FAIL,
        "Applied migrations match their files."
        if not drift else f"Migration files changed after being applied: {', '.join(drift)}",
    ))

    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    except sqlite3.Error as exc:
        integrity = f"error: {exc}"
    checks.append(_check(
        "database_integrity", OK if integrity == "ok" else FAIL,
        f"integrity_check: {integrity}",
    ))

    fk_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
    checks.append(_check(
        "foreign_keys", OK if not fk_errors else FAIL,
        "No foreign key violations." if not fk_errors
        else f"{len(fk_errors)} foreign key violation(s).",
    ))

    chain_ok, chain_problems = audit.verify_chain(conn)
    checks.append(_check(
        "audit_chain", OK if chain_ok else FAIL,
        "Audit hash chain intact." if chain_ok
        else f"{len(chain_problems)} problem(s): {chain_problems[:3]}",
    ))

    # --- ingestion ---------------------------------------------------------
    stats = queue_stats(conn)
    failed = failed_jobs(conn)
    checks.append(_check(
        "ingest_queue",
        OK if not failed and not stats.in_progress else WARN,
        f"Queue: {stats.to_dict()}."
        + (f" {len(failed)} failed job(s) need attention." if failed else "")
        + (" Jobs stuck IN_PROGRESS will be recovered on next start."
           if stats.in_progress else ""),
        stats=stats.to_dict(),
        failures=[{"path": f["path"], "error": f["last_error"]} for f in failed[:10]],
    ))

    missing_originals = conn.execute(
        "SELECT doc_uid, storage_path FROM documents WHERE status='ACTIVE'"
    ).fetchall()
    gone = [dict(r) for r in missing_originals if not Path(r["storage_path"]).exists()]
    checks.append(_check(
        "document_originals",
        OK if not gone else FAIL,
        f"All {len(missing_originals)} indexed originals present." if not gone
        else f"{len(gone)} indexed document(s) no longer exist at their recorded path.",
        missing=gone[:10],
    ))

    broken_text = conn.execute(
        "SELECT COUNT(*) AS n FROM documents WHERE text_path IS NOT NULL "
        "AND extraction_error IS NOT NULL"
    ).fetchone()["n"]
    checks.append(_check(
        "text_extraction",
        OK if not broken_text else WARN,
        "All documents extracted." if not broken_text
        else f"{broken_text} document(s) recorded an extraction error and are indexed "
             "without text. They are visible, not hidden.",
    ))

    deps = dependency_report()
    absent = [name for name, info in deps.items() if not info["installed"]]
    checks.append(_check(
        "extraction_dependencies",
        OK if not absent else WARN,
        "All optional extractors installed." if not absent
        else ("Degraded extraction. Missing: "
              + ", ".join(f"{n} ({deps[n]['enables']})" for n in absent)),
        missing=absent,
    ))

    # --- litigation integrity ---------------------------------------------
    unsourced = conn.execute(
        "SELECT COUNT(*) AS n FROM facts WHERE verification_status IN "
        "('VERIFIED_PRIMARY','VERIFIED_SECONDARY') AND "
        "(source_document_id IS NULL OR source_page_or_paragraph IS NULL)"
    ).fetchone()["n"]
    checks.append(_check(
        "verified_facts_have_sources", OK if not unsourced else FAIL,
        "Every verified fact cites a source." if not unsourced
        else f"{unsourced} fact(s) marked verified without a source and locator.",
    ))

    unproven = conn.execute(
        "SELECT COUNT(*) AS n FROM filings WHERE filing_status IN "
        f"({','.join('?' * len(CONFIRMED_FILING_STATUSES))}) AND proof_type IS NULL",
        CONFIRMED_FILING_STATUSES,
    ).fetchone()["n"]
    checks.append(_check(
        "filing_proof", OK if not unproven else FAIL,
        "Every confirmed filing has proof." if not unproven
        else f"{unproven} filing(s) claim a confirmed status without proof.",
    ))

    protected = conn.execute(
        "SELECT COUNT(*) AS n FROM issues WHERE protected=1").fetchone()["n"]
    checks.append(_check(
        "protected_issues", OK if protected >= 23 else FAIL,
        f"{protected} protected issue(s) present."
        + ("" if protected >= 23 else " Expected at least 23 preloaded PSC/AEP issues."),
        count=protected,
    ))

    separate = conn.execute(
        "SELECT COUNT(*) AS n FROM matters WHERE folder='01_PSC_AEP' AND status='ACTIVE'"
    ).fetchone()["n"]
    checks.append(_check(
        "psc_matters_separate", OK if separate >= 6 else FAIL,
        f"{separate} PSC/AEP matters kept separate."
        + ("" if separate >= 6 else " Expected 6; matters must not be merged."),
    ))

    open_approvals = conn.execute(
        "SELECT COUNT(*) AS n FROM approvals WHERE state='OPEN'").fetchone()["n"]
    checks.append(_check(
        "pending_approvals", OK if open_approvals == 0 else WARN,
        "No decisions waiting." if open_approvals == 0
        else f"{open_approvals} decision(s) waiting for you.",
        count=open_approvals,
    ))

    pending_fleet = conn.execute(
        "SELECT COUNT(*) AS n FROM fleet_proposal_items WHERE decision='PENDING'"
    ).fetchone()["n"]
    checks.append(_check(
        "fleet_review_queue", OK if pending_fleet == 0 else WARN,
        "No Fleet proposals awaiting review." if pending_fleet == 0
        else f"{pending_fleet} Fleet proposal item(s) awaiting review.",
        count=pending_fleet,
    ))

    # --- backups -----------------------------------------------------------
    backups = backup_mod.list_backups(config)
    if not backups:
        backup_status, backup_detail = WARN, "No backup has been taken yet."
    elif backups[0]["verified"]:
        backup_status = OK
        backup_detail = f"{len(backups)} backup(s); most recent verified {backups[0]['created_at']}."
    else:
        backup_status = FAIL
        backup_detail = f"Most recent backup ({backups[0]['path']}) is unverified or failed verification."
    checks.append(_check("backups", backup_status, backup_detail, count=len(backups)))

    statuses = [c["status"] for c in checks]
    overall = FAIL if FAIL in statuses else (WARN if WARN in statuses else OK)

    return {
        "overall": overall,
        "checked_at": conn.execute(
            "SELECT strftime('%Y-%m-%dT%H:%M:%SZ','now') AS t").fetchone()["t"],
        "data_root": str(config.data_root),
        "database": str(config.db_path),
        "counts": {
            "ok": statuses.count(OK), "warn": statuses.count(WARN), "fail": statuses.count(FAIL),
        },
        "checks": checks,
    }


def format_report(report: dict[str, Any]) -> str:
    symbols = {OK: "  OK  ", WARN: " WARN ", FAIL: " FAIL "}
    lines = [
        f"Case Command health: {report['overall']}",
        f"Data root: {report['data_root']}",
        f"Database:  {report['database']}",
        "",
    ]
    for check in report["checks"]:
        lines.append(f"[{symbols.get(check['status'], '  ?   ')}] {check['check']}")
        lines.append(f"          {check['detail']}")
    counts = report["counts"]
    lines.append("")
    lines.append(f"{counts['ok']} ok, {counts['warn']} warning(s), {counts['fail']} failure(s)")
    return "\n".join(lines)
