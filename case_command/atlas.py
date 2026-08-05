"""Path Atlas — what can actually be done in a matter right now.

The question this answers is the one a pro se litigant most needs answered and
least often can: *given where this case stands, what are my options, and which
of them am I actually able to take today?*

Each option is sorted into one of four columns:

    CAN BE PREPARED NOW    every prerequisite this system can check is met
    BLOCKED               a prerequisite is missing, and the missing thing is named
    PRESERVES AN ISSUE    its purpose is to keep an issue alive for appeal
    SUGGESTED ORDER       the sequence, ordered by deadline pressure

**What this module will not do.** It does not predict how a tribunal will rule,
score a filing's likelihood of success, or rank options by expected outcome. The
mockups this view is modelled on showed "Likely Response: Grant / Partial Grant"
and "High success probability". Those are forecasts dressed as data. A blocked
option here is blocked because a *named record fact* is missing — an unfiled
exception, an unlinked source, an unruled motion — and the fix is stated. That is
checkable. A probability is not.

Prerequisites are evaluated against the record only. A path shown as available
is one this system found no recorded obstacle to; it is not legal advice that
the path is available in law.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any, Callable

from .views import days_until


@dataclass
class Path:
    """One procedural option, with why it is or is not currently available."""

    key: str
    label: str
    what_it_does: str
    #: Named prerequisites that are not satisfied. Empty means nothing blocks it.
    blockers: list[str] = field(default_factory=list)
    preserves: str | None = None
    urgency_date: str | None = None
    urgency_reason: str | None = None
    authority_to_confirm: str | None = None

    @property
    def available(self) -> bool:
        return not self.blockers

    @property
    def days_left(self) -> int | None:
        return days_until(self.urgency_date)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "label": self.label, "what_it_does": self.what_it_does,
            "blockers": self.blockers, "preserves": self.preserves,
            "urgency_date": self.urgency_date, "urgency_reason": self.urgency_reason,
            "authority_to_confirm": self.authority_to_confirm,
            "available": self.available, "days_left": self.days_left,
        }


def _count(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    return int(conn.execute(sql, params).fetchone()[0])


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(sql, params)]


# ---------------------------------------------------------------------------
# path builders
#
# Each returns a Path, or None when it does not apply to this matter at all.
# A builder never invents a deadline: it reads one already in the record, and
# carries forward the authority that deadline says must be confirmed.
# ---------------------------------------------------------------------------
def _exceptions_path(conn: sqlite3.Connection, matter_id: int) -> Path | None:
    order = conn.execute(
        "SELECT * FROM orders WHERE matter_id=? AND is_recommended_decision=1 "
        "AND status='ACTIVE' ORDER BY entered_date DESC LIMIT 1", (matter_id,)).fetchone()
    if order is None:
        return None

    deadline = conn.execute(
        "SELECT * FROM deadlines WHERE matter_id=? AND deadline_type='exception' "
        "AND satisfied=0 AND status='ACTIVE' ORDER BY due_date LIMIT 1", (matter_id,)).fetchone()

    pending = _count(conn,
        "SELECT COUNT(*) FROM preservation_items WHERE matter_id=? AND status='ACTIVE' "
        "AND exception_required=1 AND exception_filed=0", (matter_id,))

    return Path(
        key="exceptions",
        label="File exceptions to the Recommended Decision",
        what_it_does=(
            f"Preserves objections for review. {pending} issue(s) are currently marked "
            "as needing an exception that has not been filed."
            if pending else
            "Preserves objections to the Recommended Decision for review."),
        preserves=f"{pending} issue(s) awaiting an exception" if pending else None,
        urgency_date=deadline["due_date"] if deadline else None,
        urgency_reason=f"Recommended Decision entered {order['entered_date']}"
                       if order["entered_date"] else None,
        authority_to_confirm=(deadline["notes"] if deadline else
                              "Confirm the exception period against the governing rule."),
    )


def _appeal_path(conn: sqlite3.Connection, matter_id: int) -> Path | None:
    order = conn.execute(
        "SELECT * FROM orders WHERE matter_id=? AND is_final=1 AND status='ACTIVE' "
        "ORDER BY entered_date DESC LIMIT 1", (matter_id,)).fetchone()
    if order is None:
        return None

    deadline = conn.execute(
        "SELECT * FROM deadlines WHERE matter_id=? AND deadline_type='appeal' "
        "AND satisfied=0 AND status='ACTIVE' ORDER BY due_date LIMIT 1", (matter_id,)).fetchone()

    blockers: list[str] = []
    unraised = _count(conn,
        "SELECT COUNT(*) FROM preservation_items WHERE matter_id=? AND status='ACTIVE' "
        "AND raised=0", (matter_id,))
    if unraised:
        blockers.append(
            f"{unraised} issue(s) are not recorded as having been raised below. An issue "
            "not raised is generally not preserved — record where each was raised, or "
            "record why it did not need to be.")

    return Path(
        key="appeal",
        label="Perfect an appeal from the final order",
        what_it_does="Takes the final order to the reviewing court.",
        blockers=blockers,
        preserves="Every issue properly raised and ruled on below",
        urgency_date=deadline["due_date"] if deadline else None,
        urgency_reason=f"Final order entered {order['entered_date']}"
                       if order["entered_date"] else None,
        authority_to_confirm=(deadline["notes"] if deadline else
                              "Confirm the appeal period and its trigger date."),
    )


def _ruling_path(conn: sqlite3.Connection, matter_id: int) -> Path | None:
    unruled = _rows(conn,
        "SELECT * FROM motions WHERE matter_id=? AND ruled_on=0 AND status='ACTIVE'",
        (matter_id,))
    if not unruled:
        return None
    threshold = [m for m in unruled if m["threshold_motion"]]
    return Path(
        key="request_ruling",
        label="Request a ruling on the record",
        what_it_does=(
            f"{len(unruled)} motion(s) are pending with no ruling"
            + (f", {len(threshold)} of them threshold motions" if threshold else "")
            + ". A request passed over without a ruling can later be treated as "
              "abandoned unless the record shows both the request and the absence "
              "of a ruling."),
        preserves=f"{len(unruled)} pending motion(s)",
        urgency_reason="Pending since " + min(
            (m["filed_date"] for m in unruled if m["filed_date"]), default="an unrecorded date"),
    )


def _contradiction_path(conn: sqlite3.Connection, matter_id: int) -> Path | None:
    open_conflicts = _count(conn,
        "SELECT COUNT(*) FROM contradictions WHERE matter_id=? AND resolved=0 "
        "AND status='ACTIVE'", (matter_id,))
    if not open_conflicts:
        return None
    return Path(
        key="resolve_contradictions",
        label="Resolve open contradictions before filing",
        what_it_does=(
            f"{open_conflicts} contradiction(s) in the record are unresolved. Filing "
            "while the record contradicts itself hands the point to the other side."),
        blockers=[f"{open_conflicts} contradiction(s) need a recorded resolution"],
    )


def _evidence_path(conn: sqlite3.Connection, matter_id: int) -> Path | None:
    unsourced = _count(conn,
        "SELECT COUNT(*) FROM issues WHERE matter_id=? AND status IN "
        "('ACTIVE','MISSING_PROOF') AND verification_status IN ('MISSING_SOURCE','UNKNOWN')",
        (matter_id,))
    if not unsourced:
        return None
    return Path(
        key="link_sources",
        label="Link source documents to unsourced issues",
        what_it_does=(
            f"{unsourced} active issue(s) have no source document linked. An issue "
            "without a source cannot be argued as a verified fact."),
        blockers=[f"{unsourced} issue(s) need a linked source document"],
    )


def _redteam_path(conn: sqlite3.Connection, matter_id: int) -> Path | None:
    active = _count(conn,
        "SELECT COUNT(*) FROM issues WHERE matter_id=? AND status='ACTIVE'", (matter_id,))
    if not active:
        return None
    with_defense = _count(conn,
        "SELECT COUNT(DISTINCT issue_id) FROM defenses WHERE matter_id=? AND status='ACTIVE' "
        "AND issue_id IS NOT NULL", (matter_id,))
    missing = active - with_defense
    if missing <= 0:
        return None
    return Path(
        key="red_team",
        label="Red-team the remaining issues",
        what_it_does=(
            f"{missing} active issue(s) have no recorded opposing argument. Running a "
            "defense review surfaces the attack before the other side makes it."),
        preserves=None,
    )


def _access_path(conn: sqlite3.Connection, matter_id: int) -> Path | None:
    unreported = _count(conn,
        "SELECT COUNT(*) FROM access_barriers WHERE status='ACTIVE' AND reported_to_tribunal=0 "
        "AND (matter_id=? OR matter_id IS NULL)", (matter_id,))
    if not unreported:
        return None
    return Path(
        key="report_access_barrier",
        label="Put an access barrier on the record",
        what_it_does=(
            f"{unreported} logged barrier(s) that prevented a filing were never reported "
            "to the tribunal. A barrier raised for the first time on appeal is much "
            "harder to rely on than one the record already shows."),
        preserves="Prejudice to the right to be heard (PSC-020, PSC-021)",
    )


PATH_BUILDERS: tuple[Callable[[sqlite3.Connection, int], "Path | None"], ...] = (
    _exceptions_path,
    _appeal_path,
    _ruling_path,
    _contradiction_path,
    _evidence_path,
    _redteam_path,
    _access_path,
)


def build_atlas(conn: sqlite3.Connection, matter_id: int) -> dict[str, Any]:
    """Assemble every path this system can evaluate for a matter."""
    matter = conn.execute("SELECT * FROM matters WHERE id=?", (matter_id,)).fetchone()
    if matter is None:
        return {}

    paths = [p for p in (build(conn, matter_id) for build in PATH_BUILDERS) if p]

    available = [p for p in paths if p.available]
    blocked = [p for p in paths if not p.available]
    preserving = [p for p in paths if p.preserves]

    # Suggested order is driven by deadline pressure alone — soonest date first,
    # then paths with no date. It is a sort of the record, not a strategy.
    def sort_key(path: Path) -> tuple[int, int]:
        days = path.days_left
        return (0, days) if days is not None else (1, 0)

    suggested = sorted(available, key=sort_key)

    return {
        "matter": dict(matter),
        "available": [p.to_dict() for p in available],
        "blocked": [p.to_dict() for p in blocked],
        "preserving": [p.to_dict() for p in preserving],
        "suggested_order": [p.to_dict() for p in suggested],
        "counts": {
            "available": len(available),
            "blocked": len(blocked),
            "preserving": len(preserving),
        },
        "disclaimer": (
            "Availability here means this system found no recorded obstacle. It is not "
            "advice that a path is available in law, and nothing on this page predicts "
            "how a tribunal will rule."
        ),
    }


def coverage(conn: sqlite3.Connection, matter_id: int | None = None) -> dict[str, Any]:
    """Record coverage as a count, never as a health score.

    "14 of 23 issues have a linked source" can be checked against the record.
    "68% case health" cannot be checked against anything, which is why this
    returns numerators and denominators rather than a single number.
    """
    where = "WHERE matter_id=?" if matter_id is not None else ""
    params: tuple = (matter_id,) if matter_id is not None else ()

    total = _count(conn, f"SELECT COUNT(*) FROM issues {where}", params)
    sourced = _count(conn, f"""
        SELECT COUNT(*) FROM issues {where}
        {'AND' if where else 'WHERE'} verification_status IN
            ('VERIFIED_PRIMARY','VERIFIED_SECONDARY')
    """, params)
    partial = _count(conn, f"""
        SELECT COUNT(*) FROM issues {where}
        {'AND' if where else 'WHERE'} verification_status IN
            ('PARTIALLY_VERIFIED','INFERENCE','DISPUTED')
    """, params)

    preservation_total = _count(conn,
        f"SELECT COUNT(*) FROM preservation_items {where}", params)
    preservation_raised = _count(conn, f"""
        SELECT COUNT(*) FROM preservation_items {where}
        {'AND' if where else 'WHERE'} raised=1
    """, params)

    return {
        "issues_total": total,
        "issues_sourced": sourced,
        "issues_partial": partial,
        "issues_unsourced": max(0, total - sourced - partial),
        "preservation_total": preservation_total,
        "preservation_raised": preservation_raised,
        "label": f"{sourced} of {total} issues have a linked source",
        "preservation_label":
            f"{preservation_raised} of {preservation_total} issues recorded as raised",
        "note": ("A count, not a score. Every number here can be checked against the "
                 "record; a single health percentage could not be."),
    }


# ---------------------------------------------------------------------------
# graph layout
#
# The Path Atlas was four columns of prose. Prose is the wrong shape for this
# question: "what can I do, what is stopping it, and what does it protect" is a
# question about *relationships*, and a reader should be able to see a blocked
# path and its missing prerequisite in one glance rather than by matching text
# across two cards.
#
# Layout is computed here rather than in the browser for two reasons. The map
# renders identically in a screenshot, a print, and a hearing-mode display with
# no scripting; and a deterministic layout means the same record always draws
# the same picture, which matters when the picture is going to be looked at
# repeatedly under time pressure.
#
# Nothing here scores or predicts. A node is available or it names what blocks
# it. There is no risk dial and no likelihood.
# ---------------------------------------------------------------------------
NODE_W = 232
NODE_H = 74
COL_GAP = 92
ROW_GAP = 20
MARGIN = 28

#: Column order, left to right. Prerequisites sit before the path they gate
#: because that is the reading order of the question: what is missing, what does
#: it block, what would that have protected.
COLUMNS = ("matter", "blocker", "path", "preserves")


def _column_x(index: int) -> int:
    return MARGIN + index * (NODE_W + COL_GAP)


def graph(conn: sqlite3.Connection, matter_id: int) -> dict[str, Any]:
    """Path Atlas as a directed graph with fixed coordinates.

    Returns nodes carrying x/y/width/height and edges carrying a cubic bezier
    path string, so a template can draw an SVG without computing anything.
    """
    atlas = build_atlas(conn, matter_id)
    if not atlas:
        return {}

    matter = atlas["matter"]
    paths = atlas["blocked"] + atlas["suggested_order"]
    # Blocked first, then available by deadline pressure. Reading top to bottom
    # is then "what is stuck" followed by "what is ready", which is the order a
    # person actually needs.

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    def add_node(col: str, key: str, **kw: Any) -> dict[str, Any]:
        node = {"id": f"{col}:{key}", "column": col,
                "x": _column_x(COLUMNS.index(col)), "w": NODE_W, "h": NODE_H, **kw}
        nodes.append(node)
        return node

    def stack(column: str) -> list[dict[str, Any]]:
        return [n for n in nodes if n["column"] == column]

    def place(node: dict[str, Any], y: int) -> None:
        node["y"] = y

    # -- paths, evenly stacked ---------------------------------------------
    path_nodes: list[dict[str, Any]] = []
    y = MARGIN
    for p in paths:
        node = add_node("path", p["key"], label=p["label"], what=p["what_it_does"],
                        state="blocked" if p["blockers"] else "open",
                        days_left=p["days_left"], urgency_date=p["urgency_date"],
                        urgency_reason=p["urgency_reason"],
                        authority=p["authority_to_confirm"])
        place(node, y)
        path_nodes.append(node)
        y += NODE_H + ROW_GAP

    # -- blockers, aligned to the path they gate ---------------------------
    for p, node in zip(paths, path_nodes):
        for i, blocker in enumerate(p["blockers"]):
            b = add_node("blocker", f"{p['key']}-{i}", label=blocker, state="missing")
            place(b, node["y"] + i * (NODE_H + ROW_GAP) // max(1, len(p["blockers"])))
            edges.append(_edge(b, node, "blocks"))

    # -- what a path preserves ---------------------------------------------
    for p, node in zip(paths, path_nodes):
        if p["preserves"]:
            pr = add_node("preserves", p["key"], label=p["preserves"], state="preserves")
            place(pr, node["y"])
            edges.append(_edge(node, pr, "preserves"))

    # -- the matter itself, centred against the path stack ------------------
    height = max([n["y"] + n["h"] for n in nodes], default=MARGIN + NODE_H)
    # The forum name is often longer than the node. Truncate it here rather
    # than letting SVG text run past its own box.
    forum = matter.get("forum") or ""
    root = add_node("matter", matter["slug"], label=matter["title"],
                    caption=matter.get("case_number") or "", state="matter",
                    forum=forum if len(forum) <= 34 else forum[:33].rstrip() + "…")
    place(root, max(MARGIN, (height - NODE_H) // 2))
    for node in path_nodes:
        edges.append(_edge(root, node, "considers"))

    # -- cross-matter references -------------------------------------------
    # Six matters are kept permanently separate. Drawing that is the point:
    # a link is a reference, never a merge, and the picture should not let
    # anyone forget which.
    links = _rows(conn, """
        SELECT l.relationship, l.notes, m.slug, m.title, m.case_number
        FROM matter_links l JOIN matters m ON m.id = l.related_matter_id
        WHERE l.matter_id = ? ORDER BY l.relationship, m.slug
    """, (matter_id,))

    # Wrap once, here, so the template only draws.
    for node in nodes:
        node["lines"] = _wrap(str(node.get("label") or ""), 30,
                              1 if node["column"] == "matter" else 2)

    width = _column_x(len(COLUMNS) - 1) + NODE_W + MARGIN
    return {
        "matter": matter,
        "nodes": nodes,
        "edges": edges,
        "links": links,
        "width": width,
        "height": max(height, root["y"] + NODE_H) + MARGIN,
        "counts": atlas["counts"],
        "disclaimer": atlas["disclaimer"],
        "empty": not path_nodes,
        "empty_reason": (
            "No procedural path can be evaluated for this matter yet. That is a "
            "statement about the record, not about the case: paths appear once "
            "the record holds the orders, deadlines, and issues they depend on."
        ),
    }


def _wrap(text: str, width: int, max_lines: int) -> list[str]:
    """Word-aware wrap for SVG text, which cannot wrap itself.

    Slicing a label at a fixed column splits words mid-character and, worse,
    silently drops the tail. A blocker that reads "17 issue(s) need a linked
    source d…" has lost the word that says what to supply. Wrapping on word
    boundaries and marking a genuine overflow keeps the node honest about
    whether anything was cut.
    """
    words, lines, current = text.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
        if len(lines) == max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)

    consumed = len(" ".join(lines))
    if consumed < len(text.strip()):
        lines[-1] = lines[-1][:width - 1].rstrip() + "…"
    return lines


def _edge(src: dict[str, Any], dst: dict[str, Any], kind: str) -> dict[str, Any]:
    """A cubic bezier from the right edge of *src* to the left edge of *dst*."""
    x1, y1 = src["x"] + src["w"], src["y"] + src["h"] // 2
    x2, y2 = dst["x"], dst["y"] + dst["h"] // 2
    mid = (x1 + x2) / 2
    return {
        "kind": kind,
        "d": f"M {x1} {y1} C {mid} {y1}, {mid} {y2}, {x2} {y2}",
        "from": src["id"], "to": dst["id"],
    }
