"""Anti-omission checks.

These run before any draft is marked final. Each check answers one question and
returns findings rather than mutating anything. A finding is never resolved by
deleting the thing that produced it.

    completeness  — is every active issue accounted for?
    conflict      — does this contradict a prior statement, filing, or the record?
    defense       — how does each adversarial reader attack it?
    preservation  — is the issue raised, ruled on, and appealable?
    source        — does every factual assertion cite a document, page, and date?
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from .db import CONFIRMED_FILING_STATUSES

#: The five adversarial readers a draft is tested against.
DEFENSE_PERSPECTIVES = (
    ("APCO_COUNSEL", "APCo counsel: attack standing, notice, tariff compliance, and the record."),
    ("PSC_STAFF", "PSC Staff: attack reliance on utility-supplied information and procedural posture."),
    ("ALJ", "ALJ: attack scope, relevance to the noticed hearing, and whether relief is available."),
    ("NEUTRAL_JUDGE", "Neutral reviewing judge: attack clarity, proof, and whether the request is grantable."),
    ("APPELLATE_JUDGE", "Appellate judge: attack preservation, standard of review, and harmless error."),
)

#: Issue statuses that count as deliberate treatment rather than an omission.
ACCOUNTED_STATUSES = (
    "RESERVED", "OUTSIDE_CURRENT_HEARING", "SUPERSEDED_BY_AUTHORITY", "DECIDED",
)


@dataclass
class Finding:
    check: str
    severity: str          # BLOCKER | WARNING | INFO
    title: str
    detail: str
    target_table: str | None = None
    target_id: int | None = None
    issue_key: str | None = None
    remedy: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "check": self.check, "severity": self.severity, "title": self.title,
            "detail": self.detail, "target_table": self.target_table,
            "target_id": self.target_id, "issue_key": self.issue_key,
            "remedy": self.remedy,
        }


@dataclass
class CheckReport:
    matter_id: int | None
    findings: list[Finding] = field(default_factory=list)

    @property
    def blockers(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "BLOCKER"]

    @property
    def ok(self) -> bool:
        return not self.blockers

    def to_dict(self) -> dict[str, Any]:
        return {
            "matter_id": self.matter_id,
            "ok": self.ok,
            "blocker_count": len(self.blockers),
            "finding_count": len(self.findings),
            "findings": [f.to_dict() for f in self.findings],
        }


# ---------------------------------------------------------------------------
# completeness
# ---------------------------------------------------------------------------
def completeness_check(conn: sqlite3.Connection, matter_id: int,
                       draft_text: str = "") -> list[Finding]:
    """For every active issue: included, excluded, reserved, out of scope,
    already decided, or missing proof. An issue may not simply be absent."""
    findings: list[Finding] = []
    haystack = draft_text.lower()

    issues = conn.execute(
        "SELECT * FROM issues WHERE matter_id=? ORDER BY issue_key", (matter_id,)
    ).fetchall()

    for issue in issues:
        key = (issue["issue_key"] or "").lower()
        title = (issue["title"] or "").lower()
        mentioned = bool(draft_text) and (
            (key and key in haystack)
            or (len(title) > 8 and title in haystack)
            # A distinctive fragment of the title is enough to count as covered.
            or any(len(word) > 6 and word in haystack for word in re.findall(r"\w+", title))
        )

        if issue["status"] in ACCOUNTED_STATUSES:
            findings.append(Finding(
                check="completeness", severity="INFO",
                title=f"{issue['issue_key']} is {issue['status']}",
                detail=f"{issue['title']} — deliberately accounted for, not omitted.",
                target_table="issues", target_id=issue["id"], issue_key=issue["issue_key"],
            ))
            continue

        if issue["status"] == "MISSING_PROOF":
            findings.append(Finding(
                check="completeness", severity="WARNING",
                title=f"{issue['issue_key']} lacks proof",
                detail=f"{issue['title']} — active but marked MISSING_PROOF.",
                target_table="issues", target_id=issue["id"], issue_key=issue["issue_key"],
                remedy="Link a source document or move the issue to RESERVED with a reason.",
            ))
            continue

        if draft_text and not mentioned:
            findings.append(Finding(
                check="completeness", severity="BLOCKER",
                title=f"{issue['issue_key']} is active but absent from the draft",
                detail=(f"{issue['title']} — an ACTIVE issue that the draft does not address. "
                        "Include it, or set it to RESERVED / OUTSIDE_CURRENT_HEARING with a "
                        "recorded reason. It may not simply vanish."),
                target_table="issues", target_id=issue["id"], issue_key=issue["issue_key"],
                remedy="Address it in the draft or change its status with a reason.",
            ))

    return findings


# ---------------------------------------------------------------------------
# conflict
# ---------------------------------------------------------------------------
def conflict_check(conn: sqlite3.Connection, matter_id: int) -> list[Finding]:
    """Compare the record against itself: open contradictions, disputed facts,
    and relief requested but never disposed of."""
    findings: list[Finding] = []

    for row in conn.execute(
        "SELECT * FROM contradictions WHERE matter_id=? AND resolved=0 AND status='ACTIVE'",
        (matter_id,),
    ):
        findings.append(Finding(
            check="conflict", severity="BLOCKER",
            title=f"Unresolved contradiction: {row['title']}",
            detail=(f"LEFT: {row['left_statement'] or '(unstated)'}\n"
                    f"RIGHT: {row['right_statement'] or '(unstated)'}"),
            target_table="contradictions", target_id=row["id"],
            remedy="Resolve it, or state in the draft which version is correct and why.",
        ))

    for row in conn.execute(
        "SELECT * FROM facts WHERE matter_id=? AND disputed=1 AND status='ACTIVE'",
        (matter_id,),
    ):
        findings.append(Finding(
            check="conflict", severity="WARNING",
            title=f"Disputed fact relied upon: {row['title']}",
            detail=row["statement"] or "",
            target_table="facts", target_id=row["id"],
            remedy="Do not present a disputed fact as established.",
        ))

    for row in conn.execute(
        "SELECT * FROM relief WHERE matter_id=? AND disposition IS NULL AND status='ACTIVE'",
        (matter_id,),
    ):
        findings.append(Finding(
            check="conflict", severity="INFO",
            title=f"Relief requested with no recorded disposition: {row['title']}",
            detail="Still outstanding. Carry it forward rather than dropping it.",
            target_table="relief", target_id=row["id"],
        ))

    return findings


# ---------------------------------------------------------------------------
# defense
# ---------------------------------------------------------------------------
def defense_check(conn: sqlite3.Connection, matter_id: int) -> list[Finding]:
    """Confirm every active issue has been red-teamed from all five angles."""
    findings: list[Finding] = []
    issues = conn.execute(
        "SELECT * FROM issues WHERE matter_id=? AND status='ACTIVE'", (matter_id,)
    ).fetchall()

    for issue in issues:
        covered = {
            (row["raised_by"] or "").upper()
            for row in conn.execute(
                "SELECT raised_by FROM defenses WHERE issue_id=? AND status='ACTIVE'",
                (issue["id"],))
        }
        missing = [name for name, _ in DEFENSE_PERSPECTIVES
                   if not any(name in entry for entry in covered)]
        if missing:
            findings.append(Finding(
                check="defense", severity="WARNING",
                title=f"{issue['issue_key']} not red-teamed from {len(missing)} perspective(s)",
                detail="Missing: " + ", ".join(missing),
                target_table="issues", target_id=issue["id"], issue_key=issue["issue_key"],
                remedy="Run a defense_red_team Fleet job for the missing perspectives.",
            ))
        if not issue["best_reply"] and covered:
            findings.append(Finding(
                check="defense", severity="WARNING",
                title=f"{issue['issue_key']} has an identified attack but no reply",
                detail=issue["opponent_defense"] or "",
                target_table="issues", target_id=issue["id"], issue_key=issue["issue_key"],
                remedy="Record the best reply before filing.",
            ))
    return findings


# ---------------------------------------------------------------------------
# preservation
# ---------------------------------------------------------------------------
def preservation_check(conn: sqlite3.Connection, matter_id: int) -> list[Finding]:
    """Raised, ruling requested, ruling obtained or ignored, exception, deadline."""
    findings: list[Finding] = []

    for row in conn.execute(
        """
        SELECT p.*, i.issue_key, i.title AS issue_title
        FROM preservation_items p
        LEFT JOIN issues i ON i.id = p.issue_id
        WHERE p.matter_id=? AND p.status='ACTIVE'
        """,
        (matter_id,),
    ):
        key = row["issue_key"]
        if not row["raised"]:
            findings.append(Finding(
                check="preservation", severity="WARNING",
                title=f"{key or row['title']}: never raised",
                detail="An issue not raised below is not preserved for review.",
                target_table="preservation_items", target_id=row["id"], issue_key=key,
                remedy="Raise it, or record why it did not need to be raised.",
            ))
            continue
        if row["ruling_requested"] and not row["ruling_issued"]:
            findings.append(Finding(
                check="preservation", severity="BLOCKER",
                title=f"{key or row['title']}: ruling requested but never issued",
                detail=("A request left unruled can be treated as abandoned unless the "
                        "record shows the request and the absence of a ruling."),
                target_table="preservation_items", target_id=row["id"], issue_key=key,
                remedy="Renew the request, note the absence on the record, or file an exception.",
            ))
        if row["ignored"] and not row["exception_filed"]:
            findings.append(Finding(
                check="preservation", severity="BLOCKER",
                title=f"{key or row['title']}: ignored, no exception filed",
                detail="An ignored motion needs an exception or a renewed request to survive.",
                target_table="preservation_items", target_id=row["id"], issue_key=key,
                remedy="File an exception before the deadline.",
            ))
        if row["exception_required"] and not row["exception_filed"]:
            findings.append(Finding(
                check="preservation", severity="BLOCKER",
                title=f"{key or row['title']}: exception required but not filed",
                detail=f"Appeal deadline: {row['appeal_deadline'] or 'unknown'}",
                target_table="preservation_items", target_id=row["id"], issue_key=key,
                remedy="File the exception.",
            ))
        if not row["standard_of_review"]:
            findings.append(Finding(
                check="preservation", severity="INFO",
                title=f"{key or row['title']}: no standard of review recorded",
                detail="Needed to frame the argument on appeal.",
                target_table="preservation_items", target_id=row["id"], issue_key=key,
            ))

    # Unruled threshold motions are a preservation problem in their own right.
    for row in conn.execute(
        "SELECT * FROM motions WHERE matter_id=? AND ruled_on=0 AND status='ACTIVE'",
        (matter_id,),
    ):
        findings.append(Finding(
            check="preservation",
            severity="BLOCKER" if row["threshold_motion"] else "WARNING",
            title=f"Motion pending with no ruling: {row['title']}",
            detail=f"Filed {row['filed_date'] or 'date unknown'}. Still unresolved.",
            target_table="motions", target_id=row["id"],
            remedy="Request a ruling on the record and preserve the absence of one.",
        ))

    return findings


# ---------------------------------------------------------------------------
# source
# ---------------------------------------------------------------------------
def source_check(conn: sqlite3.Connection, matter_id: int) -> list[Finding]:
    """Every verified item must cite a document, a locator, and a date."""
    findings: list[Finding] = []

    for table, label in (("facts", "fact"), ("events", "event"), ("evidence", "evidence item"),
                         ("issues", "issue"), ("filings", "filing"), ("orders", "order")):
        for row in conn.execute(
            f"SELECT * FROM {table} WHERE matter_id=? AND status <> 'SUPERSEDED' "
            f"AND verification_status IN ('VERIFIED_PRIMARY','VERIFIED_SECONDARY')",
            (matter_id,),
        ):
            problems = []
            if not row["source_document_id"]:
                problems.append("no source document")
            if not row["source_page_or_paragraph"]:
                problems.append("no page or paragraph locator")
            if problems:
                findings.append(Finding(
                    check="source", severity="BLOCKER",
                    title=f"Verified {label} without a source: {row['title']}",
                    detail=("Marked " + row["verification_status"] + " but has "
                            + " and ".join(problems) + "."),
                    target_table=table, target_id=row["id"],
                    remedy="Attach the source and locator, or downgrade to MISSING_SOURCE.",
                ))

    # A filing may not claim a confirmed status without proof. The database
    # constraint prevents it; this surfaces anything that predates the constraint.
    for row in conn.execute(
        "SELECT * FROM filings WHERE matter_id=? AND filing_status IN "
        f"({','.join('?' * len(CONFIRMED_FILING_STATUSES))})",
        (matter_id, *CONFIRMED_FILING_STATUSES),
    ):
        if not row["proof_type"]:
            findings.append(Finding(
                check="source", severity="BLOCKER",
                title=f"Filing claims {row['filing_status']} without proof: {row['title']}",
                detail="Folder or Drive presence is never proof of filing.",
                target_table="filings", target_id=row["id"],
                remedy="Attach a docket entry, clerk confirmation, stamped copy, "
                       "electronic receipt, official order, or verified service receipt.",
            ))

    for row in conn.execute(
        "SELECT * FROM unknowns WHERE matter_id=? AND resolved=0 AND status='ACTIVE'",
        (matter_id,),
    ):
        findings.append(Finding(
            check="source", severity="WARNING",
            title=f"Open unknown: {row['title']}",
            detail=row["question"] or "",
            target_table="unknowns", target_id=row["id"],
            remedy=row["how_to_resolve"] or "Resolve before relying on this area.",
        ))

    return findings


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------
def run_all(conn: sqlite3.Connection, matter_id: int,
            draft_text: str = "") -> CheckReport:
    """Run every pre-final check for a matter."""
    report = CheckReport(matter_id=matter_id)
    report.findings.extend(completeness_check(conn, matter_id, draft_text))
    report.findings.extend(conflict_check(conn, matter_id))
    report.findings.extend(defense_check(conn, matter_id))
    report.findings.extend(preservation_check(conn, matter_id))
    report.findings.extend(source_check(conn, matter_id))
    order = {"BLOCKER": 0, "WARNING": 1, "INFO": 2}
    report.findings.sort(key=lambda f: (order.get(f.severity, 3), f.check, f.title))
    return report


def can_mark_final(conn: sqlite3.Connection, matter_id: int,
                   draft_text: str) -> tuple[bool, CheckReport]:
    """A draft may be marked final only when no blocker remains."""
    report = run_all(conn, matter_id, draft_text)
    return report.ok, report
