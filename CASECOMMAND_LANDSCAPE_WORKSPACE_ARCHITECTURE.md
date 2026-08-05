# Case Command — landscape workspace architecture

Written 2026-08-04, against the implementation on `claude/case-command-production-xfjxa0`.

## Step 1 of the requested sequence: inspect and report

The layout brief asked for ten specific things to be inspected before any redesign:
the Jarvis root layout component, the sidebar component, the conversation-list
component, content max-width rules, the CaseCommand route wrapper, CSS
grid/flex constraints, existing responsive breakpoints, duplicate CaseCommand
sidebar entries, the horizontal overflow source, and the exact files that must
change.

Six of those ten do not exist in this repository, and two of the defects they
were meant to explain are not present. That is not a refusal of the brief — it
is the inspection result, and acting on the brief without saying so would mean
"fixing" files that were never there.

### What was inspected

```
$ find . -name '*.tsx' -o -name '*.jsx' | grep -v node_modules
./ghostmesh/frontend/src/...        (34 files — GhostMesh, a different product)

$ grep -ril 'CaseCommandPage|conversation-list|conversationList' --include=*.tsx .
(no matches)
```

There is no React shell in this repo, no `CaseCommandPage.tsx`, no conversation
list, and no Jarvis root layout component. The only TSX belongs to GhostMesh
(entity search, tech-sniper, archive) — a different application that happens to
share the repository.

**Case Command's web UI is Python + Jinja2**, served by `case_command/web/server.py`
from `case_command/web/templates/`. It renders its own full-height shell:
`base.html` provides the left rail, the top bar, and the grid. There is no host
layout wrapping it and nothing constraining it.

The implementation the layout brief describes — a portrait content column inside
a Jarvis React shell, with a conversation sidebar and duplicated CaseCommand nav
entries — is real, but it is not this one. It is almost certainly the work
Codex was doing at `/opt/JarvisOS` on the Mac, which this container has never
had access to. Screenshots of that build cannot be used to diagnose this one.

### Measured, not assumed

Chromium at 1920×1080 against the running server:

| Route | viewport | `<main>` width | computed `max-width` | `body.scrollWidth` |
|---|---|---|---|---|
| `/` | 1920 | **1920** | `none` | 1920 |
| `/atlas` | 1920 | **1920** | `none` | 1920 |
| `/triage` | 1920 | **1920** | `none` | 1920 |
| `/timeline` | 1920 | **1920** | `none` | 1920 |

`body.scrollWidth == innerWidth` on every route, so there is no horizontal
overflow anywhere. `max-width` is `none`, so there is no centred reading column.

### Defects from the brief that are not present here

| Alleged defect | Status in this build | Evidence |
|---|---|---|
| Narrow centred content column | Not present | `<main>` = full 1920px |
| `max-width` container | Not present | computed `max-width: none` |
| Horizontal scrollbar under the tab row | Not present | `scrollWidth == innerWidth`; there is no tab row |
| Conversation list consuming width | Not present | No conversation list exists |
| Duplicate CaseCommand sidebar entries | Not present | One rail, one entry each |
| Jarvis branding inside the product surface | Not present | Rail reads **Case Command / LITIGATION RECORD**; removed earlier at your request |
| Features represented mainly as top tabs | Not present | 13 routes on a persistent left rail |

### Defects from the brief that *are* real here

These are the gaps worth the work, and they are what the rebuild targets.

| Gap | Current state | Target |
|---|---|---|
| **No contextual inspector** | Nothing pinned right | Persistent right inspector on Command and Matter, collapsible below 1440px |
| **Path Atlas is stacked text cards** | Four columns of prose | A real node graph: paths as nodes, dependencies as edges, blocked/open/preserving encoded visually |
| **Timeline is a filtered table** | Rows sorted by date | Horizontal chronology band with the boundary marked, table retained below as the detail view |
| **No Document Center** | `/triage` is a list | Full-width operational table + preview inspector, bulk selection, column config |
| **No Filing Studio** | Does not exist | Path matrix, staged packet, checklist, draft queue, status tracker |
| **Low-data dead space** | Empty panels leave large voids | Panels collapse to their content; the grid reflows rather than reserving height |
| **No command palette** | Rail only | ⌘K palette over routes, matters, and documents |

## The layout model

Case Command is its own shell. It does not need a route-aware host mode because
there is no host in this repo constraining it — so the requested
"route-aware Jarvis shell" step has nothing to modify here. What it *does* need
is a workspace grid that changes shape per route and per viewport.

```
┌──────────┬──────────────────────────────────────────────┬─────────────┐
│ rail     │ header — matter selector, search, status     │             │
│ (240px,  ├──────────────────────────────────────────────┤ inspector   │
│  icon    │ mission band                                 │ (360px,     │
│  mode    ├──────────────────────────────────────────────┤  pinned     │
│  <1440)  │ workspace grid — per route                   │  ≥1440px)   │
└──────────┴──────────────────────────────────────────────┴─────────────┘
```

Breakpoints:

- **≥1440px** — rail expanded, inspector pinned, workspace 3–4 columns.
- **1100–1439px** — rail expanded, inspector becomes a drawer, workspace 2 columns.
- **<1100px** — rail collapses to icons, panels stack, inspector is a sheet.
- **<720px** — the separate mobile routes (`/m/*`) already built.

Implemented as CSS grid with named areas in `base.html`, so a route declares
which areas it fills rather than each template inventing its own layout.

## What this does not adopt from the reference designs

The reference images contain three things that are not defensible in a record
system, and they stay out for the same reason they stayed out before:

- **"68% Overall — Moderate" case health.** Nothing can source 68%. The panel
  in its place reports counts with numerator and denominator: *0 of 23 issues
  have a linked source.*
- **"Likely Response: Grant / Partial Grant", "High success probability", "81%
  Confidence".** These predict a tribunal's ruling. Path Atlas reports whether
  prerequisites are met, which is a fact about the record.
- **"Take Action" as a button that files and serves.** Nothing in this UI
  transmits. The affordance does not exist.

The references also show invented matters (`Highgate Energy v. Meridian Control`)
and a 1,248-document corpus. Every panel here renders what is actually in the
database, including when that is nothing.

The visual language — dark operations console, mission band, KPI strip, dense
multi-panel workspace, node-graph atlas, pinned inspector — is adopted in full.
