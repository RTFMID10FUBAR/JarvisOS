"""Case Command command-line interface.

    python -m case_command <command> [options]

Every destructive operation is off by default and requires an explicit flag.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import (
    __version__, access, audit, backup, checks, fleet, health, migrate_tree,
    packets, triage, views, watcher,
)
from .config import LITIGATION_FOLDERS, ensure_layout, load_config
from .db import open_database
from .ingest import ingest_path, scan_all


def _config(args: argparse.Namespace):
    return load_config(data_root=getattr(args, "data_root", None))


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


# ---------------------------------------------------------------------------
def cmd_init(args) -> int:
    config = _config(args)
    created = ensure_layout(config)
    conn = open_database(config)
    try:
        from .db import applied_migrations

        print(f"Data root:  {config.data_root}")
        print(f"Database:   {config.db_path}")
        print(f"Created {len(created)} director{'y' if len(created) == 1 else 'ies'}.")
        print(f"Migrations: {', '.join(applied_migrations(conn))}")
        print("\nApproved folder structure:")
        for name in LITIGATION_FOLDERS:
            print(f"  {name}")
        audit.record(conn, actor=args.actor, action="INIT",
                     summary=f"{len(created)} directories created")
    finally:
        conn.close()
    return 0


def cmd_ingest(args) -> int:
    config = _config(args)
    conn = open_database(config)
    try:
        if args.path:
            results = [ingest_path(config, conn, Path(args.path), actor=args.actor,
                                   allow_ocr=not args.no_ocr)]
        else:
            results = scan_all(config, conn, actor=args.actor, allow_ocr=not args.no_ocr)

        summary: dict[str, int] = {}
        for result in results:
            summary[result.status] = summary.get(result.status, 0) + 1
            marker = {"ingested": "+", "duplicate": "=", "failed": "!",
                      "unchanged": ".", "skipped": "-"}.get(result.status, "?")
            print(f"{marker} {result.status:10} {Path(result.path).name}"
                  + (f"  {result.doc_uid}" if result.doc_uid else "")
                  + (f"  ({result.error})" if result.error else ""))
        print(f"\n{summary}")
        if args.json:
            _print([r.to_dict() for r in results])
    finally:
        conn.close()
    return 0


def cmd_watch(args) -> int:
    config = _config(args)
    conn = open_database(config)
    try:
        watcher.watch(config, conn, interval=args.interval,
                      iterations=args.once and 1 or None,
                      allow_ocr=not args.no_ocr)
    finally:
        conn.close()
    return 0


def cmd_status(args) -> int:
    config = _config(args)
    conn = open_database(config, migrate_if_needed=False)
    try:
        data = views.dashboard(conn)
        if args.json:
            _print(data)
            return 0
        print(f"Case Command {__version__} — {config.data_root}\n")
        print(f"Documents: {data['counts']['documents']}   "
              f"Issues: {data['counts']['issues']}   "
              f"Open unknowns: {data['counts']['unknowns']}")
        if data["next_deadline"]:
            deadline = data["next_deadline"]
            print(f"\nNext deadline: {deadline['due_date']} — {deadline['title']} "
                  f"({deadline['days_until']} day(s)) [{deadline['verification_status']}]")
        print(f"\nToday's actions ({len(data['todays_actions'])}):")
        for action in data["todays_actions"][:10]:
            print(f"  [{action['priority']:6}] {action['action']}")
        print(f"\nWaiver risks:        {len(data['waiver_risks'])}")
        print(f"Open contradictions: {len(data['open_contradictions'])}")
        print(f"Unresolved motions:  {len(data['unresolved_motions'])}")
        print(f"Pending approvals:   {len(data['open_approvals'])}")
    finally:
        conn.close()
    return 0


def cmd_health(args) -> int:
    config = _config(args)
    conn = open_database(config, migrate_if_needed=False)
    try:
        report = health.run_health_checks(config, conn)
        if args.json:
            _print(report)
        else:
            print(health.format_report(report))
        return 0 if report["overall"] != "FAIL" else 1
    finally:
        conn.close()


def cmd_check(args) -> int:
    """Run the anti-omission checks before marking a draft final."""
    config = _config(args)
    conn = open_database(config, migrate_if_needed=False)
    try:
        draft = Path(args.draft).read_text(encoding="utf-8", errors="replace") if args.draft else ""
        report = checks.run_all(conn, args.matter_id, draft)
        if args.json:
            _print(report.to_dict())
            return 0 if report.ok else 1
        print(f"Pre-final checks for matter {args.matter_id}: "
              f"{'PASS' if report.ok else 'BLOCKED'}")
        print(f"{len(report.blockers)} blocker(s), {len(report.findings)} finding(s)\n")
        for finding in report.findings:
            if finding.severity == "INFO" and not args.verbose:
                continue
            print(f"[{finding.severity:7}] {finding.check:13} {finding.title}")
            print(f"              {finding.detail}")
            if finding.remedy:
                print(f"              -> {finding.remedy}")
        return 0 if report.ok else 1
    finally:
        conn.close()


def cmd_triage(args) -> int:
    """Chronological list of every document, for deciding what is what."""
    config = _config(args)
    conn = open_database(config)
    try:
        if args.action == "list":
            triage.backfill_extracts(conn)
            report = triage.chronology(
                conn, matter_id=args.matter_id, folder=args.folder,
                status=args.status, include_duplicates=not args.hide_copies)
            if args.csv:
                out = triage.to_csv(report)
                if args.out:
                    Path(args.out).write_text(out, encoding="utf-8")
                    print(f"Wrote {report['total']} row(s) to {args.out}")
                else:
                    print(out, end="")
            elif args.json:
                _print(report)
            else:
                print(triage.format_table(report))
        elif args.action == "copies":
            groups = triage.copy_locations(conn)
            if args.json:
                _print(groups)
            elif not groups:
                print("No redundant copies recorded. Every document exists in one place.")
            else:
                total = sum(len(g["copies"]) for g in groups)
                print(f"{len(groups)} document(s) with {total} redundant copy location(s).\n")
                for group in groups:
                    print(f"{group['doc_uid']}  {group['date'] or '(no date)'}  "
                          f"{(group['what_it_is'] or '')[:60]}")
                    print(f"    canonical: {group['canonical_path']}")
                    for copy in group["copies"]:
                        print(f"    copy:      {copy['path']}  [{copy['disposition']}]")
                    print()
        elif args.action == "propose-archive":
            _print(triage.propose_copy_archive(conn, reviewer=args.actor))
        elif args.action == "set":
            _print(triage.set_status(conn, args.document_id, args.status_value,
                                     reviewer=args.actor, note=args.note))
    finally:
        conn.close()
    return 0


def cmd_access(args) -> int:
    """Log and review access barriers — what actually prevented a filing."""
    config = _config(args)
    conn = open_database(config)
    try:
        if args.action == "log":
            if not args.blocked:
                print("--blocked is required: name the specific filing, service, or "
                      "appearance that was prevented. A general statement of hardship "
                      "is not evidence.", file=sys.stderr)
                return 1
            result = access.log_barrier(
                conn,
                incident_date=args.date,
                barrier_type=args.type,
                what_was_blocked=args.blocked,
                matter_id=args.matter_id,
                deadline_affected=args.deadline,
                deadline_date=args.deadline_date,
                workaround_attempted=args.tried,
                workaround_result=args.result,
                hours_lost=args.hours,
                cost_incurred=args.cost,
                reported_to_tribunal=args.reported,
                how_reported=args.how_reported,
                evidence_document_id=args.evidence_id,
                notes=args.note,
                actor=args.actor,
            )
            _print(result)
        elif args.action == "list":
            if args.json:
                _print(access.list_barriers(conn, args.matter_id, args.type))
            else:
                print(access.format_log(conn, args.matter_id))
        elif args.action == "summary":
            _print(access.summarize(conn, args.matter_id))
        elif args.action == "attach":
            _print(access.attach_evidence(conn, args.barrier_id, args.evidence_id,
                                          locator=args.locator, actor=args.actor))
    finally:
        conn.close()
    return 0


def cmd_backup(args) -> int:
    config = _config(args)
    conn = open_database(config, migrate_if_needed=False)
    try:
        if args.action == "create":
            _print(backup.create_backup(config, conn, label=args.label, actor=args.actor))
        elif args.action == "list":
            _print(backup.list_backups(config))
        elif args.action == "verify":
            _print(backup.verify_backup(config, Path(args.file)))
        elif args.action == "restore":
            result = backup.restore(config, Path(args.file), approved=args.approve,
                                    actor=args.actor)
            _print(result)
            return 0 if result.get("restored") else 1
        elif args.action == "prune":
            _print(backup.prune_candidates(config, keep=args.keep))
    finally:
        conn.close()
    return 0


def cmd_migrate(args) -> int:
    config = _config(args)
    conn = open_database(config)
    try:
        if args.action == "plan":
            plan = migrate_tree.build_plan(config)
            path = migrate_tree.write_plan(config, plan)
            print(migrate_tree.summarize_plan(plan))
            print(f"\nPlan written to {path}")
        elif args.action == "dry-run":
            plan = migrate_tree.build_plan(config)
            migrate_tree.write_plan(config, plan)
            _print(migrate_tree.dry_run(config, plan))
        elif args.action == "execute":
            plan = migrate_tree.build_plan(config)
            migrate_tree.write_plan(config, plan)
            result = migrate_tree.execute(config, conn, plan, approved=args.approve,
                                          actor=args.actor)
            _print(result)
            return 0 if result.get("executed") else 1
        elif args.action == "rollback":
            _print(migrate_tree.rollback(config, conn, Path(args.manifest), actor=args.actor))
    finally:
        conn.close()
    return 0


def cmd_fleet(args) -> int:
    config = _config(args)
    conn = open_database(config, migrate_if_needed=False)
    try:
        if args.action == "packet":
            packet = packets.build_packet(
                conn, task=args.task, job_type=args.job_type,
                matter_id=args.matter_id, issue_id=args.issue_id)
            _print(packet)
            print(f"\n# packet size: {packets.packet_size(packet)} characters",
                  file=sys.stderr)
        elif args.action == "submit":
            payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
            try:
                _print(fleet.submit_proposal(conn, payload, agent=args.agent))
            except fleet.FleetRejection as exc:
                print(str(exc), file=sys.stderr)
                return 1
        elif args.action == "pending":
            _print(fleet.pending_items(conn))
        elif args.action == "decide":
            _print(fleet.decide_item(conn, args.item_id, args.decision,
                                     reviewer=args.actor, note=args.note))
    finally:
        conn.close()
    return 0


def cmd_audit(args) -> int:
    config = _config(args)
    conn = open_database(config, migrate_if_needed=False)
    try:
        if args.action == "verify":
            ok, problems = audit.verify_chain(conn)
            print("audit chain: " + ("INTACT" if ok else "BROKEN"))
            for problem in problems:
                print(f"  {problem}")
            return 0 if ok else 1
        _print(audit.recent(conn, limit=args.limit))
    finally:
        conn.close()
    return 0


def cmd_serve(args) -> int:
    from .web.server import serve

    serve(_config(args), host=args.host, port=args.port, open_browser=args.open)
    return 0


# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="case-command",
        description="Case Command — authoritative litigation record.")
    parser.add_argument("--version", action="version", version=f"Case Command {__version__}")
    parser.add_argument("--data-root", help="override the litigation data root")
    parser.add_argument("--actor", default="jacob", help="who is performing this action")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create the approved folder structure and database")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("ingest", help="ingest a file, or every approved folder")
    p.add_argument("path", nargs="?", help="a single file; omit to scan every folder")
    p.add_argument("--no-ocr", action="store_true", help="skip OCR fallback")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("watch", help="continuously watch the approved folders")
    p.add_argument("--interval", type=float, default=5.0)
    p.add_argument("--once", action="store_true", help="run a single pass and exit")
    p.add_argument("--no-ocr", action="store_true")
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("status", help="command dashboard summary")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("health", help="run every health check")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_health)

    p = sub.add_parser("check", help="anti-omission checks before marking a draft final")
    p.add_argument("matter_id", type=int)
    p.add_argument("--draft", help="path to the draft being checked")
    p.add_argument("--json", action="store_true")
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("triage", help="chronological document list: date, extract, flags")
    p.add_argument("action", choices=["list", "copies", "propose-archive", "set"],
                   nargs="?", default="list")
    p.add_argument("--matter-id", type=int)
    p.add_argument("--folder")
    p.add_argument("--status", help="filter by triage status")
    p.add_argument("--hide-copies", action="store_true",
                   help="omit byte-identical copies from the list")
    p.add_argument("--csv", action="store_true", help="emit CSV for a spreadsheet")
    p.add_argument("--out", help="write CSV to this path")
    p.add_argument("--json", action="store_true")
    p.add_argument("--document-id", type=int, help="for `set`")
    p.add_argument("--status-value", help="for `set`: "
                   + ", ".join(triage.TRIAGE_STATUSES))
    p.add_argument("--note")
    p.set_defaults(func=cmd_triage)

    p = sub.add_parser("access",
                       help="log what prevented a filing — evidence of prejudice")
    p.add_argument("action", choices=["log", "list", "summary", "attach"], nargs="?",
                   default="list")
    p.add_argument("--date", help="incident date, YYYY-MM-DD")
    p.add_argument("--type", choices=list(access.BARRIER_TYPES), default="OTHER")
    p.add_argument("--blocked", help="the specific filing, service, or appearance prevented")
    p.add_argument("--matter-id", type=int)
    p.add_argument("--deadline", help="the deadline this affected")
    p.add_argument("--deadline-date")
    p.add_argument("--tried", help="workaround attempted")
    p.add_argument("--result", help="what came of the workaround")
    p.add_argument("--hours", type=float, help="hours lost")
    p.add_argument("--cost", type=float, help="cost incurred")
    p.add_argument("--reported", action="store_true",
                   help="the tribunal was told about this barrier")
    p.add_argument("--how-reported")
    p.add_argument("--barrier-id", type=int, help="for `attach`")
    p.add_argument("--evidence-id", type=int,
                   help="document id of supporting proof (shutoff notice, receipt)")
    p.add_argument("--locator", help="page or paragraph in the supporting document")
    p.add_argument("--note")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_access)

    p = sub.add_parser("backup", help="backup, verify, and restore")
    p.add_argument("action", choices=["create", "list", "verify", "restore", "prune"])
    p.add_argument("--file", help="backup file for verify/restore")
    p.add_argument("--label", default="manual")
    p.add_argument("--keep", type=int, default=10)
    p.add_argument("--approve", action="store_true",
                   help="required to actually restore over the live database")
    p.set_defaults(func=cmd_backup)

    p = sub.add_parser("migrate", help="inventory, plan, dry-run, and roll back file moves")
    p.add_argument("action", choices=["plan", "dry-run", "execute", "rollback"])
    p.add_argument("--manifest", help="rollback manifest path")
    p.add_argument("--approve", action="store_true",
                   help="required to actually move original files")
    p.set_defaults(func=cmd_migrate)

    p = sub.add_parser("fleet", help="build packets, submit proposals, review items")
    p.add_argument("action", choices=["packet", "submit", "pending", "decide"])
    p.add_argument("--task", default="")
    p.add_argument("--job-type", default="document_extraction")
    p.add_argument("--matter-id", type=int)
    p.add_argument("--issue-id", type=int)
    p.add_argument("--file", help="JSON file containing a Fleet response")
    p.add_argument("--agent", default="fleet")
    p.add_argument("--item-id", type=int)
    p.add_argument("--decision", choices=["APPROVED", "REJECTED"])
    p.add_argument("--note")
    p.set_defaults(func=cmd_fleet)

    p = sub.add_parser("audit", help="inspect and verify the append-only audit log")
    p.add_argument("action", choices=["verify", "recent"], default="recent", nargs="?")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("serve", help="start the web UI")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8787)
    p.add_argument("--open", action="store_true", help="open a browser window")
    p.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
