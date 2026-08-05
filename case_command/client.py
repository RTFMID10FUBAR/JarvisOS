"""Reference sync client — the phone side of the protocol, written to be ported.

A web wrapper shows what the desktop renders. A standalone app holds its own
copy of the record and reconciles with it. That difference is entirely in this
file: pairing, a cursor, a local mirror, cached originals, and a capture queue
that survives being offline.

This module exists for three reasons.

1.  It is the specification. Everything a native client must do is here in
    executable form, so the Kotlin or Swift port is a translation of logic that
    has been run rather than an invention that has not.

2.  It is the conformance harness. `conformance()` drives a live server through
    every rule the protocol makes and reports pass or fail per rule. A native
    client can be checked against the same list, so "the app works" becomes a
    thing that is demonstrated rather than asserted.

3.  It is honest about the network. The interesting cases are all failures — a
    dropped upload, a capped sync, a revoked device, a courthouse basement with
    no signal. Those are tested here, not hoped about.

Standard library only. No cloud, no account, no third party ever holds the
record.

The client is read-only against the case, with one deliberate exception:
evidence captured on the device is uploaded. It cannot edit a fact, mark
anything verified, or file anything. Those limits live on the server too — this
is a client, and a client's promises are not security.
"""

from __future__ import annotations

import json
import mimetypes
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable, Iterable

from .hashing import sha256_bytes

#: Tables the server replicates. Kept here so a client can tell the difference
#: between "this table had no changes" and "this server is newer than I am".
MIRROR_TABLES = (
    "matters", "documents", "issues", "deadlines", "events",
    "preservation_items", "access_barriers",
)

#: Rows per table per sync request. Small enough that a bad connection can
#: still make progress, and the client loops until the server stops saying
#: there is more.
SYNC_PAGE = 500

#: A sync that says "more available" is not finished. This bounds the loop so a
#: server bug cannot spin a phone's battery flat.
MAX_SYNC_ROUNDS = 100


class ClientError(Exception):
    """Something the client could not do. Carries the HTTP status when there was one."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class Unreachable(ClientError):
    """No answer from the server. Not an error in the record — an error in the network.

    This distinction matters more than it looks. Unreachable means *fall back to
    the mirror and keep working*. Any other error means something is actually
    wrong and the user should be told.
    """


class Revoked(ClientError):
    """This device's token no longer works.

    Never retried silently. A revoked phone that quietly keeps trying looks to
    the user like a phone that is still syncing.
    """


# ---------------------------------------------------------------------------
# local store — what the device holds when there is no network
# ---------------------------------------------------------------------------
MIRROR_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- One row per synced record. Storing the payload as JSON rather than as seven
-- mirrored schemas is deliberate: the server's columns can grow without the
-- phone needing a migration to keep working, and a phone that cannot sync is
-- worse than a phone that does not know about a new column.
CREATE TABLE IF NOT EXISTS records (
    table_name TEXT NOT NULL,
    row_id     INTEGER NOT NULL,
    matter_id  INTEGER,
    updated_at TEXT,
    payload    TEXT NOT NULL,
    PRIMARY KEY (table_name, row_id)
);
CREATE INDEX IF NOT EXISTS idx_records_matter ON records(table_name, matter_id);

-- Cached original bytes, keyed by the server's digest. The key is the content,
-- so a corrupted or substituted file cannot masquerade as the original.
CREATE TABLE IF NOT EXISTS blobs (
    sha256     TEXT PRIMARY KEY,
    doc_uid    TEXT,
    filename   TEXT,
    byte_size  INTEGER NOT NULL,
    data       BLOB NOT NULL,
    cached_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- Captures taken while offline. They wait here until there is a connection.
-- client_uid is generated once, on the device, and reused on every retry, so a
-- dropped upload becomes one capture rather than two.
CREATE TABLE IF NOT EXISTS outbox (
    client_uid  TEXT PRIMARY KEY,
    filename    TEXT NOT NULL,
    data        BLOB NOT NULL,
    matter_id   INTEGER,
    kind        TEXT NOT NULL DEFAULT 'PHOTO',
    captured_at TEXT NOT NULL,
    note        TEXT,
    state       TEXT NOT NULL DEFAULT 'PENDING',
    attempts    INTEGER NOT NULL DEFAULT 0,
    last_error  TEXT,
    queued_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
"""


class LocalStore:
    """The device's own copy. Everything readable offline is read from here."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(MIRROR_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # -- meta ---------------------------------------------------------------
    def get(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set(self, key: str, value: str | None) -> None:
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        self.conn.commit()

    @property
    def cursor(self) -> str | None:
        return self.get("sync_cursor")

    @property
    def token(self) -> str | None:
        return self.get("token")

    # -- records ------------------------------------------------------------
    def apply(self, table: str, rows: Iterable[dict[str, Any]]) -> int:
        count = 0
        for row in rows:
            self.conn.execute(
                "INSERT INTO records(table_name, row_id, matter_id, updated_at, payload) "
                "VALUES(?,?,?,?,?) ON CONFLICT(table_name, row_id) DO UPDATE SET "
                "matter_id=excluded.matter_id, updated_at=excluded.updated_at, "
                "payload=excluded.payload",
                (table, int(row["id"]), row.get("matter_id"),
                 row.get("updated_at"), json.dumps(row, sort_keys=True)))
            count += 1
        self.conn.commit()
        return count

    def rows(self, table: str, *, matter_id: int | None = None) -> list[dict[str, Any]]:
        if matter_id is None:
            cur = self.conn.execute(
                "SELECT payload FROM records WHERE table_name=? ORDER BY row_id", (table,))
        else:
            cur = self.conn.execute(
                "SELECT payload FROM records WHERE table_name=? AND matter_id=? "
                "ORDER BY row_id", (table, matter_id))
        return [json.loads(r["payload"]) for r in cur]

    def row(self, table: str, row_id: int) -> dict[str, Any] | None:
        found = self.conn.execute(
            "SELECT payload FROM records WHERE table_name=? AND row_id=?",
            (table, row_id)).fetchone()
        return json.loads(found["payload"]) if found else None

    def counts(self) -> dict[str, int]:
        return {t: self.conn.execute(
            "SELECT COUNT(*) c FROM records WHERE table_name=?", (t,)).fetchone()["c"]
            for t in MIRROR_TABLES}

    # -- blobs --------------------------------------------------------------
    def put_blob(self, *, sha256: str, doc_uid: str, filename: str, data: bytes) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO blobs(sha256, doc_uid, filename, byte_size, data) "
            "VALUES(?,?,?,?,?)", (sha256, doc_uid, filename, len(data), data))
        self.conn.commit()

    def blob(self, sha256: str) -> bytes | None:
        """Cached bytes, or None.

        The digest is recomputed on the way out. A cache that can hand back the
        wrong bytes is worse than no cache: this record has to be quotable in a
        hearing, and "it was in my phone's cache" is not a provenance.
        """
        row = self.conn.execute("SELECT data FROM blobs WHERE sha256=?", (sha256,)).fetchone()
        if row is None:
            return None
        data = bytes(row["data"])
        if sha256_bytes(data) != sha256:
            self.conn.execute("DELETE FROM blobs WHERE sha256=?", (sha256,))
            self.conn.commit()
            raise ClientError(
                f"cached copy of {sha256[:12]} does not match its digest; it was discarded")
        return data

    def cached_bytes(self) -> int:
        return self.conn.execute(
            "SELECT COALESCE(SUM(byte_size), 0) n FROM blobs").fetchone()["n"]

    # -- outbox -------------------------------------------------------------
    def queue_capture(self, *, filename: str, data: bytes, captured_at: str,
                      matter_id: int | None = None, kind: str = "PHOTO",
                      note: str | None = None, client_uid: str | None = None) -> str:
        client_uid = client_uid or uuid.uuid4().hex
        self.conn.execute(
            "INSERT INTO outbox(client_uid, filename, data, matter_id, kind, "
            "captured_at, note) VALUES(?,?,?,?,?,?,?)",
            (client_uid, filename, data, matter_id, kind, captured_at, note))
        self.conn.commit()
        return client_uid

    def pending(self) -> list[sqlite3.Row]:
        return list(self.conn.execute(
            "SELECT * FROM outbox WHERE state='PENDING' ORDER BY queued_at"))

    def mark_sent(self, client_uid: str) -> None:
        self.conn.execute("UPDATE outbox SET state='SENT', last_error=NULL "
                          "WHERE client_uid=?", (client_uid,))
        self.conn.commit()

    def mark_failed(self, client_uid: str, error: str) -> None:
        self.conn.execute(
            "UPDATE outbox SET attempts=attempts+1, last_error=? WHERE client_uid=?",
            (error, client_uid))
        self.conn.commit()


# ---------------------------------------------------------------------------
# client
# ---------------------------------------------------------------------------
class CaseCommandClient:
    """Talks to one Case Command server on behalf of one paired device."""

    def __init__(self, base_url: str, store: LocalStore, *, timeout: float = 15.0) -> None:
        self.base = base_url.rstrip("/")
        self.store = store
        self.timeout = timeout

    # -- transport ----------------------------------------------------------
    def _request(self, method: str, path: str, *, body: bytes | None = None,
                 content_type: str | None = None, auth: bool = True,
                 raw: bool = False) -> Any:
        url = f"{self.base}/api/v1{path}"
        req = urllib.request.Request(url, data=body, method=method)
        if content_type:
            req.add_header("Content-Type", content_type)
        if auth:
            token = self.store.token
            if not token:
                raise ClientError("this device is not paired yet")
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = resp.read()
                return payload if raw else json.loads(payload.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            try:
                detail = json.loads(detail).get("error", detail)
            except (ValueError, AttributeError):
                pass
            if exc.code == 403:
                raise Revoked(detail, 403) from exc
            raise ClientError(detail, exc.code) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            # No answer. Not a problem with the record — a problem with the
            # network. The caller falls back to the mirror.
            raise Unreachable(str(exc)) from exc

    # -- pairing ------------------------------------------------------------
    def pair(self, code: str, *, label: str, platform: str = "reference",
             app_version: str | None = None) -> dict[str, Any]:
        """Redeem a code shown on the desktop. The token is stored locally, once."""
        payload = self._request(
            "POST", "/pair", auth=False, content_type="application/json",
            body=json.dumps({"code": code.strip().upper(), "label": label,
                             "platform": platform, "app_version": app_version}).encode())
        self.store.set("token", payload["token"])
        self.store.set("device_uid", payload["device_uid"])
        self.store.set("server", self.base)
        return payload

    def index(self) -> dict[str, Any]:
        return self._request("GET", "/", auth=False)

    # -- sync ---------------------------------------------------------------
    def sync(self, *, full: bool = False, page_size: int = SYNC_PAGE,
             on_round: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
        """Pull everything that changed, looping until the server stops saying there is more.

        The cursor is only advanced once the server reports nothing further is
        waiting. A client that saves the cursor after a truncated page believes
        it is current while rows it has never seen sit on the other side — and
        it will never ask for them again, because as far as it knows it already
        has them. That is how a sync client loses a document silently, and it is
        the one failure this system cannot tolerate.
        """
        since = None if full else self.store.cursor
        applied: dict[str, int] = {t: 0 for t in MIRROR_TABLES}
        rounds = 0
        cursor = since
        held_back = False

        while True:
            rounds += 1
            if rounds > MAX_SYNC_ROUNDS:
                raise ClientError(
                    f"sync did not converge after {MAX_SYNC_ROUNDS} rounds; "
                    "the server keeps reporting more changes")
            query = [f"limit={int(page_size)}"]
            if cursor:
                query.append(f"since={urllib.parse.quote(cursor)}")
            page = self._request("GET", "/sync?" + "&".join(query))

            for table, rows in page.get("changed", {}).items():
                if table not in MIRROR_TABLES:
                    # A newer server. Skip it rather than fail: the phone stays
                    # useful, and unknown tables are reported below.
                    continue
                applied[table] += self.store.apply(table, rows)

            cursor = page["next_cursor"]
            if on_round:
                on_round(page)
            if not page.get("more_available"):
                break
            # More is waiting. The cursor stays out of the store until the
            # server says it is finished, so a crash mid-loop resumes from the
            # last complete position rather than skipping the remainder.
            held_back = True

        self.store.set("sync_cursor", cursor)
        self.store.set("last_sync_at", cursor)
        unknown = sorted(set(page.get("counts", {})) - set(MIRROR_TABLES))
        return {
            "rounds": rounds,
            "applied": applied,
            "total": sum(applied.values()),
            "cursor": cursor,
            "full_sync": since is None,
            "unknown_tables": unknown,
            "paged": held_back,
        }

    def sync_or_offline(self) -> dict[str, Any]:
        """Sync if the network is there; otherwise say so and carry on.

        This is the call a phone screen should make. Being offline is a normal
        state for this system, not an error condition.
        """
        try:
            result = self.sync()
            result["online"] = True
            return result
        except Unreachable as exc:
            return {"online": False, "reason": str(exc),
                    "cursor": self.store.cursor,
                    "counts": self.store.counts(),
                    "note": "Showing the copy held on this device. "
                            f"Last synced: {self.store.get('last_sync_at') or 'never'}."}

    # -- documents ----------------------------------------------------------
    def document(self, doc_uid: str) -> dict[str, Any]:
        return self._request("GET", f"/documents/{urllib.parse.quote(doc_uid)}")

    def pin(self, doc_uid: str, *, sha256: str, filename: str) -> int:
        """Download an original and keep it. Verified against the server's digest.

        If the bytes that arrive do not hash to what the record says they
        should, nothing is cached. A wrong exhibit at a hearing is worse than a
        missing one, because a missing one is obvious.
        """
        data = self._request("GET", f"/documents/{urllib.parse.quote(doc_uid)}/original",
                             raw=True)
        digest = sha256_bytes(data)
        if digest != sha256:
            raise ClientError(
                f"{doc_uid}: downloaded bytes hash to {digest[:12]} but the record "
                f"says {sha256[:12]}; nothing was cached")
        self.store.put_blob(sha256=sha256, doc_uid=doc_uid, filename=filename, data=data)
        return len(data)

    def pin_matter(self, matter_id: int, *, budget_bytes: int | None = None) -> dict[str, Any]:
        """Cache the originals for a matter, largest-first refusal on budget.

        Reports exactly what it skipped. A pack that silently drops documents is
        the failure mode this whole system exists to prevent.
        """
        cached, skipped, failed = [], [], []
        used = self.store.cached_bytes()
        for doc in self.store.rows("documents", matter_id=matter_id):
            sha, uid = doc.get("sha256"), doc.get("doc_uid")
            if not sha or not uid:
                skipped.append({"doc_uid": uid, "reason": "no digest recorded"})
                continue
            if self.store.blob(sha) is not None:
                continue
            size = int(doc.get("byte_size") or 0)
            if budget_bytes is not None and used + size > budget_bytes:
                skipped.append({"doc_uid": uid, "reason": "over the storage budget",
                                "byte_size": size})
                continue
            try:
                used += self.pin(uid, sha256=sha,
                                 filename=doc.get("original_filename") or uid)
                cached.append(uid)
            except ClientError as exc:
                failed.append({"doc_uid": uid, "reason": str(exc)})
        return {"cached": cached, "skipped": skipped, "failed": failed,
                "bytes_held": self.store.cached_bytes()}

    def read_offline(self, doc_uid: str) -> dict[str, Any]:
        """A document as the device can show it with no network at all."""
        doc = next((d for d in self.store.rows("documents")
                    if d.get("doc_uid") == doc_uid), None)
        if doc is None:
            raise ClientError(f"{doc_uid} is not in this device's copy", 404)
        data = self.store.blob(doc["sha256"]) if doc.get("sha256") else None
        return {
            "doc_uid": doc_uid,
            "title": doc.get("title"),
            "document_date": doc.get("document_date"),
            # Provenance travels with the document. On a phone, in a hallway,
            # under time pressure, this is exactly when a date's source matters.
            "date_source": doc.get("date_source"),
            "extract_line": doc.get("extract_line"),
            "extract_locator": doc.get("extract_locator"),
            "verification_status": doc.get("verification_status"),
            "original_available_offline": data is not None,
            "byte_size": len(data) if data else None,
        }

    # -- captures -----------------------------------------------------------
    def capture(self, *, filename: str, data: bytes, captured_at: str,
                matter_id: int | None = None, kind: str = "PHOTO",
                note: str | None = None) -> dict[str, Any]:
        """Queue evidence captured on the device, then try to send it.

        It is queued first and sent second, always. A photo of a posted notice
        taken in a building with no signal has to survive the walk back to the
        car.
        """
        client_uid = self.store.queue_capture(
            filename=filename, data=data, captured_at=captured_at,
            matter_id=matter_id, kind=kind, note=note)
        flushed = self.flush()
        return {"client_uid": client_uid, "queued": True,
                "sent": client_uid in flushed["sent"], "flush": flushed}

    def flush(self) -> dict[str, Any]:
        """Send everything waiting in the outbox. Safe to call at any time."""
        sent, still_waiting = [], []
        for item in self.store.pending():
            try:
                self._upload(item)
                self.store.mark_sent(item["client_uid"])
                sent.append(item["client_uid"])
            except Unreachable as exc:
                self.store.mark_failed(item["client_uid"], str(exc))
                still_waiting.append(item["client_uid"])
            except ClientError as exc:
                self.store.mark_failed(item["client_uid"], str(exc))
                still_waiting.append(item["client_uid"])
        return {"sent": sent, "still_waiting": still_waiting,
                "pending": len(self.store.pending())}

    def _upload(self, item: sqlite3.Row) -> dict[str, Any]:
        fields = {"client_uid": item["client_uid"], "capture_kind": item["kind"],
                  "captured_at": item["captured_at"]}
        if item["matter_id"] is not None:
            fields["matter_id"] = str(item["matter_id"])
        if item["note"]:
            fields["device_note"] = item["note"]
        body, content_type = _multipart(fields, item["filename"], bytes(item["data"]))
        return self._request("POST", "/captures", body=body, content_type=content_type)


def _multipart(fields: dict[str, str], filename: str,
               data: bytes) -> tuple[bytes, str]:
    boundary = f"----casecommand{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n"
            f"{value}\r\n".encode())
    guessed = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
        f"filename=\"{Path(filename).name}\"\r\nContent-Type: {guessed}\r\n\r\n".encode())
    parts.append(data)
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


# ---------------------------------------------------------------------------
# conformance
# ---------------------------------------------------------------------------
#: What a client has to get right. A native port is finished when it passes
#: these, and not before. Each one is a failure that has actually happened to
#: somebody's sync client, not a hypothetical.
CONFORMANCE_RULES = (
    ("open-index", "The index is readable without a token."),
    ("auth-required", "Sync without a token is refused."),
    ("pair-once", "A pairing code works once and not twice."),
    ("full-sync", "A first sync pulls the whole record."),
    ("delta-sync", "A second sync pulls only what changed."),
    ("cursor-holds", "The cursor is not advanced past a truncated page."),
    ("blob-verified", "A cached original is verified against the record's digest."),
    ("offline-read", "A pinned document is readable with the network down."),
    ("offline-provenance", "An offline document still carries its date source."),
    ("capture-survives-offline", "A capture taken offline is kept and sent later."),
    ("capture-dedupes", "A replayed upload is one capture, not two."),
    ("revocation-surfaces", "A revoked device is told, not silently retried."),
)


def conformance(base_url: str, code: str, store_path: str | Path, *,
                revoke: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Drive a live server through every rule and report pass or fail for each.

    `revoke` is called with the device_uid to test the revocation rule; pass
    None to skip it. Everything else runs against the server as a real client
    would, over HTTP.
    """
    results: list[dict[str, Any]] = []

    def record(rule: str, ok: bool, detail: str) -> None:
        results.append({"rule": rule, "passed": bool(ok), "detail": detail})

    store = LocalStore(store_path)
    client = CaseCommandClient(base_url, store)

    try:
        idx = client.index()
        record("open-index", idx.get("api_version") == "v1",
               f"api_version={idx.get('api_version')}, {len(idx.get('endpoints', []))} endpoints")

        try:
            client._request("GET", "/sync", auth=False)
            record("auth-required", False, "sync answered without a token")
        except ClientError as exc:
            record("auth-required", exc.status == 401, f"HTTP {exc.status}")

        paired = client.pair(code, label="Conformance", platform="reference")
        try:
            second = LocalStore(Path(store_path).with_suffix(".second.db"))
            CaseCommandClient(base_url, second).pair(code, label="Replay")
            record("pair-once", False, "the same code paired a second device")
            second.close()
        except ClientError as exc:
            record("pair-once", exc.status in (400, 404, 409), f"refused: {exc}")

        first = client.sync(full=True)
        record("full-sync", first["total"] > 0,
               f"{first['total']} rows in {first['rounds']} round(s)")

        second_sync = client.sync()
        record("delta-sync", second_sync["total"] == 0,
               f"{second_sync['total']} rows changed since the first sync")

        # Force truncation with a deliberately tiny page, then check the client
        # both looped and ended up holding everything a single big page held.
        # Asking the server whether it *has* a more_available field proves
        # nothing; making it say yes, and surviving that, is the actual test.
        expected = store.counts()
        paged_store = LocalStore(Path(store_path).with_suffix(".paged.db"))
        paged_store.set("token", store.token)
        paged = CaseCommandClient(base_url, paged_store)
        walked = paged.sync(full=True, page_size=1)
        got = paged_store.counts()
        record("cursor-holds",
               walked["paged"] and walked["rounds"] > 1 and got == expected,
               f"{walked['rounds']} rounds at 1 row/table/page -> {sum(got.values())} rows, "
               f"same as the {sum(expected.values())} from one large page")
        paged_store.close()

        docs = [d for d in store.rows("documents") if d.get("sha256")]
        if docs:
            doc = docs[0]
            try:
                size = client.pin(doc["doc_uid"], sha256=doc["sha256"],
                                  filename=doc.get("original_filename") or doc["doc_uid"])
                verified = store.blob(doc["sha256"]) is not None
                record("blob-verified", verified, f"{size} bytes cached and re-verified")
            except ClientError as exc:
                record("blob-verified", False, str(exc))

            offline = client.read_offline(doc["doc_uid"])
            record("offline-read", offline["original_available_offline"],
                   f"{doc['doc_uid']} readable from the device's own copy")
            record("offline-provenance", bool(offline.get("date_source")),
                   f"date_source={offline.get('date_source')!r}")
        else:
            for rule in ("blob-verified", "offline-read", "offline-provenance"):
                record(rule, False, "no documents with a digest were synced")

        # Offline capture: point the client at a dead port so the send genuinely
        # fails, then repair it and flush.
        offline_client = CaseCommandClient("http://127.0.0.1:1", store, timeout=1.0)
        queued = offline_client.capture(
            filename="notice.txt", data=b"posted notice, photographed at the courthouse",
            captured_at="2026-08-04T09:00:00.000Z", note="conformance")
        held = not queued["sent"] and len(store.pending()) >= 1
        flushed = client.flush()
        record("capture-survives-offline",
               held and queued["client_uid"] in flushed["sent"],
               f"queued while unreachable, sent on reconnect ({len(flushed['sent'])} item(s))")

        replay = store.conn.execute(
            "UPDATE outbox SET state='PENDING' WHERE client_uid=?",
            (queued["client_uid"],))
        store.conn.commit()
        del replay
        again = client._upload(store.conn.execute(
            "SELECT * FROM outbox WHERE client_uid=?", (queued["client_uid"],)).fetchone())
        record("capture-dedupes", bool(again.get("duplicate")),
               f"server answered duplicate={again.get('duplicate')}")
        store.mark_sent(queued["client_uid"])

        if revoke is not None:
            revoke(paired["device_uid"])
            try:
                client.sync()
                record("revocation-surfaces", False, "sync still worked after revocation")
            except Revoked as exc:
                record("revocation-surfaces", True, f"HTTP {exc.status}: {exc}")
            except ClientError as exc:
                record("revocation-surfaces", False, f"wrong error type: {exc}")
        else:
            record("revocation-surfaces", False, "not tested (no revoke callback)")
    finally:
        store.close()

    covered = {r["rule"] for r in results}
    for rule, _ in CONFORMANCE_RULES:
        if rule not in covered:
            record(rule, False, "not run")

    passed = sum(1 for r in results if r["passed"])
    return {
        "results": results,
        "passed": passed,
        "total": len(results),
        "all_passed": passed == len(results),
        "rules": {k: v for k, v in CONFORMANCE_RULES},
    }


def format_conformance(report: dict[str, Any]) -> str:
    descriptions = report["rules"]
    lines = [f"Client conformance: {report['passed']}/{report['total']} rules", ""]
    width = max(len(r["rule"]) for r in report["results"])
    for result in report["results"]:
        mark = "PASS" if result["passed"] else "FAIL"
        lines.append(f"  [{mark}] {result['rule']:<{width}}  {result['detail']}")
        lines.append(f"         {' ' * width}  {descriptions.get(result['rule'], '')}")
    if not report["all_passed"]:
        lines += ["", "A client that does not pass all of these can lose a document",
                  "without saying so. Do not ship it."]
    return "\n".join(lines)


__all__ = [
    "CaseCommandClient", "LocalStore", "ClientError", "Unreachable", "Revoked",
    "CONFORMANCE_RULES", "conformance", "format_conformance", "MIRROR_TABLES",
]
