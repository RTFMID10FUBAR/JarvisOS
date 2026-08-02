"""Text extraction dispatch.

`extract_file` picks a handler from the file's extension and magic bytes, then
returns a uniform :class:`ExtractionResult`. Handlers live in sibling modules
and are imported lazily so a missing optional dependency in one format never
blocks the others.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from .base import (
    ExtractContext,
    ExtractionResult,
    MissingDependency,
    NATIVE_TEXT_MIN_CHARS_PER_PAGE,
    native_text_is_incomplete,
    optional_import,
)

__all__ = [
    "ExtractContext",
    "ExtractionResult",
    "MissingDependency",
    "NATIVE_TEXT_MIN_CHARS_PER_PAGE",
    "native_text_is_incomplete",
    "optional_import",
    "extract_file",
    "detect_kind",
    "dependency_report",
]

#: extension -> (kind, module name inside this package)
_EXTENSION_MAP: dict[str, tuple[str, str]] = {
    ".pdf": ("pdf", "pdf"),
    ".docx": ("docx", "office"),
    ".doc": ("doc", "office"),
    ".rtf": ("rtf", "office"),
    ".odt": ("odt", "office"),
    ".txt": ("text", "plaintext"),
    ".md": ("text", "plaintext"),
    ".log": ("text", "plaintext"),
    ".json": ("text", "plaintext"),
    ".htm": ("html", "plaintext"),
    ".html": ("html", "plaintext"),
    ".vtt": ("transcript", "plaintext"),
    ".srt": ("transcript", "plaintext"),
    ".eml": ("email", "mail"),
    ".msg": ("email", "mail"),
    ".mbox": ("email", "mail"),
    ".csv": ("spreadsheet", "sheet"),
    ".tsv": ("spreadsheet", "sheet"),
    ".xlsx": ("spreadsheet", "sheet"),
    ".xlsm": ("spreadsheet", "sheet"),
    ".xls": ("spreadsheet", "sheet"),
    ".png": ("image", "image"),
    ".jpg": ("image", "image"),
    ".jpeg": ("image", "image"),
    ".tif": ("image", "image"),
    ".tiff": ("image", "image"),
    ".bmp": ("image", "image"),
    ".heic": ("image", "image"),
    ".gif": ("image", "image"),
    ".zip": ("archive", "archive"),
    ".mp3": ("audio", "media"),
    ".m4a": ("audio", "media"),
    ".wav": ("audio", "media"),
    ".aac": ("audio", "media"),
    ".mp4": ("video", "media"),
    ".mov": ("video", "media"),
    ".m4v": ("video", "media"),
    ".avi": ("video", "media"),
    ".mkv": ("video", "media"),
}

_MAGIC_SIGNATURES: tuple[tuple[bytes, str, str], ...] = (
    (b"%PDF-", "pdf", "pdf"),
    (b"\x89PNG\r\n\x1a\n", "image", "image"),
    (b"\xff\xd8\xff", "image", "image"),
    (b"GIF8", "image", "image"),
)

MIME_BY_KIND = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
    "rtf": "application/rtf",
    "odt": "application/vnd.oasis.opendocument.text",
    "text": "text/plain",
    "html": "text/html",
    "transcript": "text/plain",
    "email": "message/rfc822",
    "spreadsheet": "application/vnd.ms-excel",
    "image": "image/*",
    "archive": "application/zip",
    "audio": "audio/*",
    "video": "video/*",
    "unknown": "application/octet-stream",
}


def detect_kind(path: Path) -> tuple[str, str | None]:
    """Return ``(kind, handler_module)`` for *path*.

    Extension wins when known; otherwise magic bytes are consulted. Unknown
    files fall back to a best-effort plain-text read rather than being dropped.
    """
    suffix = path.suffix.lower()
    if suffix in _EXTENSION_MAP:
        return _EXTENSION_MAP[suffix]

    try:
        with open(path, "rb") as handle:
            head = handle.read(16)
    except OSError:
        return ("unknown", None)

    for signature, kind, module in _MAGIC_SIGNATURES:
        if head.startswith(signature):
            return (kind, module)

    # DOCX/XLSX/ZIP all begin with PK; let the archive handler disambiguate.
    if head.startswith(b"PK\x03\x04"):
        return ("archive", "archive")

    return ("unknown", "plaintext")


def extract_file(path: Path, ctx: ExtractContext | None = None) -> ExtractionResult:
    """Extract text from *path*. Never raises for a recoverable problem."""
    ctx = ctx or ExtractContext()
    path = Path(path)

    if not path.exists():
        return ExtractionResult(error=f"file does not exist: {path}")
    if path.is_dir():
        return ExtractionResult(error=f"path is a directory: {path}")

    kind, module_name = detect_kind(path)
    if module_name is None:
        return ExtractionResult(method="none", metadata={"kind": kind},
                                error="no handler for this file type")

    try:
        module = importlib.import_module(f".{module_name}", __package__)
    except Exception as exc:  # pragma: no cover - import failure is environmental
        return ExtractionResult(metadata={"kind": kind},
                                error=f"handler {module_name} failed to load: {exc}")

    try:
        result = module.extract(path, ctx)
    except Exception as exc:
        # Fail loud but contained: the document is still ingested and indexed,
        # with the extraction failure recorded for review.
        return ExtractionResult(metadata={"kind": kind},
                                error=f"{type(exc).__name__}: {exc}")

    result.metadata.setdefault("kind", kind)
    result.metadata.setdefault("handler", module_name)
    return result


#: Optional libraries and what they unlock. Reported by the health check so a
#: degraded extraction path is always visible rather than silently assumed.
OPTIONAL_DEPENDENCIES = {
    "pypdf": "PDF native text extraction",
    "docx": "DOCX text extraction (python-docx)",
    "openpyxl": "XLSX spreadsheet extraction",
    "PIL": "image handling for OCR (Pillow)",
    "pytesseract": "OCR of scanned filings and images",
    "extract_msg": "Outlook .msg email extraction",
    "striprtf": "RTF text extraction",
}


def dependency_report() -> dict[str, dict[str, object]]:
    """Which optional extraction dependencies are present, and what is lost."""
    report: dict[str, dict[str, object]] = {}
    for module_name, purpose in OPTIONAL_DEPENDENCIES.items():
        present = optional_import(module_name) is not None
        report[module_name] = {"installed": present, "enables": purpose}
    return report
