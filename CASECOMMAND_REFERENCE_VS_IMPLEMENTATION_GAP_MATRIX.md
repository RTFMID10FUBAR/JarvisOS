# Reference vs implementation — gap matrix

Compares the approved reference designs against the build on
`claude/case-command-production-xfjxa0`, measured at 1920×1080 in Chromium on
2026-08-04.

Status key: **MET** — present and equivalent · **GAP** — real, being built ·
**DECLINED** — deliberately not built, reason given · **N/A** — the premise does
not apply to this codebase.

## Shell and layout

| # | Reference expectation | Status | Evidence / note |
|---|---|---|---|
| 1 | Full viewport width at 1920×1080 | **MET** | `<main>` measures 1920px; `max-width: none` |
| 2 | No large unused right-side void | **MET** at data volume; **GAP** when empty | Panels reserve height when a matter has no rows — being changed to reflow |
| 3 | No horizontal scrolling for primary nav | **MET** | `body.scrollWidth == innerWidth` on all four routes; nav is a rail, not tabs |
| 4 | Compact global host rail collapsing | **N/A** | No host shell exists in this repo — see architecture doc |
| 5 | Persistent left workspace navigation | **MET** | 13 routes grouped Record / Act / Review, with live badge counts |
| 6 | Persistent command/status header | **MET** | Title, Live indicator, workspace identity, data-as-of |
| 7 | Contextual right inspector | **GAP** | Nothing pinned right on any route |
| 8 | Panel collapse / adjustable widths | **GAP** | Panels are fixed |
| 9 | Global command palette | **GAP** | Rail navigation only |
| 10 | Route-backed workspaces, not tab rows | **MET** | Each screen is its own URL and template |
| 11 | Product branding not host branding | **MET** | Rail reads *Case Command / LITIGATION RECORD* |
| 12 | Duplicate nav entries removed | **N/A** | Never duplicated here |

## Command workspace — `02_litigation_command_futuristic_dashboard.png`

| # | Reference element | Status | Note |
|---|---|---|---|
| 13 | Mission now | **MET** | States plainly when nothing is scheduled, and that an empty calendar may mean an incomplete record |
| 14 | Safest next action | **MET** | Named "Next action", with priority and a link |
| 15 | Urgent deadline / at-risk tiles | **MET** | Six-tile KPI strip incl. dates already passed, waiver risk |
| 16 | Proof blockers | **MET** | Filings blocked / need proof |
| 17 | Record conflicts | **MET** | Contradictions panel |
| 18 | Active matters table with next action | **MET** | Six matters, next action, boundary, counts |
| 19 | Upcoming events panel | **GAP** | Folded into the deadline tiles; needs its own panel |
| 20 | Strategy / Path Atlas embedded in command view | **GAP** | Atlas is a separate route only |
| 21 | Recent activity feed | **GAP** | Not present |
| 22 | Document Center summary counts | **GAP** | Not present |
| 23 | Fleet notes lane | **PARTIAL** | `/fleet` exists as a route; not surfaced on Command |
| 24 | Case health donut, "68% Overall" | **DECLINED** | Nothing can source 68%. Replaced by record coverage with numerator/denominator |
| 25 | Per-matter "Confidence 81% / 74%" column | **DECLINED** | Same reason — a confidence number no record can support |
| 26 | "Take Action" primary button | **DECLINED** | Would file or serve. Nothing in this UI transmits |
| 27 | Bottom global counters strip | **MET** | Open matters, documents, issues, open unknowns, access barriers |

## Path Atlas — `03_litigation_command_core_workspace.png`

| # | Reference element | Status | Note |
|---|---|---|---|
| 28 | Visual decision map with nodes and edges | **GAP** | Currently four columns of text cards — the single largest visual gap |
| 29 | Open path / closed path / preserves-issue encoding | **PARTIAL** | The classification exists in data; not drawn |
| 30 | Cross-reference edges between matters | **GAP** | `matter_links` exist in the schema; not visualised |
| 31 | Must-remain-separate edges | **GAP** | Enforced in data (six matters never merged); not drawn |
| 32 | Per-node risk dots | **DECLINED** as risk *scoring*; **GAP** as prerequisite state | Nodes will show met / not-met prerequisites, not a risk score |
| 33 | "Likely Response: Grant / Partial Grant" | **DECLINED** | Outcome prediction |
| 34 | Plain-English explainers | **MET** | Preservation, exceptions, waiver, why "blocked" not "unlikely" |

## Timeline — reference chronology band

| # | Reference element | Status | Note |
|---|---|---|---|
| 35 | Horizontal chronology | **GAP** | Currently a filtered table sorted by date |
| 36 | Filter bar | **MET** | Matter, date range, actor, filing type, boundary, verification, disputed, significance |
| 37 | Date-type distinction visible | **MET** in data, **GAP** in visual | Every row carries its `date_source`; not visually encoded |
| 38 | Boundary marked on the axis | **GAP** | The 2025-09-03 boundary is in the data and named in rows, but not drawn as a line |
| 39 | Event inspector | **MET** | "What counts as proof" panel, pinned |
| 40 | Contradiction panel adjacent | **GAP** | Contradictions live on Command only |
| 41 | Source confidence per event | **MET** | `verification` column plus the source locator (`CC-DOC-000001 char 404`) |
| 41a | **Every item states what proves it** | **MET** | New `event_proof` table: one row per piece of proof, typed, each with its own locator. A documented event and a remembered one are visually distinct — solid green border vs dashed amber |
| 41b | **Add an event by hand, including a recollection** | **MET** | `/timeline/add` and `/timeline/proof`; `case-command event add\|proof\|unproved` |
| 41c | **A recollection never counts as proof of the fact** | **MET** | Caps the event at `UNKNOWN`; documentary proof caps at `PARTIALLY_VERIFIED`; `VERIFIED_PRIMARY` stays a person's decision |
| 41d | **The gap between event and recording is shown** | **MET** | "recorded 306 days after" — arithmetic on two dates, reported, never scored |
| 41e | Filing and order dates entered by hand | **N/A — not needed** | Read off the document's own signature block / dated line / service date, each carrying its cue |

## Document Center — `05_document_center_and_intake.png`

| # | Reference element | Status | Note |
|---|---|---|---|
| 42 | Full-width operational table | **GAP** | `/triage` is a list |
| 43 | Preview inspector | **GAP** | Document detail is a separate page |
| 44 | Duplicate detection surfaced | **PARTIAL** | Detected at ingest and recorded in `document_copies`; not shown as a queue |
| 45 | Extracted metadata columns | **PARTIAL** | Date, source, method shown; not configurable |
| 46 | Bulk selection and staging actions | **GAP** | Per-row only |
| 47 | OCR state | **MET** in data | `ocr_used`, `text_method`, `text_confidence` |
| 48 | Exhibit assignment | **GAP** | Not built |
| 49 | Print / export builder | **GAP** | Not built |

## Filing Studio — `04_filing_and_exhibit_builder.png`

| # | Reference element | Status | Note |
|---|---|---|---|
| 50 | Procedural path matrix | **GAP** | Data exists in Path Atlas; no filing view |
| 51 | Staged filing packet | **GAP** | Not built |
| 52 | Smart checklist | **PARTIAL** | `case-command check` runs five anti-omission checks in the CLI; no UI |
| 53 | Draft queue | **GAP** | Not built |
| 54 | Real-time status tracker | **PARTIAL** | Ten filing statuses in the schema; no tracker UI |
| 55 | Legal explainers | **MET** on Atlas | Reusable on Filing |
| 56 | "Likely Response" column | **DECLINED** | Outcome prediction |
| 57 | Filing controls that file and serve | **DECLINED** | Nothing transmits without approval; this UI has no send path at all |

## Mobile — `06_mobile_companion_concept.png`

| # | Reference element | Status | Note |
|---|---|---|---|
| 58 | Mobile home, at-a-glance | **MET** | `/m/` routes |
| 59 | Matter detail | **MET** | `/m/doc/<uid>` and matter routes |
| 60 | Quick evidence capture, offline | **MET, verified** | Capture queued with the network genuinely down, flushed on reconnect |
| 61 | Document scan / OCR | **PARTIAL** | Upload + server-side extraction; no on-device scan UI |
| 62 | Deadline alert with countdown | **PARTIAL** | Deadlines listed; no push notification |
| 63 | Voice note → task | **GAP** | Not built |
| 64 | Offline mode indicator | **MET** | Shown, and honest about last-sync time |
| 65 | "81% Conf." per matter | **DECLINED** | Same reason as #25 |
| 66 | Biometric unlock | **GAP** | Android app scope |

## Summary

- **MET: 24** · **PARTIAL: 9** · **GAP: 24** · **DECLINED: 7** · **N/A: 2**
- Every DECLINED item is a number or an action that no record can support. Each
  has a built replacement that reports a fact instead.
- The two N/A items are the layout defects attributed to a React shell that does
  not exist in this repository.
- The four largest real gaps, in build order: **Path Atlas as a visual map**,
  **contextual inspector**, **Document Center**, **Filing Studio**.
