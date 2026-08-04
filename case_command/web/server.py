"""Case Command web UI.

Built on the standard library's HTTP server plus Jinja2 templates. There is no
framework dependency and no build step: the same command runs on a laptop, on a
VM, and in CI. It binds to localhost only.
"""

from __future__ import annotations

import json
import sqlite3
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from .. import __version__, access, atlas, audit, fleet, health, triage, views
from ..config import Config, LITIGATION_FOLDERS, load_config
from ..db import open_database, utcnow

TEMPLATE_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


def _jinja_env():
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
    except ImportError as exc:  # pragma: no cover - environmental
        raise SystemExit(
            "The Case Command web UI needs Jinja2.\n"
            "  pip install jinja2\n"
            f"(import failed: {exc})"
        ) from exc

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["days_until"] = views.days_until
    env.filters["shortdate"] = lambda v: (v or "")[:10]
    env.globals["version"] = __version__
    env.globals["now"] = utcnow
    return env


class CaseCommandHandler(BaseHTTPRequestHandler):
    server_version = f"CaseCommand/{__version__}"
    config: Config
    env: Any

    # -- plumbing -----------------------------------------------------------
    def log_message(self, fmt: str, *args: Any) -> None:  # quieter default logging
        if self.path.startswith("/static"):
            return
        super().log_message(fmt, *args)

    def _conn(self) -> sqlite3.Connection:
        return open_database(self.config, migrate_if_needed=False)

    def _send(self, body: bytes, status: int = 200,
              content_type: str = "text/html; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _nav_counts(self, conn: sqlite3.Connection) -> dict[str, Any]:
        """Badge counts for the rail. Cheap queries only."""
        def n(sql: str) -> int:
            try:
                return int(conn.execute(sql).fetchone()[0])
            except sqlite3.Error:
                return 0

        return {
            "approvals": n("SELECT COUNT(*) FROM approvals WHERE state='OPEN'"),
            "fleet": n("SELECT COUNT(*) FROM fleet_proposal_items WHERE decision='PENDING'"),
            "unreviewed": n("SELECT COUNT(*) FROM documents WHERE triage_status='UNREVIEWED'"),
        }

    def _render(self, template: str, conn: sqlite3.Connection | None = None,
                **context: Any) -> None:
        context.setdefault("nav_active", "")
        if conn is not None and "nav_counts" not in context:
            context["nav_counts"] = self._nav_counts(conn)
        html = self.env.get_template(template).render(**context)
        self._send(html.encode("utf-8"))

    def _json(self, payload: Any, status: int = 200) -> None:
        self._send(json.dumps(payload, indent=2, default=str).encode("utf-8"),
                   status, "application/json; charset=utf-8")

    def _redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    @staticmethod
    def _int(params: dict[str, list[str]], key: str) -> int | None:
        raw = (params.get(key) or [""])[0].strip()
        try:
            return int(raw)
        except ValueError:
            return None

    @staticmethod
    def _str(params: dict[str, list[str]], key: str) -> str | None:
        value = (params.get(key) or [""])[0].strip()
        return value or None

    # -- routing ------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path.startswith("/static/"):
            return self._serve_static(parsed.path)

        routes: dict[str, Callable[[dict[str, list[str]]], None]] = {
            "/": self.view_dashboard,
            "/atlas": self.view_atlas,
            "/access": self.view_access,
            "/triage": self.view_triage,
            "/triage.csv": self.export_triage_csv,
            "/matter": self.view_matter,
            "/timeline": self.view_timeline,
            "/compare": self.view_compare,
            "/issues": self.view_issues,
            "/hearing": self.view_hearing,
            "/preservation": self.view_preservation,
            "/approvals": self.view_approvals,
            "/fleet": self.view_fleet,
            "/document": self.view_document,
            "/health": self.view_health,
            "/api/health": self.api_health,
            "/api/dashboard": self.api_dashboard,
        }
        handler = routes.get(parsed.path)
        if handler is None:
            return self._send(b"<h1>404</h1><p>No such view.</p>", 404)

        try:
            handler(params)
        except Exception:
            # Fail loud: the error is shown, not swallowed.
            detail = traceback.format_exc()
            self._send(
                f"<h1>500</h1><pre>{detail}</pre>".encode("utf-8"), 500)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        form = parse_qs(raw)

        try:
            if parsed.path == "/triage/decide":
                return self.post_triage_decide(form)
            if parsed.path == "/approvals/resolve":
                return self.post_resolve_approval(form)
            if parsed.path == "/fleet/decide":
                return self.post_fleet_decide(form)
            self._send(b"<h1>404</h1>", 404)
        except Exception:
            self._send(f"<h1>500</h1><pre>{traceback.format_exc()}</pre>".encode("utf-8"), 500)

    def _serve_static(self, path: str) -> None:
        name = Path(path).name
        target = STATIC_DIR / name
        if not target.exists() or not target.is_file():
            return self._send(b"not found", 404, "text/plain")
        content_type = "text/css" if name.endswith(".css") else "application/octet-stream"
        self._send(target.read_bytes(), 200, content_type)

    # -- views --------------------------------------------------------------
    def view_dashboard(self, params: dict[str, list[str]]) -> None:
        conn = self._conn()
        try:
            self._render("dashboard.html", conn, nav_active="dashboard",
                         data=views.dashboard(conn))
        finally:
            conn.close()

    def _triage_report(self, params: dict[str, list[str]]):
        conn = self._conn()
        try:
            triage.backfill_extracts(conn)
            return conn, triage.chronology(
                conn,
                matter_id=self._int(params, "matter_id"),
                folder=self._str(params, "folder"),
                status=self._str(params, "status"),
                include_duplicates=self._str(params, "hide_copies") != "1",
            )
        except BaseException:
            conn.close()
            raise

    def view_triage(self, params: dict[str, list[str]]) -> None:
        conn, data = self._triage_report(params)
        try:
            self._render("triage.html", conn, nav_active="triage", data=data,
                         matters=views.list_matters(conn),
                         folders=LITIGATION_FOLDERS,
                         statuses=triage.TRIAGE_STATUSES)
        finally:
            conn.close()

    def export_triage_csv(self, params: dict[str, list[str]]) -> None:
        conn, data = self._triage_report(params)
        try:
            body = triage.to_csv(data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition",
                             'attachment; filename="case_command_chronology.csv"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        finally:
            conn.close()

    def post_triage_decide(self, form: dict[str, list[str]]) -> None:
        document_id = int((form.get("document_id") or ["0"])[0])
        status = (form.get("status") or [""])[0]
        reviewer = (form.get("reviewer") or ["jacob"])[0]
        note = (form.get("note") or [""])[0] or None

        conn = self._conn()
        try:
            triage.set_status(conn, document_id, status, reviewer=reviewer, note=note)
            self._redirect("/triage")
        except ValueError as exc:
            self._send(f"<h1>400</h1><p>{exc}</p>".encode("utf-8"), 400)
        finally:
            conn.close()

    def view_atlas(self, params: dict[str, list[str]]) -> None:
        conn = self._conn()
        try:
            matters = views.list_matters(conn)
            matter_id = self._int(params, "matter_id")
            if matter_id is None and matters:
                matter_id = matters[0]["id"]
            data = atlas.build_atlas(conn, matter_id) if matter_id else {}
            self._render("atlas.html", conn, nav_active="atlas", data=data,
                         matters=matters,
                         coverage=atlas.coverage(conn, matter_id) if matter_id else {})
        finally:
            conn.close()

    def view_access(self, params: dict[str, list[str]]) -> None:
        conn = self._conn()
        try:
            matter_id = self._int(params, "matter_id")
            self._render("access.html", conn, nav_active="access",
                         barriers=access.list_barriers(conn, matter_id),
                         summary=access.summarize(conn, matter_id),
                         barrier_types=access.BARRIER_TYPES,
                         barrier_labels=access.BARRIER_LABELS,
                         matters=views.list_matters(conn), matter_id=matter_id)
        finally:
            conn.close()

    def view_matter(self, params: dict[str, list[str]]) -> None:
        matter_id = self._int(params, "id")
        conn = self._conn()
        try:
            if matter_id is None:
                return self._render("matters.html", conn, nav_active="matters",
                                    matters=views.list_matters(conn))
            data = views.matter_view(conn, matter_id)
            if not data:
                return self._send(b"<h1>404</h1><p>No such matter.</p>", 404)
            self._render("matter.html", conn, nav_active="matters", data=data)
        finally:
            conn.close()

    def view_timeline(self, params: dict[str, list[str]]) -> None:
        conn = self._conn()
        try:
            disputed_raw = self._str(params, "disputed")
            data = views.timeline(
                conn,
                matter_id=self._int(params, "matter_id"),
                start=self._str(params, "start"),
                end=self._str(params, "end"),
                actor=self._str(params, "actor"),
                filing_type=self._str(params, "filing_type"),
                boundary=self._str(params, "boundary"),
                verification=self._str(params, "verification"),
                disputed=None if disputed_raw is None else disputed_raw == "1",
                significance=self._str(params, "significance"),
            )
            self._render("timeline.html", conn, nav_active="timeline", data=data,
                         matters=views.list_matters(conn))
        finally:
            conn.close()

    def view_compare(self, params: dict[str, list[str]]) -> None:
        conn = self._conn()
        try:
            data = views.comparison(
                conn,
                mode=self._str(params, "mode") or "complaint_answer",
                left_id=self._int(params, "left"),
                right_id=self._int(params, "right"),
                matter_id=self._int(params, "matter_id"),
            )
            self._render("compare.html", conn, nav_active="compare", data=data,
                         matters=views.list_matters(conn))
        finally:
            conn.close()

    def view_issues(self, params: dict[str, list[str]]) -> None:
        conn = self._conn()
        try:
            self._render("issues.html", conn, nav_active="issues",
                         data=views.issue_matrix(conn, self._int(params, "matter_id")))
        finally:
            conn.close()

    def view_hearing(self, params: dict[str, list[str]]) -> None:
        matter_id = self._int(params, "matter_id")
        conn = self._conn()
        try:
            if matter_id is None:
                return self._render("matters.html", conn, nav_active="hearing",
                                    matters=views.list_matters(conn),
                                    prompt="Choose a matter to enter hearing mode.")
            data = views.hearing_mode(conn, matter_id, self._str(params, "date"))
            if not data:
                return self._send(b"<h1>404</h1><p>No such matter.</p>", 404)
            self._render("hearing.html", conn, nav_active="hearing", data=data)
        finally:
            conn.close()

    def view_preservation(self, params: dict[str, list[str]]) -> None:
        conn = self._conn()
        try:
            self._render("preservation.html", conn, nav_active="preservation",
                         data=views.preservation_view(conn, self._int(params, "matter_id")))
        finally:
            conn.close()

    def view_approvals(self, params: dict[str, list[str]]) -> None:
        conn = self._conn()
        try:
            self._render("approvals.html", conn, nav_active="approvals",
                         data=views.approvals_view(conn))
        finally:
            conn.close()

    def view_fleet(self, params: dict[str, list[str]]) -> None:
        conn = self._conn()
        try:
            self._render("fleet.html", conn, nav_active="fleet", data=views.fleet_view(conn))
        finally:
            conn.close()

    def view_document(self, params: dict[str, list[str]]) -> None:
        document_id = self._int(params, "id")
        conn = self._conn()
        try:
            data = views.document_view(conn, document_id) if document_id else {}
            if not data:
                return self._send(b"<h1>404</h1><p>No such document.</p>", 404)
            self._render("document.html", conn, nav_active="", data=data)
        finally:
            conn.close()

    def view_health(self, params: dict[str, list[str]]) -> None:
        conn = self._conn()
        try:
            self._render("health.html", conn, nav_active="health",
                         report=health.run_health_checks(self.config, conn))
        finally:
            conn.close()

    def api_health(self, params: dict[str, list[str]]) -> None:
        conn = self._conn()
        try:
            report = health.run_health_checks(self.config, conn)
            self._json(report, 200 if report["overall"] != "FAIL" else 503)
        finally:
            conn.close()

    def api_dashboard(self, params: dict[str, list[str]]) -> None:
        conn = self._conn()
        try:
            self._json(views.dashboard(conn))
        finally:
            conn.close()

    # -- actions ------------------------------------------------------------
    def post_resolve_approval(self, form: dict[str, list[str]]) -> None:
        approval_id = int((form.get("approval_id") or ["0"])[0])
        decision = (form.get("decision") or [""])[0]
        reviewer = (form.get("reviewer") or ["jacob"])[0]

        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
            if row is None:
                return self._send(b"<h1>404</h1><p>No such approval.</p>", 404)

            conn.execute(
                "UPDATE approvals SET decision=?, decided_by=?, decided_at=?, state='RESOLVED' "
                "WHERE id=?",
                (decision, reviewer, utcnow(), approval_id),
            )

            # Applying a matter assignment is the only side effect here, and it
            # only ever sets the matter — it never moves a file.
            if row["kind"] == "matter_assignment" and row["target_table"] == "documents":
                slug = decision.split("—")[0].strip()
                matter = conn.execute("SELECT id FROM matters WHERE slug=?", (slug,)).fetchone()
                if matter:
                    conn.execute(
                        "UPDATE documents SET matter_id=?, classification_approved=1, "
                        "last_reviewed_by=?, updated_at=? WHERE id=?",
                        (matter["id"], reviewer, utcnow(), row["target_id"]),
                    )

            audit.record(conn, actor=reviewer, action="APPROVAL_RESOLVED",
                         target_table=row["target_table"], target_id=row["target_id"],
                         matter_id=row["matter_id"],
                         summary=f"{row['kind']}: {decision}",
                         payload={"approval_id": approval_id})
            self._redirect("/approvals")
        finally:
            conn.close()

    def post_fleet_decide(self, form: dict[str, list[str]]) -> None:
        item_id = int((form.get("item_id") or ["0"])[0])
        decision = (form.get("decision") or [""])[0].upper()
        reviewer = (form.get("reviewer") or ["jacob"])[0]
        note = (form.get("note") or [""])[0] or None

        conn = self._conn()
        try:
            fleet.decide_item(conn, item_id, decision, reviewer=reviewer, note=note)
            self._redirect("/fleet")
        except ValueError as exc:
            self._send(f"<h1>400</h1><p>{exc}</p>".encode("utf-8"), 400)
        finally:
            conn.close()


def serve(config: Config | None = None, host: str = "127.0.0.1", port: int = 8787,
          *, open_browser: bool = False) -> None:
    config = config or load_config()

    conn = open_database(config)   # apply migrations once at startup
    conn.close()

    handler = type("BoundHandler", (CaseCommandHandler,),
                   {"config": config, "env": _jinja_env()})
    httpd = ThreadingHTTPServer((host, port), handler)

    print(f"Case Command {__version__}")
    print(f"  data root: {config.data_root}")
    print(f"  database:  {config.db_path}")
    print(f"  listening: http://{host}:{port}/")
    print("  health:    http://%s:%d/api/health" % (host, port))
    print("Ctrl-C to stop.")

    if open_browser:
        import webbrowser

        webbrowser.open(f"http://{host}:{port}/")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()
