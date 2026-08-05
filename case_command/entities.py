"""Entity and metadata extraction from document text.

Everything produced here is a *proposal* with a source locator. Nothing is
written into the canonical record as verified. When a value cannot be
determined, an ``unknowns`` candidate is produced instead of a guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Iterable

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

_LONG_DATE = re.compile(
    r"\b(" + "|".join(MONTHS) + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b",
    re.IGNORECASE,
)
_NUMERIC_DATE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

# PSC-style docket numbers (24-0735-E-C) and general case numbers.
_PSC_CASE = re.compile(r"\b(\d{2}-\d{3,5}-[A-Z]{1,3}(?:-[A-Z]{1,3})?)\b")
_GENERIC_CASE = re.compile(
    r"\b(?:case|civil action|docket|no\.?|number)\s*(?:no\.?|#)?\s*"
    r"([0-9]{1,4}[:\-][0-9]{2,6}[A-Za-z0-9\-]*|[0-9]{2,6}-[A-Za-z0-9\-]{2,20})",
    re.IGNORECASE,
)

_MONEY = re.compile(r"\$\s?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|[0-9]+\.[0-9]{2})")

_RULE_CITE = re.compile(
    r"\b(?:Rule|R\.)\s*([0-9]+(?:\.[0-9]+)*(?:\([a-z0-9]+\))*)\b", re.IGNORECASE)
_CFR_CITE = re.compile(r"\b(\d{1,2})\s*C\.?F\.?R\.?\s*(?:§+\s*)?([\d.]+)", re.IGNORECASE)
_USC_CITE = re.compile(r"\b(\d{1,2})\s*U\.?S\.?C\.?\s*(?:§+\s*)?([\d\-]+)", re.IGNORECASE)
_WV_CODE = re.compile(r"\bW\.?\s?Va\.?\s*Code\s*(?:§+\s*)?([\d\-A-Za-z.]+)", re.IGNORECASE)
_CSR_CITE = re.compile(r"\b(\d{1,3})\s*C\.?S\.?R\.?\s*(?:§+\s*)?([\d.\-]+)", re.IGNORECASE)

_EXHIBIT = re.compile(r"\bexhibit\s+([A-Z0-9]{1,4})\b", re.IGNORECASE)

_JUDGE = re.compile(
    r"\b(?:the\s+)?(?:Hon(?:orable)?\.?|Judge|Justice)\s+([A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){0,3})")
_ALJ = re.compile(
    r"\b(?:Administrative\s+Law\s+Judge|ALJ)\s+([A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){0,3})")
_COUNSEL = re.compile(
    r"\b(?:Counsel\s+for|Attorney\s+for|Esq\.?,?\s+(?:counsel\s+for)?)\s*"
    r"(?:the\s+)?([A-Z][A-Za-z.'\- ]{2,60})")

_COURT = re.compile(
    r"\b((?:Supreme\s+Court(?:\s+of\s+Appeals)?|Circuit\s+Court|District\s+Court|"
    r"Court\s+of\s+Appeals|Municipal\s+Court|Public\s+Service\s+Commission|"
    r"Board\s+of\s+Veterans'?\s+Appeals)"
    r"(?:\s+(?:of|for)\s+[A-Za-z ,.]{3,60})?)", re.IGNORECASE)

_DEADLINE_CUE = re.compile(
    r"([^.\n]{0,200}?\b(?:no\s+later\s+than|on\s+or\s+before|within\s+\w+\s+(?:\(\d+\)\s*)?days?"
    r"|due\s+(?:on|by)|shall\s+be\s+filed\s+by|must\s+be\s+(?:filed|served)\s+(?:by|within)"
    r"|deadline)\b[^.\n]{0,200})", re.IGNORECASE)

_RELIEF_CUE = re.compile(
    r"([^.\n]{0,160}?\b(?:wherefore|respectfully\s+requests?|prays?\s+(?:for|that)"
    r"|requests?\s+that\s+the\s+(?:Court|Commission)|moves?\s+(?:the\s+\w+\s+)?for)\b[^.\n]{0,300})",
    re.IGNORECASE)

_SERVICE_CUE = re.compile(
    r"certificate\s+of\s+service[^.\n]{0,400}", re.IGNORECASE)

KNOWN_PARTIES = (
    "Appalachian Power Company", "Appalachian Power", "APCo", "AEP",
    "Public Service Commission of West Virginia", "Commission Staff",
    "Rocket Mortgage", "PHH Mortgage", "Onity Group", "Ocwen",
    "Department of Veterans Affairs", "Village of Bridgeport",
    "Jacob Kerr", "Jacob B. Kerr", "Kerr",
)


@dataclass
class Candidate:
    """One proposed piece of structured data, with where it came from."""

    kind: str
    value: str
    locator: str                       # e.g. "p.3" or "char 1204"
    context: str = ""
    confidence: float = 0.5
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "value": self.value,
            "locator": self.locator,
            "context": self.context[:300],
            "confidence": round(self.confidence, 3),
            "extra": self.extra,
        }


def _locator_for(offset: int, pages: list[str] | None) -> str:
    """Translate a character offset into a page locator when pages are known."""
    if not pages:
        return f"char {offset}"
    running = 0
    for index, page_text in enumerate(pages):
        running += len(page_text) + 1
        if offset < running:
            return f"p.{index + 1}"
    return f"p.{len(pages)}"


def _context(text: str, start: int, end: int, width: int = 120) -> str:
    lo = max(0, start - width)
    hi = min(len(text), end + width)
    return re.sub(r"\s+", " ", text[lo:hi]).strip()


def parse_date(raw: str) -> str | None:
    """Normalize a date string to ISO. Returns None when ambiguous or invalid."""
    raw = raw.strip()
    match = _ISO_DATE.search(raw)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat()
        except ValueError:
            return None
    match = _LONG_DATE.search(raw)
    if match:
        month = MONTHS[match.group(1).lower().rstrip(".")]
        try:
            return date(int(match.group(3)), month, int(match.group(2))).isoformat()
        except ValueError:
            return None
    match = _NUMERIC_DATE.search(raw)
    if match:
        month, day, year = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if year < 100:
            year += 2000 if year < 70 else 1900
        # US convention; a day > 12 in the first position is reported as unparsed
        # rather than silently swapped.
        if month > 12:
            return None
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None
    return None


def _scan(pattern: re.Pattern[str], text: str, kind: str, pages: list[str] | None,
          *, group: int = 1, confidence: float = 0.5,
          transform=None) -> list[Candidate]:
    out: list[Candidate] = []
    seen: set[str] = set()
    for match in pattern.finditer(text):
        try:
            value = match.group(group)
        except IndexError:
            continue
        if value is None:
            continue
        value = value.strip().rstrip(".,;:")
        if transform:
            value = transform(match) or value
        if not value or value.lower() in seen:
            continue
        seen.add(value.lower())
        out.append(Candidate(
            kind=kind,
            value=value,
            locator=_locator_for(match.start(), pages),
            context=_context(text, match.start(), match.end()),
            confidence=confidence,
        ))
    return out


def extract_entities(text: str, pages: list[str] | None = None) -> dict[str, list[Candidate]]:
    """Pull every structured signal we know how to recognize out of *text*."""
    if not text:
        return {}

    found: dict[str, list[Candidate]] = {}

    def add(kind: str, candidates: Iterable[Candidate]) -> None:
        items = [c for c in candidates]
        if items:
            found[kind] = items

    add("case_number", _scan(_PSC_CASE, text, "case_number", pages, confidence=0.9))
    generic = _scan(_GENERIC_CASE, text, "case_number", pages, confidence=0.6)
    if generic:
        existing = {c.value.lower() for c in found.get("case_number", [])}
        merged = found.get("case_number", []) + [c for c in generic
                                                 if c.value.lower() not in existing]
        found["case_number"] = merged

    add("court", _scan(_COURT, text, "court", pages, confidence=0.7))
    add("judge", _scan(_JUDGE, text, "judge", pages, confidence=0.6))
    add("alj", _scan(_ALJ, text, "alj", pages, confidence=0.75))
    add("counsel", _scan(_COUNSEL, text, "counsel", pages, confidence=0.45))
    add("exhibit", _scan(_EXHIBIT, text, "exhibit", pages, confidence=0.7))
    add("money", _scan(_MONEY, text, "money", pages, confidence=0.7))
    add("deadline_phrase", _scan(_DEADLINE_CUE, text, "deadline_phrase", pages, confidence=0.55))
    add("relief_request", _scan(_RELIEF_CUE, text, "relief_request", pages, confidence=0.55))
    add("service", _scan(_SERVICE_CUE, text, "service", pages, group=0, confidence=0.6))

    # Rules, statutes, and regulations.
    rules: list[Candidate] = []
    rules += _scan(_RULE_CITE, text, "rule", pages, confidence=0.6,
                   transform=lambda m: f"Rule {m.group(1)}")
    rules += _scan(_CFR_CITE, text, "rule", pages, confidence=0.8,
                   transform=lambda m: f"{m.group(1)} C.F.R. § {m.group(2)}")
    rules += _scan(_USC_CITE, text, "rule", pages, confidence=0.8,
                   transform=lambda m: f"{m.group(1)} U.S.C. § {m.group(2)}")
    rules += _scan(_WV_CODE, text, "rule", pages, confidence=0.8,
                   transform=lambda m: f"W. Va. Code § {m.group(1)}")
    rules += _scan(_CSR_CITE, text, "rule", pages, confidence=0.8,
                   transform=lambda m: f"{m.group(1)} C.S.R. § {m.group(2)}")
    if rules:
        deduped: dict[str, Candidate] = {}
        for candidate in rules:
            deduped.setdefault(candidate.value.lower(), candidate)
        found["rule"] = list(deduped.values())

    # Dates, normalized to ISO with the raw form kept for review.
    dates: list[Candidate] = []
    seen_dates: set[str] = set()
    for pattern in (_ISO_DATE, _LONG_DATE, _NUMERIC_DATE):
        for match in pattern.finditer(text):
            iso = parse_date(match.group(0))
            if not iso or iso in seen_dates:
                continue
            seen_dates.add(iso)
            dates.append(Candidate(
                kind="date",
                value=iso,
                locator=_locator_for(match.start(), pages),
                context=_context(text, match.start(), match.end()),
                confidence=0.75,
                extra={"raw": match.group(0)},
            ))
    if dates:
        found["date"] = sorted(dates, key=lambda c: c.value)

    # Known parties, matched literally so we never invent a party name.
    lowered = text.lower()
    parties: list[Candidate] = []
    for party in KNOWN_PARTIES:
        index = lowered.find(party.lower())
        if index >= 0:
            parties.append(Candidate(
                kind="party",
                value=party,
                locator=_locator_for(index, pages),
                context=_context(text, index, index + len(party)),
                confidence=0.85,
            ))
    if parties:
        found["party"] = parties

    return found


def summarize_entities(found: dict[str, list[Candidate]]) -> dict[str, Any]:
    """Compact, JSON-safe view for storage and for Fleet context packets."""
    return {kind: [c.to_dict() for c in candidates] for kind, candidates in found.items()}


def primary_case_number(found: dict[str, list[Candidate]]) -> str | None:
    candidates = found.get("case_number") or []
    return candidates[0].value if candidates else None


#: Phrases that introduce a document's OWN date, with a priority rank.
#:
#: Ranking matters more than matching. A legal filing cites many dates, and
#: "entered September 3, 2025" inside an answer refers to somebody else's order,
#: not to this document. So a signature block always beats a mid-sentence
#: "entered", and a field-style cue at the start of a line beats the same words
#: buried in a paragraph.
#:
#: rank 1 is the most trustworthy.
_DATE_CUES: tuple[tuple[str, str, int], ...] = (
    (r"\bthis\s+\d{1,2}(?:st|nd|rd|th)?\s+day\s+of\s+", "signature block", 1),
    (r"\bdated\s*:?\s*", "dated line", 2),
    (r"\bserved\s+(?:upon[^.\n]{0,60})?(?:by[^.\n]{0,40})?\s*(?:on)?\s*", "service date", 3),
    (r"\bdate\s+entered\s*:?\s*", "entered date", 4),
    (r"\bdate\s+filed\s*:?\s*", "filed date", 4),
    (r"\bentered\s*(?:on)?\s*:?\s*", "entered date", 5),
    (r"\bfiled\s*(?:on)?\s*:?\s*", "filed date", 5),
    (r"\bissued\s*(?:on)?\s*:?\s*", "issued date", 5),
    (r"\bdate\s*:\s*", "date line", 6),
)

#: A cue at the start of a line is a labelled field ("Entered: September 3,
#: 2025"). The same words mid-paragraph are prose about some other document, so
#: they are demoted below every position-independent cue.
_MID_SENTENCE_PENALTY = 6

#: How much of a document counts as its header. Court and agency filings put the
#: caption block — court, parties, case number, document title — at the top of
#: page one, so almost everything needed to identify a document lives here.
HEADER_CHARS = 1500
HEADER_LINES = 30

#: A cue found in the header outranks the same cue found in the body. "Entered:"
#: in a caption block dates this document; "entered" three pages in is prose
#: about somebody else's order.
_HEADER_BONUS = -2


def header_zone(text: str, pages: list[str] | None = None) -> str:
    """The caption region: page one's top, where a filing identifies itself.

    Two things follow from this, and both matter for scanned documents:
    identification usually needs only page one, and OCR can therefore start
    there instead of processing an entire filing before anything is known.
    """
    if not text:
        return ""
    source = pages[0] if pages else text
    lines = source.splitlines()[:HEADER_LINES]
    return "\n".join(lines)[:HEADER_CHARS]

#: How far after a cue a date still counts as belonging to it.
_CUE_WINDOW = 60


def document_date(found: dict[str, list[Candidate]], text: str = "",
                  pages: list[str] | None = None) -> tuple[str | None, str]:
    """The document's own date, and where that reading came from.

    Returns ``(iso_date_or_None, source_label)``. The label matters: a date read
    off a signature block is evidence, a date inferred from position is a guess,
    and the two must never look alike in a chronology.
    """
    dates = found.get("date", [])
    if not dates:
        return (None, "no date found")

    # 1. Collect every cue hit, then take the best-ranked one. First-match-wins
    #    would let whichever cue appears earliest in the file decide, which is
    #    exactly how a cited order's date hijacks the document's own date.
    if text:
        header_len = len(header_zone(text, pages))
        hits: list[tuple[int, int, str, str]] = []   # (rank, position, iso, label)
        for pattern, label, base_rank in _DATE_CUES:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                line_start = text.rfind("\n", 0, match.start()) + 1
                at_line_start = not text[line_start:match.start()].strip()
                rank = base_rank if at_line_start else base_rank + _MID_SENTENCE_PENALTY
                if match.start() < header_len:
                    rank += _HEADER_BONUS   # caption-block dates identify the filing

                window = text[match.end():match.end() + _CUE_WINDOW]
                iso = parse_date(window)
                if not iso:
                    # "this 5th day of March, 2026" splits day from month/year.
                    stitched = re.match(
                        r"\s*(" + "|".join(MONTHS) + r")\.?,?\s+(\d{4})",
                        window, re.IGNORECASE)
                    day_match = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+day\s+of\s*$",
                                          text[:match.end()], re.IGNORECASE)
                    if stitched and day_match:
                        month = MONTHS[stitched.group(1).lower().rstrip(".")]
                        try:
                            iso = date(int(stitched.group(2)), month,
                                       int(day_match.group(1))).isoformat()
                        except ValueError:
                            iso = None
                if iso:
                    hits.append((rank, match.start(), iso, label))

        if hits:
            # Best rank wins; among equals, the later occurrence wins, because
            # signature and service blocks sit at the end of a filing.
            rank, _pos, iso, label = min(hits, key=lambda h: (h[0], -h[1]))
            qualifier = "" if rank <= len(_DATE_CUES) else " (mid-sentence, verify)"
            return (iso, label + qualifier)

    # 2. No cue. A document is normally dated on or after everything it cites,
    #    so the LATEST date is a better reading than the earliest — but it is
    #    still an inference, and it is labelled as one.
    #    Future dates are excluded: those are deadlines, not the document's date.
    today = datetime.now(timezone.utc).date().isoformat()
    past = [c.value for c in dates if c.value <= today]
    if past:
        return (max(past), "inferred (latest date in document)")
    return (min(c.value for c in dates), "inferred (no past date found)")


def unknowns_for_missing(found: dict[str, list[Candidate]],
                         required: tuple[str, ...] = ("case_number", "court", "date")
                         ) -> list[dict[str, str]]:
    """Turn absent-but-expected fields into explicit unknowns, never guesses."""
    gaps: list[dict[str, str]] = []
    for kind in required:
        if not found.get(kind):
            gaps.append({
                "field": kind,
                "question": f"What is the {kind.replace('_', ' ')} for this document?",
                "why_it_matters": "Required to place the document in the canonical record.",
                "how_to_resolve": "Read the caption or docket entry and set it manually.",
            })
    return gaps


def parse_deadline_days(phrase: str) -> int | None:
    """Extract 'within thirty (30) days' style day counts."""
    match = re.search(r"within\s+(?:\w+\s+)?\((\d{1,3})\)\s*days?", phrase, re.IGNORECASE)
    if match:
        return int(match.group(1))
    match = re.search(r"within\s+(\d{1,3})\s*days?", phrase, re.IGNORECASE)
    if match:
        return int(match.group(1))
    words = {
        "five": 5, "ten": 10, "fourteen": 14, "fifteen": 15, "twenty": 20,
        "thirty": 30, "sixty": 60, "ninety": 90,
    }
    match = re.search(r"within\s+(" + "|".join(words) + r")\s*days?", phrase, re.IGNORECASE)
    if match:
        return words[match.group(1).lower()]
    return None
