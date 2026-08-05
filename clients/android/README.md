# Case Command — Android client

A standalone app. It holds its own copy of the record and reconciles with the
desktop; it is not a browser pointed at the web UI. That difference is what the
`core` module is.

## What is verified, and what is not

This matters more than usual here, so it is stated first and precisely.

| Module | What is proven | How |
|---|---|---|
| `core/` — protocol, sync, store, conformance | **Behaviour.** 24 self checks and all twelve conformance rules against a live server | `tools/build-core.sh`, using only the Kotlin compiler inside Gradle. No Maven, no Android SDK, no network |
| `app/` — Compose UI, SQLite store, manifest | **That it builds.** Compiles, links, packages, signs | The `apk` CI job, on a runner that has the SDK |

That split is deliberate. Everything that could silently lose a document lives
in `core` and is exercised against a real server. `app` is proven to build and
nothing more.

**The APK has never been run on a device.** CI produces a real, installable,
signed artifact every push — but a build that compiles is not a screen that
renders. Nothing here has been seen working on a phone.

The manifest is where that gap bites hardest, because it compiles whatever you
put in it. `android:usesCleartextTraffic="true"` sat on `<activity>`, where the
attribute is not declared and is dropped without a word — and since targetSdk 28
the default is to refuse cleartext, so every request to the LAN server would
have failed with *CLEARTEXT communication not permitted*. Six green builds, an
APK that installs, and an app that cannot talk to anything. It is now on
`<application>`, and `TestAndroidManifest` in the Python suite parses the file
and fails if it moves back — checked there because it is the suite that
actually runs.

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

## Pairing by tapping

Open the desktop's **Pair a device** page *on the phone*, press the button, tap
the link. The app opens with the address and the code already in it.

The address in that link is the one the phone used to load the page, taken from
the request rather than guessed. A machine has several addresses and only some
of them work from where the phone is standing; the one it just used
demonstrably does. Nothing is read across a room and retyped.

```
casecommand://pair?host=http%3A//192.168.1.50%3A8899&code=8EURJ3
```

A custom scheme rather than an `https` link on purpose: an https link needs a
domain to verify against, and this system has no domain and no server on the
internet.

The code is minted when you press the button and not before, so a page left
open in a tab is not a way in. It is single use and expires in ten minutes.

### There is no code field in the app

Not hidden, not optional — removed. The pairing screen has no text input at
all, and an address field without a code field pairs nothing, so that is gone
too. Opening the link *is* pressing the button: the app pairs on arrival and
shows a progress bar, not a form.

What this gives up is pairing from a code somebody reads to you. What it costs
is nothing else: pairing now needs the phone to open the desktop's `/pair` page
in its own browser, and the phone has to reach that same server immediately
afterwards to sync at all — so it rules out no case that would otherwise have
worked.

If a link fails, the app says so and tells you to make a new code rather than
offering a retry. A code is single use, so retrying the same one fails
identically and looks like a broken app.

`case_command/client.py` and `case-command conform` still take a code as an
argument; they are not the phone, and a test harness needs to pair without a
browser. The code stays on the web page too, folded away under *The code this
link carries*, so you can see what was issued and match it against the paired
devices list.

## Pairing once, not every time

You pair a device once. After that it holds a token and never asks again — that
is how it was designed, and for a while it was not how it behaved.

The cause was signing. Gradle signs a debug build with a keystore it generates
on the spot if none exists, and a CI runner never has one, so **every build got
a brand-new key.** The certificate in the first published APK gives it away:

```
Owner:      C=US, O=Android, CN=Android Debug
Valid from: Tue Aug 04 12:41:12 UTC 2026
```

The build finished at 12:41:20. That key was made eight seconds earlier.

Android refuses to install an APK over one signed with a different key, so every
update meant uninstalling first — which wipes the app's data, including the
paired token. Hence a pairing code every time. Nothing reported it: each APK was
valid, signed, and installable. It just was never *the same app* as the one
before it.

### Fixing it, once

The key is passed by environment, never committed — this repository is public,
and a signing key in it would let anyone build an APK that Android would accept
as an update to this one.

**On your Mac.** The private key is generated here and stays here.

```sh
keytool -genkeypair -v \
  -keystore casecommand.jks \
  -alias casecommand \
  -keyalg RSA -keysize 4096 -validity 10000 \
  -dname "CN=Case Command, O=Kerr, C=US"
```

It asks for a password twice. Keep the file and the password somewhere you will
still have them in five years — **if you lose them, you cannot update the app
again without an uninstall**, which is the whole problem coming back.

Then produce the value to paste into GitHub:

```sh
base64 -i casecommand.jks | tr -d '\n' | pbcopy   # now on your clipboard
```

**In the repository**, under *Settings → Secrets and variables → Actions → New
repository secret*, add three:

| Name | Value |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | the clipboard contents |
| `ANDROID_KEYSTORE_PASSWORD` | the password you chose |
| `ANDROID_KEY_ALIAS` | `casecommand` |

The next build signs with that key and prints its fingerprint. Copy that
fingerprint into `clients/android/signing-key.sha256` and commit it — from then
on CI **fails** if the signing key ever changes again, rather than quietly
shipping an APK that cannot be installed over the last one.

Until the secrets are set, builds still work; CI just warns that the key is a
throwaway.

### One last uninstall

The APK already published is signed with one of the throwaway keys. Moving to
the stable key means uninstalling once more and pairing once more. After that,
updates install over the top and the pairing survives.

### Checking a build yourself

```sh
python3 clients/android/tools/apk-signer.py case-command-debug.apk
```

Two APKs with the same fingerprint will install over each other. Two with
different fingerprints will not.

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
