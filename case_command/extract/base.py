"""Shared contract for every text extractor.

Rules that apply to all extractors:

* Originals are opened read-only. An extractor never writes to the source file.
* Native text extraction is attempted before OCR. OCR runs only when native
  extraction fails or returns materially incomplete text.
* OCR-derived text is never reported as exact. It carries method='ocr', a
  confidence value, and per-page text so the source page can always be shown.
* A missing optional dependency is a reported degradation, never a crash.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: Below this many characters per page, native extraction is treated as
#: materially incomplete and OCR is offered as a fallback.
NATIVE_TEXT_MIN_CHARS_PER_PAGE = 80


@dataclass
class ExtractionResult:
    """Outcome of reading text out of one file."""

    text: str = ""
    method: str = "none"          # native | ocr | native+ocr | partial | none
    confidence: float | None = None   # 0.0-1.0; None when not meaningful
    page_count: int | None = None
    pages: list[str] = field(default_factory=list)   # per-page text when available
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    #: Nested members for containers (ZIP packets, email attachments): each is
    #: (relative_name, bytes). Ingestion re-enters the pipeline for each one.
    members: list[tuple[str, bytes]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def char_count(self) -> int:
        return len(self.text)

    @property
    def used_ocr(self) -> bool:
        return "ocr" in self.method

    def page_locator(self, page_index: int) -> str:
        return f"p.{page_index + 1}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "confidence": self.confidence,
            "page_count": self.page_count,
            "char_count": self.char_count,
            "error": self.error,
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


@dataclass
class ExtractContext:
    """Options handed to an extractor."""

    allow_ocr: bool = True
    ocr_language: str = "eng"
    max_bytes: int = 512 * 1024 * 1024
    #: Recursion guard for nested containers.
    depth: int = 0
    max_depth: int = 3


class MissingDependency(RuntimeError):
    """Raised internally when an optional library is absent; converted to a warning."""


def optional_import(module_name: str):
    """Import an optional dependency, returning None when it is not installed."""
    try:
        import importlib

        return importlib.import_module(module_name)
    except Exception:
        return None


def native_text_is_incomplete(text: str, page_count: int | None) -> bool:
    """True when native extraction produced too little text to trust."""
    pages = page_count or 1
    return len(text.strip()) < NATIVE_TEXT_MIN_CHARS_PER_PAGE * pages


def read_bytes_readonly(path: Path, limit: int) -> bytes:
    """Read a file without modifying it, refusing anything over *limit*."""
    size = path.stat().st_size
    if size > limit:
        raise ValueError(f"file is {size} bytes, over the {limit}-byte extraction limit")
    with open(path, "rb") as handle:
        return handle.read()
