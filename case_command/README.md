# Case Command

The authoritative litigation record. Case Command ingests, classifies, indexes,
and cross-references every document placed in a small set of approved folders,
and it is the only place a case fact, issue, deadline, or preservation item
officially exists.

Fleet agents may analyze and propose. Only an approved proposal enters the
record.

---

## Design invariants

These are enforced in code and in the database schema, not just documented.

| Invariant | Where it is enforced |
|---|---|
| A document has one physical location, one canonical ID, one matter, and any number of *links* | `documents.sha256` UNIQUE + `document_matter_links` |
| Nothing in the canonical record is deleted | `BEFORE DELETE` triggers on `issues`, `facts`, `evidence`, `documents`, `matters`, `preservation_items`, `contradictions`, `unknowns` |
| Nothing is verified without a source and a locator | `checks.source_check`, `fleet.validate_proposal`, `fleet._apply_fact` |
| Folder presence is never proof of filing | `CHECK` constraint on `filings`; `fleet.validate_proposal` |
| The audit log is append-only and tamper-evident | `BEFORE UPDATE/DELETE` triggers + SHA-256 hash chain in `audit.py` |
| Originals are never moved without approval | `migrate_tree.execute(approved=False)` refuses by default |
| Fleet cannot delete an issue, merge matters, or decide an argument is abandoned | `fleet.validate_proposal` rejects the whole proposal |
| A computed deadline is never presented as verified | `preservation.py` stores every computed date as `INFERENCE` with the authority to confirm |

---

## Install and run

Requires Python 3.9+. The core has **no third-party dependencies**. The web UI
needs Jinja2.

```bash
pip install jinja2

# optional, and each one is reported by the health check when absent:
pip install pypdf python-docx openpyxl pillow pytesseract extract-msg striprtf
```

### Startup command

```bash
export CASE_COMMAND_DATA_ROOT=/Volumes/JarvisSSD/Kerr_Court_Cases
cd /opt/JarvisOS
python3 -m case_command init          # create folders + database (safe to re-run)
python3 -m case_command serve         # http://127.0.0.1:8787/
```

### Health-check command

```bash
python3 -m case_command health        # exit 0 = OK/WARN, exit 1 = FAIL
curl -s http://127.0.0.1:8787/api/health
```

### Watch a folder continuously

```bash
python3 -m case_command watch --interval 5
```

The queue lives in SQLite. Kill the watcher mid-job and restart it: interrupted
work returns to `PENDING` and resumes.

---

## Paths

Defaults, each overridable by environment variable.

| What | Path |
|---|---|
| Application root | `/opt/JarvisOS` (`CASE_COMMAND_APP_ROOT`) |
| Source | `/opt/JarvisOS/case_command/` |
| Litigation data | `/Volumes/JarvisSSD/Kerr_Court_Cases/` (`CASE_COMMAND_DATA_ROOT`) |
| Database | `<data>/.case_command/case_command.sqlite3` |
| Extracted text | `<data>/.case_command/text/` |
| Previews | `<data>/.case_command/previews/` |
| Manifests | `<data>/.case_command/manifests/` |
| Fleet work products | `<data>/.case_command/fleet/` |
| Backups | `<data>/.case_command/backups/` |

## Folders

```
Kerr_Court_Cases/
├── 00_INBOX/            new, unsorted, scanned, emailed, downloaded
├── 01_PSC_AEP/          PSC, APCo, AEP, tariff, meter, shutoff, appeal, mandamus, Rule 60
├── 02_MORTGAGE/         Rocket, PHH, Onity, VA mortgage, RESPA, foreclosure
├── 03_BRIDGEPORT/       Bridgeport, Belmont County, ADA, trial
├── 04_VETERANS/         VA disability, benefits, housing, SMC, appeals
├── 05_OTHER_CASES/      any legal matter not covered above
├── 06_SHARED_EVIDENCE/  evidence used across matters — stored once, linked many
├── 07_FINAL_FILINGS/    only what was actually filed/served/entered. No drafts.
└── 99_ARCHIVE/          superseded, duplicate, obsolete, rejected
```

Case Command asks at most two questions per document: **which matter**, and
**is this filed or working material**. Everything else is automated.

---

## Migrating an existing, disorganized tree

Built for a folder that has accumulated several competing organizational schemes
with content-identical copies scattered across them. Identity is determined by
SHA-256 of file bytes — never by filename or location — so copies another tool
left behind collapse into one canonical document plus flagged duplicates.

```bash
python3 -m case_command migrate plan       # inventory + hash + dedupe + propose. Read-only.
python3 -m case_command migrate dry-run    # verify every move would succeed. Moves nothing.
python3 -m case_command migrate execute            # refuses: approval required
python3 -m case_command migrate execute --approve  # writes a rollback manifest first
python3 -m case_command migrate rollback --manifest <path>
```

`plan` writes a baseline inventory manifest before anything else, so the
pre-migration state is always recoverable.

---

## Backups

```bash
python3 -m case_command backup create
python3 -m case_command backup list
python3 -m case_command backup verify --file <path>
python3 -m case_command backup restore --file <path>            # refuses
python3 -m case_command backup restore --file <path> --approve  # keeps a safety copy first
```

Every backup is verified at creation: the copy is reopened, `integrity_check` and
`foreign_key_check` run, row counts are compared against the live database, and
the audit hash chain is re-verified. Backup pruning reports what it *would*
remove and deletes nothing.

---

## Fleet

Fleet receives a small packet, not the case file.

```bash
python3 -m case_command fleet packet \
    --job-type rule_element_analysis --matter-id 2 --issue-id 2 \
    --task "Check the pretermination notice elements against the record."

python3 -m case_command fleet submit --file response.json
python3 -m case_command fleet pending
python3 -m case_command fleet decide --item-id 7 --decision APPROVED
```

Allowed jobs: `document_extraction`, `complaint_to_answer_comparison`,
`timeline_extraction`, `rule_element_analysis`, `tariff_matching`,
`contradiction_detection`, `defense_red_team`, `judge_view_review`,
`evidence_gap_analysis`, `deadline_extraction`, `proposed_findings`,
`appeal_preservation_review`, `citation_verification`.

Every response must return all twelve contract fields. A proposal that attempts a
prohibited action is rejected **in full**, with the reason named, and the
rejection is recorded in the audit log.

---

## Pre-final checks

```bash
python3 -m case_command check <matter_id> --draft path/to/draft.txt
```

Runs five checks and exits non-zero while any blocker remains:

* **completeness** — every active issue is included, excluded, reserved, out of
  scope, decided, or flagged as missing proof. An issue may not simply be absent.
* **conflict** — open contradictions, disputed facts relied on as established,
  relief requested with no disposition.
* **defense** — each issue red-teamed as APCo counsel, PSC Staff, the ALJ, a
  neutral reviewing judge, and an appellate judge.
* **preservation** — raised, ruling requested, ruling obtained or ignored,
  exception needed, appeal deadline.
* **source** — every verified assertion cites a document, page/paragraph, and date.

---

## Tests

```bash
python3 -m unittest case_command.tests.test_acceptance -v
```

64 tests covering section 14 of the specification: ingestion, classification,
litigation integrity, Fleet prohibitions, hearing support, preservation,
reliability, migration safety, token efficiency, anti-omission, and view rendering.

Build a populated demo instance:

```bash
python3 -m case_command.tests.demo /tmp/demo_root
CASE_COMMAND_DATA_ROOT=/tmp/demo_root python3 -m case_command serve
```

---

## PSC/AEP setup

Six **separate** matters, linked but never merged:

| Slug | Matter |
|---|---|
| `psc-24-0735` | PSC Case 24-0735-E-C (Case 1) |
| `psc-26-0315` | PSC Case 26-0315-E-C (Case 2) |
| `wvsca-appeal-24-0735` | WVSCA appeal from Case 24-0735 |
| `wvsca-mandamus` | WVSCA mandamus matter |
| `kanawha-rule-60` | Kanawha Rule 60 matter |
| `federal-civil-rights` | Related federal civil-rights action |

**Boundary date: September 3, 2025** — the PSC Final Order in Case 1. Every
PSC/AEP event and issue is classified as `CASE_1_DECIDED_ISSUE`,
`POST_FINAL_ORDER_NEW_CONDUCT`, `PRIOR_EVIDENCE_FOR_LIMITED_PURPOSE`,
`PROCEDURAL_HISTORY`, or `UNKNOWN`. Conduct after the boundary is never
automatically treated as relitigation.

23 live issues (`PSC-001` … `PSC-023`) are preloaded and marked `protected`.
They cannot be deleted. They can only move between `ACTIVE`, `RESERVED`, `WEAK`,
`MISSING_PROOF`, `OUTSIDE_CURRENT_HEARING`, `SUPERSEDED_BY_AUTHORITY`, and
`DECIDED`.

They are seeded with `verification_status = MISSING_SOURCE` because they come
from a specification, not from a filed document. Each will keep showing as
unsourced in the issue matrix until a document is linked to it. **That visible
gap is intentional** — inventing a source would be worse than showing the hole.

---

## What this system will not do

* Mark a fact verified without a source document and a locator.
* Treat a draft as operative, or a folder as proof of filing.
* Delete an issue, a fact, a document, or an audit entry.
* Move, rename, or overwrite an original without explicit approval.
* Send, file, serve, or transmit anything.
* Present a computed deadline as a confirmed legal deadline.
* Silently drop a document it could not read — an unreadable file becomes a
  visible `unknowns` record, not a gap.
