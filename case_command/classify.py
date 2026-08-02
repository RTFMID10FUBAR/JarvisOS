"""Matter classification and folder routing.

The routing rules in the specification are implemented as ordered, explainable
signal sets. Every classification carries the rule that fired and the terms that
matched, so a wrong answer can be corrected at the rule rather than by guessing.

Classification never moves a file. It produces a *proposal*. Ingestion records
the proposal; a human approves the matter assignment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import (
    ARCHIVE,
    BRIDGEPORT,
    FINAL_FILINGS,
    INBOX,
    MORTGAGE,
    OTHER_CASES,
    PSC_AEP,
    SHARED_EVIDENCE,
    VETERANS,
)


@dataclass
class Signal:
    """One routing rule: a folder, the terms that select it, and its weight."""

    folder: str
    name: str
    terms: tuple[str, ...]
    weight: float = 1.0
    #: Terms worth far more than a passing mention (docket numbers, party names).
    strong_terms: tuple[str, ...] = ()


# Order matters only for tie-breaking; scoring decides the winner.
SIGNALS: tuple[Signal, ...] = (
    Signal(
        folder=PSC_AEP,
        name="psc_aep_utility",
        terms=(
            "public service commission", "psc", "appalachian power", "apco", "aep",
            "utility", "electric service", "shutoff", "shut-off", "shut off",
            "termination of service", "disconnection", "tariff", "meter",
            "kilowatt", "kwh", "rule 60", "mandamus", "administrative law judge",
            "alj", "recommended decision", "exceptions", "wvsca",
            "west virginia supreme court", "commission staff", "ratepayer",
            "budget billing", "deposit", "reconnection",
        ),
        strong_terms=(
            "24-0735-e-c", "26-0315-e-c", "24-0735", "26-0315",
            "appalachian power company", "public service commission of west virginia",
        ),
        weight=1.0,
    ),
    Signal(
        folder=MORTGAGE,
        name="mortgage_servicing",
        terms=(
            "rocket mortgage", "rocket", "phh", "onity", "ocwen", "respa",
            "mortgage", "foreclosure", "loss mitigation", "servicer", "servicing",
            "escrow", "deed of trust", "promissory note", "loan modification",
            "notice of default", "reinstatement", "forbearance", "va loan",
            "qualified written request", "regulation x", "12 c.f.r. 1024",
        ),
        strong_terms=("rocket mortgage", "phh mortgage", "onity group", "respa"),
        weight=1.0,
    ),
    Signal(
        folder=BRIDGEPORT,
        name="bridgeport_belmont",
        terms=(
            "bridgeport", "belmont county", "belmont", "ada",
            "americans with disabilities act", "bench trial", "jury trial",
            "village of bridgeport", "municipal court", "ohio",
        ),
        strong_terms=("village of bridgeport", "belmont county"),
        weight=1.0,
    ),
    Signal(
        folder=VETERANS,
        name="veterans_benefits",
        terms=(
            "department of veterans affairs", "veterans affairs", "va disability",
            "disability compensation", "smc", "special monthly compensation",
            "board of veterans", "bva", "veteran", "service connected",
            "service-connected", "dependent", "va benefits", "va housing",
            "specially adapted housing", "veterans assistance", "dd-214", "dd214",
        ),
        strong_terms=("department of veterans affairs", "board of veterans' appeals",
                      "special monthly compensation"),
        weight=1.0,
    ),
    Signal(
        folder=SHARED_EVIDENCE,
        name="shared_hardship_evidence",
        terms=(
            "hardship", "declaration", "affidavit", "medical record",
            "disability documentation", "receipt", "photograph", "photo log",
            "timeline", "bank statement", "income", "proof of identity",
            "account statement", "transportation", "vehicle loss",
            "food loss", "spoilage", "generator", "temperature log",
        ),
        strong_terms=("hardship declaration", "disability documentation"),
        weight=0.85,
    ),
)

#: Terms that indicate a document is a real, operative filing rather than a
#: draft. These NEVER set a filing status by themselves — see filings.py. They
#: only flag a document for filing-status review.
FINAL_FILING_SIGNALS = (
    "filed", "e-filed", "efiled", "date filed", "clerk of court",
    "certificate of service", "served upon", "docketed", "entered",
    "so ordered", "it is hereby ordered", "received and filed",
    "electronically filed", "file-stamped", "filing receipt",
    "confirmation number", "transaction receipt",
)

#: Terms that mark working material. Presence of any of these blocks a document
#: from being treated as final even if a filing signal also appears.
DRAFT_SIGNALS = (
    "draft", "working copy", "do not file", "for review", "redline",
    "track changes", "wip", "rough", "outline", "template", "sample",
    "v1", "v2", "rev1", "rev 1",
)

ARCHIVE_SIGNALS = (
    "superseded", "obsolete", "old version", "duplicate", "rejected",
    "withdrawn", "replaced by", "do not use", "archive",
)


@dataclass
class Classification:
    """A routing proposal. Never applied without approval."""

    folder: str
    confidence: float
    rule: str
    matched_terms: list[str] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    cross_reference_folders: list[str] = field(default_factory=list)
    looks_final: bool = False
    looks_draft: bool = False
    looks_archivable: bool = False
    reasons: list[str] = field(default_factory=list)

    @property
    def needs_human_choice(self) -> bool:
        """True when the app must ask 'Which matter?' rather than assume."""
        return self.folder == INBOX or self.confidence < 0.35

    def to_dict(self) -> dict[str, object]:
        return {
            "folder": self.folder,
            "confidence": round(self.confidence, 4),
            "rule": self.rule,
            "matched_terms": self.matched_terms[:40],
            "scores": {k: round(v, 4) for k, v in self.scores.items()},
            "cross_reference_folders": self.cross_reference_folders,
            "looks_final": self.looks_final,
            "looks_draft": self.looks_draft,
            "looks_archivable": self.looks_archivable,
            "reasons": self.reasons,
        }


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def _count_terms(haystack: str, terms: tuple[str, ...]) -> list[str]:
    hits: list[str] = []
    for term in terms:
        # Word-boundary match for short alphanumeric terms so "psc" does not fire
        # inside "psychology" and "aep" does not fire inside "aeplan".
        if len(term) <= 4 and term.isalnum():
            if re.search(rf"\b{re.escape(term)}\b", haystack):
                hits.append(term)
        elif term in haystack:
            hits.append(term)
    return hits


def classify_text(text: str, *, filename: str = "", current_folder: str | None = None) -> Classification:
    """Score a document's text (and filename) against the routing rules."""
    haystack = _normalize(f"{filename}\n{text}")
    name_hay = _normalize(filename)

    scores: dict[str, float] = {}
    matched: dict[str, list[str]] = {}
    rule_for_folder: dict[str, str] = {}

    for signal in SIGNALS:
        hits = _count_terms(haystack, signal.terms)
        strong_hits = _count_terms(haystack, signal.strong_terms)
        name_hits = _count_terms(name_hay, signal.terms + signal.strong_terms)
        if not hits and not strong_hits:
            continue
        # Diminishing returns on repeated ordinary terms; strong terms and
        # filename matches are weighted heavily because they rarely appear by
        # accident.
        score = (
            len(set(hits)) * 1.0
            + len(set(strong_hits)) * 6.0
            + len(set(name_hits)) * 2.5
        ) * signal.weight
        if score > scores.get(signal.folder, 0.0):
            rule_for_folder[signal.folder] = signal.name
        scores[signal.folder] = scores.get(signal.folder, 0.0) + score
        matched.setdefault(signal.folder, []).extend(sorted(set(hits + strong_hits)))

    looks_draft = bool(_count_terms(haystack, DRAFT_SIGNALS))
    looks_final = bool(_count_terms(haystack, FINAL_FILING_SIGNALS)) and not looks_draft
    looks_archivable = bool(_count_terms(haystack, ARCHIVE_SIGNALS))

    if not scores:
        return Classification(
            folder=INBOX,
            confidence=0.0,
            rule="unclassified",
            scores={},
            looks_final=looks_final,
            looks_draft=looks_draft,
            looks_archivable=looks_archivable,
            reasons=["No routing term matched. Held in 00_INBOX for a human decision."],
        )

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_folder, top_score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
    total = sum(scores.values()) or 1.0

    # Confidence blends share-of-signal with margin over the runner-up, so a
    # document that matches two matters equally is reported as uncertain.
    share = top_score / total
    margin = (top_score - runner_up) / top_score if top_score else 0.0
    confidence = round(min(0.99, 0.5 * share + 0.5 * margin), 4)

    # Any other matter with real signal becomes a cross-reference candidate.
    # This is how one stored document serves several cases without being copied.
    cross = [f for f, s in ranked[1:] if s >= max(2.0, top_score * 0.25)]

    reasons = [
        f"Matched {len(set(matched.get(top_folder, [])))} distinct terms for {top_folder}.",
    ]
    if cross:
        reasons.append(
            "Also matched " + ", ".join(cross)
            + ". Proposed as cross-matter links, not copies."
        )
    if looks_draft:
        reasons.append("Draft language present: blocked from 07_FINAL_FILINGS.")
    if looks_final:
        reasons.append("Filing language present: flagged for filing-status review "
                       "(proof still required before any confirmed status).")
    if looks_archivable:
        reasons.append("Superseded/duplicate language present: 99_ARCHIVE proposed for review.")
    if current_folder and current_folder != INBOX and current_folder != top_folder:
        reasons.append(
            f"Currently stored in {current_folder}; classification suggests {top_folder}. "
            "No move is performed without approval."
        )

    return Classification(
        folder=top_folder,
        confidence=confidence,
        rule=rule_for_folder.get(top_folder, "scored"),
        matched_terms=sorted(set(matched.get(top_folder, []))),
        scores=scores,
        cross_reference_folders=cross,
        looks_final=looks_final,
        looks_draft=looks_draft,
        looks_archivable=looks_archivable,
        reasons=reasons,
    )


def classify_document(path: Path, text: str, *, current_folder: str | None = None) -> Classification:
    """Classify using both the extracted text and the filename."""
    result = classify_text(text, filename=path.name, current_folder=current_folder)
    if result.folder == INBOX and not text.strip():
        result.reasons.append(
            "No text could be extracted, so routing had only the filename to work with."
        )
    return result


def unmatched_folder_default(text: str) -> str:
    """Where a legal document with no matter match belongs.

    A document that reads like a legal matter but matches no configured case
    goes to 05_OTHER_CASES rather than sitting in the inbox forever.
    """
    haystack = _normalize(text)
    legal_markers = (
        "plaintiff", "defendant", "petitioner", "respondent", "complainant",
        "in the matter of", "case no", "civil action", "docket", "court",
        "hereby", "affiant", "counsel for",
    )
    if len(_count_terms(haystack, legal_markers)) >= 2:
        return OTHER_CASES
    return INBOX


#: Exported so the web layer and tests can present the rule set without
#: reaching into module internals.
FOLDER_ROUTING_SUMMARY = {
    PSC_AEP: "PSC, APCo, AEP, utility, tariff, meter, shutoff, PSC appeal, mandamus, Rule 60",
    MORTGAGE: "Rocket, PHH, Onity, RESPA, mortgage, foreclosure, VA loan",
    BRIDGEPORT: "Bridgeport, Belmont, ADA, bench trial",
    VETERANS: "VA benefits, veteran assistance",
    SHARED_EVIDENCE: "Shared hardship and evidence used across matters",
    OTHER_CASES: "Legal matter not covered by another folder",
    FINAL_FILINGS: "Linked only when docket proof confirms filed/served/entered",
    ARCHIVE: "Proposed for duplicate, superseded, or obsolete material",
    INBOX: "New or unclassified material awaiting a decision",
}
