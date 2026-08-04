# Case Command — Android client

A standalone app. It holds its own copy of the record and reconciles with the
desktop; it is not a browser pointed at the web UI. That difference is what the
`core` module is.

## What is verified, and what is not

This matters more than usual here, so it is stated first and precisely.

| Module | Built and tested in CI? | How |
|---|---|---|
| `core/` — protocol, sync, store contract, conformance | **Yes** | `tools/build-core.sh`, using only the Kotlin compiler that ships inside Gradle. No Maven, no Android SDK, no network. |
| `app/` — Compose UI, SQLite store, manifest | **No** | Needs the Android SDK and the Compose compiler plugin. Neither is available in the environment used to verify the core. |

That split is deliberate. Everything that could silently lose a document lives
in `core` and is exercised against a live server. What is unverified in `app` is
layout and SQL, not protocol.

**Nobody has produced an APK from this yet.** The `app` module has never been
compiled. Expect to fix build errors the first time you open it; do not treat it
as working software until it builds and passes `:core:selfTest` on your machine.

## Verifying the core

```sh
# Self test only — no server needed.
clients/android/tools/build-core.sh
```

```
24 checks, 0 failure(s)
```

```sh
# Plus the twelve conformance rules against a running desktop.
R=/path/to/Kerr_Court_Cases
python3 -m case_command --data-root "$R" serve --port 8787 &
CODE=$(python3 -m case_command --data-root "$R" device pair | grep -oE '[A-HJ-NP-Z2-9]{6}')

clients/android/tools/build-core.sh http://127.0.0.1:8787 "$CODE" \
  "python3 -m case_command --data-root $R device revoke --device-uid {uid} --reason conformance"
```

```
Client conformance: 12/12 rules

  [PASS] open-index                api_version=v1, 10 endpoints
  [PASS] auth-required             HTTP 401
  [PASS] pair-once                 refused: this pairing code was already used
  [PASS] full-sync                 83 rows in 1 round(s)
  [PASS] delta-sync                0 rows changed since the first sync
  [PASS] cursor-holds              26 rounds at 1 row/table/page -> 83 rows, same as the 83 from one large page
  [PASS] blob-verified             903 bytes cached and re-verified
  [PASS] offline-read              CC-DOC-000001 readable from the device's own copy
  [PASS] offline-provenance        date_source=service date
  [PASS] capture-survives-offline  queued while unreachable, sent on reconnect (1 item(s))
  [PASS] capture-dedupes           server answered duplicate=true
  [PASS] revocation-surfaces       HTTP 403: this device has been revoked
```

These are the same twelve rules `case_command/client.py` passes. Two independent
implementations, one harness. If they ever disagree, one of them is wrong and
the disagreement is the finding.

Revocation is driven by running the desktop command, because a device must not
be able to revoke itself — there is no API endpoint for it. Without the third
argument the rule reports **not run** rather than quietly passing.

## Building the APK

On a machine with the Android SDK:

```sh
cd clients/android
./gradlew :core:selfTest          # protocol first
./gradlew :app:assembleDebug      # app/build/outputs/apk/debug/
```

Requires JDK 17+, Android SDK 34, and network access to `google()` and
`mavenCentral()` for the Compose dependencies. The `core` module needs none of
that — only `app` does.

## Architecture

```
core/  (pure Kotlin/JVM, zero dependencies)
  Json.kt         a small JSON reader/writer — a library would have meant Maven
  Store.kt        RecordStore interface + MemoryStore + sha256
  Transport.kt    Transport interface + HttpTransport (HttpURLConnection)
  CaseClient.kt   pairing, paged sync, pinning, offline reads, the outbox
  Conformance.kt  the twelve rules
  Main.kt         self test + conformance runner

app/   (needs the Android SDK)
  SqliteStore.kt   RecordStore over android.database.sqlite
  MainActivity.kt  Compose screens
```

`RecordStore` is an interface for one concrete reason: Android's SQLite lives
behind `android.database`, which cannot load on a plain JVM. If the sync engine
talked to SQLite directly, none of it could be tested without an emulator — and
with no SDK available, that means not tested at all. Behind the interface the
whole protocol runs and is verified, and Android supplies storage and nothing
else.

## Rules the client obeys

Ported from `case_command/client.py`, and each one is a failure that has
actually happened to somebody's sync client.

- **A capped page never advances the cursor past unseen rows.** A client that
  saves the cursor after a truncated page believes it is current while rows it
  has never seen sit on the other side, and it will never ask again. Writing
  this rule honestly is what caught the server bug that was dropping 75 of 80
  rows while reporting success.
- **A cached original is verified against the record's digest on the way out.**
  A cache that can hand back the wrong bytes is worse than no cache — "it was in
  my phone's cache" is not a provenance, and a wrong exhibit at a hearing is
  worse than a missing one because a missing one is obvious.
- **Unreachable is not an error.** It means fall back to the device's own copy
  and keep working. Any other failure means something is actually wrong and the
  person is told.
- **A revoked device is told.** Never silently retried — a phone quietly failing
  looks exactly like a phone still syncing.
- **A capture is queued before it is sent, always.** A photo taken in a building
  with no signal has to survive the walk back to the car. The `client_uid` is
  generated once on the device and reused on every retry, so a dropped upload is
  one capture and not two.
- **An unknown column does not break the sync.** A phone that cannot sync is
  worse than a phone that does not know about a new field.

## What the app cannot do

The same limits as everywhere else in this system, and they are enforced on the
server too — this is a client, and a client's promises are not security.

- It cannot file, serve, or transmit anything to a tribunal. There is no send
  action, no email, no court API call.
- It cannot mark a fact verified.
- It cannot edit or delete a record.
- It shows no score, health percentage, or predicted outcome. Counts with
  denominators only.

It uploads one thing: evidence captured on the device.

## Privacy

`INTERNET` is the only permission. It talks to one machine on the local network
— the one holding the record. No cloud, no account, no analytics, no third party
ever holds the case. The bearer token is shown to the device once and stored on
the desktop only as a SHA-256 hash, so a copied desktop database yields no
working credential.
