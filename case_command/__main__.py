"""Case Command command-line interface.

    python -m case_command <command> [options]

Every destructive operation is off by default and requires an explicit flag.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, audit, backup, checks, fleet, health, migrate_tree, packets, views, watcher
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
