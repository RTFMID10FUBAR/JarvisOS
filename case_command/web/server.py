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

from .. import (
    __version__, access, api, atlas, audit, fleet, health, offline, triage,
    views,
)
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

        if parsed.path.startswith("/api/v1"):
            return self._api_get(parsed.path, params)

        routes: dict[str, Callable[[dict[str, list[str]]], None]] = {
            "/": self.view_dashboard,
            "/m": self.m_home,
            "/m/offline": self.m_offline,
            "/m/capture": self.m_capture,
            "/m/deadlines": self.m_deadlines,
            "/m/hearing": self.m_hearing,
            "/m/doc": self.m_doc,
            "/api/offline/bundle": self.api_offline_bundle,
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
        content_type = self.headers.get("Content-Type") or ""

        # The API reads its own body — JSON for most endpoints, multipart for
        # uploads. This check must come before the form parse below, or the body
        # is consumed here and arrives empty there.
        if parsed.path.startswith("/api/v1"):
            return self._api_post(parsed.path)

        # Multipart bodies are binary and are read by the handler itself.
        if content_type.startswith("multipart/form-data"):
            form: dict[str, list[str]] = {}
        else:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            form = parse_qs(raw)

        try:
            if parsed.path == "/api/capture":
                return self.post_capture()
            if parsed.path == "/m/pin":
                return self.post_pin(form)
            if parsed.path == "/m/unpin":
                return self.post_unpin(form)
            if parsed.path == "/m/pack":
                return self.post_pack(form)
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
        content_type = {
            ".css": "text/css",
            ".js": "text/javascript",
            ".svg": "image/svg+xml",
            ".webmanifest": "application/manifest+json",
            ".json": "application/json",
        }.get(target.suffix, "application/octet-stream")
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        # The service worker must be allowed to control the whole origin, not
        # just /static, or the offline pages below /m would never be served.
        if name == "sw.js":
            self.send_header("Service-Worker-Allowed", "/")
            self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

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

    # -- versioned API ------------------------------------------------------
    def _api_get(self, path: str, params: dict[str, list[str]]) -> None:
        conn = self._conn()
        try:
            rest = path[len("/api/v1"):].strip("/")
            parts = rest.split("/") if rest else []

            # Open endpoints: a client needs these before it has a token.
            if not parts:
                return self._json(api.index())
            if parts == ["health"]:
                report = health.run_health_checks(self.config, conn)
                return self._json(report, 200 if report["overall"] != "FAIL" else 503)

            device = api.authenticate(conn, self.headers.get("Authorization"))

            if parts == ["sync"]:
                return self._json(api.sync(conn, since=self._str(params, "since"),
                                           device=device))
            if parts == ["matters"]:
                return self._json({"matters": views.list_matters(conn)})
            if len(parts) == 2 and parts[0] == "matters":
                return self._json(api.matter_detail(conn, int(parts[1])))
            if len(parts) == 2 and parts[0] == "documents":
                return self._json(api.document_detail(conn, parts[1]))
            if len(parts) == 3 and parts[0] == "documents" and parts[2] == "original":
                body, filename, content_type = api.document_original(conn, parts[1])
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Content-Disposition",
                                 f'attachment; filename="{filename}"')
                self.end_headers()
                return self.wfile.write(body)
            if len(parts) == 2 and parts[0] == "hearing":
                return self._json(views.hearing_mode(conn, int(parts[1])))
            if parts == ["offline", "bundle"]:
                bundle = offline.build_bundle(conn, self._int(params, "matter_id"))
                offline.mark_synced(conn, [d["id"] for d in bundle["documents"]])
                return self._json(bundle)
            if parts == ["devices"]:
                return self._json({"devices": api.list_devices(conn)})

            self._json({"error": f"no such endpoint: {path}"}, 404)
        except api.ApiError as exc:
            self._json({"error": str(exc)}, exc.status)
        except ValueError as exc:
            self._json({"error": str(exc)}, 400)
        finally:
            conn.close()

    def _api_post(self, path: str) -> None:
        conn = self._conn()
        try:
            rest = path[len("/api/v1"):].strip("/")

            if rest == "pair":
                payload = self._read_json()
                return self._json(api.redeem_pairing_code(
                    conn,
                    code=payload.get("code", ""),
                    label=payload.get("label", "Phone"),
                    platform=payload.get("platform", "unknown"),
                    app_version=payload.get("app_version"),
                ))

            device = api.authenticate(conn, self.headers.get("Authorization"))

            if rest == "captures":
                return self.post_capture()
            if rest == "pins":
                payload = self._read_json()
                return self._json(offline.pin(
                    conn, int(payload["document_id"]),
                    reason=payload.get("reason", "MANUAL"),
                    include_original=bool(payload.get("include_original")),
                    actor=device["label"]))
            if rest == "pins/pack":
                payload = self._read_json()
                return self._json(offline.build_hearing_pack(
                    conn, int(payload["matter_id"]),
                    include_originals=bool(payload.get("include_originals")),
                    actor=device["label"]))

            self._json({"error": f"no such endpoint: {path}"}, 404)
        except api.ApiError as exc:
            self._json({"error": str(exc)}, exc.status)
        except (ValueError, KeyError) as exc:
            self._json({"error": str(exc)}, 400)
        finally:
            conn.close()

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise api.ApiError(f"invalid JSON body: {exc}", 400)

    # -- phone (PWA) --------------------------------------------------------
    def _m_render(self, template: str, **context: Any) -> None:
        """Phone views do not carry the desktop rail counts."""
        html = self.env.get_template(template).render(**context)
        self._send(html.encode("utf-8"))

    def m_home(self, params: dict[str, list[str]]) -> None:
        conn = self._conn()
        try:
            pins = conn.execute("SELECT COUNT(*) FROM offline_pins").fetchone()[0]
            self._m_render("m_home.html", tab="home", data=views.dashboard(conn),
                           pins=pins)
        finally:
            conn.close()

    def m_offline(self, params: dict[str, list[str]]) -> None:
        conn = self._conn()
        try:
            self._m_render("m_offline.html", tab="offline",
                           storage=offline.storage_report(conn),
                           matters=views.list_matters(conn))
        finally:
            conn.close()

    def m_capture(self, params: dict[str, list[str]]) -> None:
        conn = self._conn()
        try:
            self._m_render("m_capture.html", tab="capture",
                           matters=views.list_matters(conn),
                           captures=offline.capture_log(conn))
        finally:
            conn.close()

    def m_deadlines(self, params: dict[str, list[str]]) -> None:
        from .. import preservation as pres

        conn = self._conn()
        try:
            deadlines = pres.upcoming_deadlines(conn, limit=50)
            for item in deadlines:
                item["days_until"] = views.days_until(item.get("due_date"))
            data = views.dashboard(conn)
            self._m_render("m_deadlines.html", tab="deadlines",
                           overdue=[d for d in deadlines if (d["days_until"] or 0) < 0],
                           upcoming=[d for d in deadlines if (d["days_until"] or 0) >= 0],
                           risks=data["waiver_risks"])
        finally:
            conn.close()

    def m_hearing(self, params: dict[str, list[str]]) -> None:
        conn = self._conn()
        try:
            matter_id = self._int(params, "matter_id")
            data = views.hearing_mode(conn, matter_id) if matter_id else {}
            self._m_render("m_hearing.html", tab="hearing", data=data,
                           matters=views.list_matters(conn), back="/m")
        finally:
            conn.close()

    def m_doc(self, params: dict[str, list[str]]) -> None:
        conn = self._conn()
        try:
            document_id = self._int(params, "id")
            document = conn.execute("SELECT * FROM documents WHERE id=?",
                                    (document_id,)).fetchone() if document_id else None
            if document is None:
                return self._send(b"<h1>404</h1>", 404)
            pinned = conn.execute("SELECT 1 FROM offline_pins WHERE document_id=?",
                                  (document_id,)).fetchone() is not None
            text = ""
            if document["text_path"]:
                path = Path(document["text_path"])
                if path.exists():
                    text = path.read_text(encoding="utf-8", errors="replace")[:200_000]
            self._m_render("m_doc.html", tab="", document=dict(document),
                           text=text, pinned=pinned, back="/m/offline")
        finally:
            conn.close()

    def api_offline_bundle(self, params: dict[str, list[str]]) -> None:
        conn = self._conn()
        try:
            bundle = offline.build_bundle(conn, self._int(params, "matter_id"))
            offline.mark_synced(conn, [d["id"] for d in bundle["documents"]])
            self._json(bundle)
        finally:
            conn.close()

    # -- phone actions ------------------------------------------------------
    def post_pin(self, form: dict[str, list[str]]) -> None:
        conn = self._conn()
        try:
            offline.pin(conn, int((form.get("document_id") or ["0"])[0]))
            self._redirect("/m/offline")
        finally:
            conn.close()

    def post_unpin(self, form: dict[str, list[str]]) -> None:
        conn = self._conn()
        try:
            offline.unpin(conn, int((form.get("document_id") or ["0"])[0]))
            self._redirect("/m/offline")
        finally:
            conn.close()

    def post_pack(self, form: dict[str, list[str]]) -> None:
        conn = self._conn()
        try:
            offline.build_hearing_pack(conn, int((form.get("matter_id") or ["0"])[0]))
            self._redirect("/m/offline")
        finally:
            conn.close()

    def post_capture(self) -> None:
        """Accept evidence captured on the device.

        The body is multipart. `client_uid` is generated on the phone, so an
        upload replayed after a dropped connection is recognised as the same
        capture rather than counted twice.
        """
        import cgi

        environ = {"REQUEST_METHOD": "POST",
                   "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                   "CONTENT_LENGTH": self.headers.get("Content-Length", "0")}
        try:
            fields = cgi.FieldStorage(fp=self.rfile, headers=self.headers,
                                      environ=environ, keep_blank_values=True)
        except Exception as exc:
            return self._json({"error": f"could not read upload: {exc}"}, 400)

        def field(name: str, default: str = "") -> str:
            value = fields.getvalue(name, default)
            return value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)

        upload = fields["file"] if "file" in fields else None
        if upload is None or not getattr(upload, "filename", None):
            return self._json({"error": "no file in upload"}, 400)

        data = upload.file.read()
        if not data:
            return self._json({"error": "empty upload"}, 400)

        matter_raw = field("matter_id")
        conn = self._conn()
        try:
            result = offline.accept_capture(
                conn, self.config,
                client_uid=field("client_uid") or f"cap-{utcnow()}",
                filename=upload.filename,
                data=data,
                capture_kind=field("capture_kind", "PHOTO") or "PHOTO",
                matter_id=int(matter_raw) if matter_raw.isdigit() else None,
                captured_at=field("captured_at") or None,
                device_note=field("device_note") or None,
            )
            self._json(result)
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
