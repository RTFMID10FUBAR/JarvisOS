"""Plain text, markdown, JSON, HTML, and transcript (VTT/SRT) extraction.

Also serves as the fallback handler for files of unknown type.
"""

from __future__ import annotations

import pathlib
import re
from html.parser import HTMLParser

from .base import (
    ExtractionResult,
    ExtractContext,
    optional_import,
    native_text_is_incomplete,
    read_bytes_readonly,
)

#: Decoding attempts, in order of preference.
_ENCODINGS = ("utf-8", "utf-8-sig", "cp1252", "latin-1")

#: Extensions treated as HTML markup that needs tag stripping.
_HTML_SUFFIXES = {".htm", ".html"}

#: Extensions treated as caption/transcript files with cue metadata to strip.
_TRANSCRIPT_SUFFIXES = {".vtt", ".srt"}

_CUE_NUMBER_RE = re.compile(r"^\d+$")
_SRT_TIMESTAMP_RE = re.compile(r"\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[.,]\d{3}")
_VTT_TIMESTAMP_RE = re.compile(r"\d{2}:\d{2}(:\d{2})?[.,]\d{3}\s*-->\s*\d{2}:\d{2}(:\d{2})?[.,]\d{3}")


class _TextOnlyHTMLParser(HTMLParser):
    """Minimal HTML-to-text stripper: drops tags, script/style content, unescapes entities."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("script", "style"):
            self._skip_depth += 1
        elif tag in ("br", "p", "div", "tr", "li"):
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag in ("p", "div", "tr", "li"):
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data:
            self._chunks.append(data)

    def get_text(self) -> str:
        return "".join(self._chunks)


def _strip_html(raw: str) -> str:
    parser = _TextOnlyHTMLParser()
    try:
        parser.feed(raw)
        parser.close()
    except Exception:
        pass
    text = parser.get_text()
    # Collapse excessive blank lines left behind by block-tag markers.
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _strip_transcript_cues(raw: str) -> str:
    """Drop cue numbers, timestamp lines, and VTT metadata; keep spoken text."""
    lines_out: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _CUE_NUMBER_RE.match(stripped):
            continue
        if _SRT_TIMESTAMP_RE.search(stripped) or _VTT_TIMESTAMP_RE.search(stripped):
            continue
        if stripped.upper() == "WEBVTT":
            continue
        if stripped.upper().startswith(("NOTE", "STYLE", "REGION")):
            continue
        # Drop common VTT cue-settings-only lines like "align:start position:0%"
        if re.fullmatch(r"(align|position|size|line|vertical):\S+(\s+\S+:\S+)*", stripped):
            continue
        lines_out.append(stripped)
    return "\n".join(lines_out).strip()


def _decode(raw: bytes) -> tuple[str, str]:
    """Try encodings in order, returning (text, encoding_used)."""
    for enc in _ENCODINGS:
        try:
            return raw.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
    # latin-1 never fails to decode any byte sequence; this is unreachable
    # in practice but kept as a hard safety net.
    return raw.decode("latin-1", errors="replace"), "latin-1 (replace)"


def _looks_binary(raw: bytes) -> bool:
    """Heuristic: a high ratio of non-text bytes suggests this isn't really text."""
    if not raw:
        return False
    sample = raw[:8192]
    if b"\x00" in sample:
        return True
    text_bytes = bytes(range(0x20, 0x7F)) + b"\t\n\r\x0b\x0c" + bytes(range(0x80, 0x100))
    nontext = sum(1 for b in sample if b not in text_bytes)
    return (nontext / len(sample)) > 0.30


def extract(path: pathlib.Path, ctx: ExtractContext) -> ExtractionResult:
    result = ExtractionResult()
    try:
        raw = read_bytes_readonly(path, ctx.max_bytes)
    except Exception as exc:
        result.error = f"could not read file: {exc}"
        return result

    if _looks_binary(raw):
        result.method = "none"
        result.error = (
            "file appears to be binary, not text; refusing to extract garbage. "
            "If this is a known format, route it through the correct handler."
        )
        result.warnings.append("high ratio of non-text bytes in sample")
        return result

    text, encoding = _decode(raw)
    suffix = path.suffix.lower()

    if suffix in _HTML_SUFFIXES:
        text = _strip_html(text)
    elif suffix in _TRANSCRIPT_SUFFIXES:
        text = _strip_transcript_cues(text)

    result.text = text
    result.method = "native"
    result.confidence = 1.0
    result.metadata["encoding"] = encoding
    result.metadata["suffix"] = suffix
    result.metadata["byte_count"] = len(raw)
    if not text.strip():
        result.warnings.append("decoded successfully but no text content remained")
    return result
