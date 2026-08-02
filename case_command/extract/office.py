"""Office document extraction: .docx, .doc, .rtf, .odt."""

from __future__ import annotations

import pathlib
import re
import string
import zipfile
from xml.etree import ElementTree

from .base import (
    ExtractionResult,
    ExtractContext,
    optional_import,
    native_text_is_incomplete,
    read_bytes_readonly,
)

_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_TEXT_NS = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"


def _docx_via_python_docx(raw: bytes, result: ExtractionResult) -> str | None:
    docx = optional_import("docx")
    if docx is None:
        return None
    import io

    try:
        document = docx.Document(io.BytesIO(raw))
    except Exception as exc:
        result.warnings.append(f"python-docx failed to open file: {exc}")
        return None

    parts: list[str] = []
    try:
        for section in document.sections:
            try:
                header = section.header
                if header is not None:
                    for para in header.paragraphs:
                        if para.text.strip():
                            parts.append(para.text)
            except Exception:
                pass
    except Exception:
        pass

    try:
        for para in document.paragraphs:
            parts.append(para.text)
    except Exception as exc:
        result.warnings.append(f"python-docx: paragraph read failed: {exc}")

    try:
        for table in document.tables:
            for row in table.rows:
                cells = [cell.text for cell in row.cells]
                if any(c.strip() for c in cells):
                    parts.append("\t".join(cells))
    except Exception as exc:
        result.warnings.append(f"python-docx: table read failed: {exc}")

    try:
        for section in document.sections:
            try:
                footer = section.footer
                if footer is not None:
                    for para in footer.paragraphs:
                        if para.text.strip():
                            parts.append(para.text)
            except Exception:
                pass
    except Exception:
        pass

    try:
        props = document.core_properties
        if props.title:
            result.metadata["title"] = props.title
        if props.author:
            result.metadata["author"] = props.author
        if props.created:
            result.metadata["creation_date"] = str(props.created)
        if props.modified:
            result.metadata["modified_date"] = str(props.modified)
    except Exception:
        pass

    return "\n".join(parts)


def _docx_stdlib_fallback(raw: bytes, result: ExtractionResult) -> str | None:
    """Zero-dependency fallback: .docx is a ZIP; parse word/document.xml directly."""
    import io

    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            try:
                xml_bytes = zf.read("word/document.xml")
            except KeyError:
                result.warnings.append("word/document.xml not found inside .docx package")
                return None
    except zipfile.BadZipFile as exc:
        result.warnings.append(f".docx is not a valid ZIP package: {exc}")
        return None

    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as exc:
        result.warnings.append(f"could not parse word/document.xml: {exc}")
        return None

    paragraphs: list[str] = []
    for para_el in root.iter(f"{_W_NS}p"):
        texts = [node.text or "" for node in para_el.iter(f"{_W_NS}t")]
        paragraphs.append("".join(texts))
    return "\n".join(paragraphs)


def _extract_docx(path: pathlib.Path, ctx: ExtractContext, result: ExtractionResult) -> None:
    try:
        raw = read_bytes_readonly(path, ctx.max_bytes)
    except Exception as exc:
        result.error = f"could not read file: {exc}"
        return

    text = _docx_via_python_docx(raw, result)
    if text is not None:
        result.text = text
        result.method = "native"
        result.confidence = 1.0
        return

    result.warnings.append(
        "python-docx not installed; used stdlib ZIP/XML fallback "
        "(pip install python-docx for tables/headers/footers and richer metadata)"
    )
    text = _docx_stdlib_fallback(raw, result)
    if text is None:
        result.method = "none"
        result.error = "could not extract text from .docx via any available method"
        return

    result.text = text
    result.method = "native" if text.strip() else "partial"
    result.confidence = 1.0 if text.strip() else 0.5


def _extract_odt(path: pathlib.Path, ctx: ExtractContext, result: ExtractionResult) -> None:
    try:
        raw = read_bytes_readonly(path, ctx.max_bytes)
    except Exception as exc:
        result.error = f"could not read file: {exc}"
        return

    import io

    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            try:
                xml_bytes = zf.read("content.xml")
            except KeyError:
                result.method = "none"
                result.error = "content.xml not found inside .odt package"
                return
    except zipfile.BadZipFile as exc:
        result.method = "none"
        result.error = f".odt is not a valid ZIP package: {exc}"
        return

    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as exc:
        result.method = "none"
        result.error = f"could not parse content.xml: {exc}"
        return

    paragraphs: list[str] = []
    for tag in ("p", "h"):
        for el in root.iter(f"{_TEXT_NS}{tag}"):
            text = "".join(el.itertext())
            paragraphs.append(text)

    result.text = "\n".join(paragraphs)
    result.method = "native" if result.text.strip() else "partial"
    result.confidence = 1.0 if result.text.strip() else 0.5
    if not result.text.strip():
        result.warnings.append("no text nodes found in content.xml")


_CONTROL_WORD_RE = re.compile(r"\\[a-zA-Z]+-?\d* ?")
_HEX_ESCAPE_RE = re.compile(r"\\'[0-9a-fA-F]{2}")
_BRACE_RE = re.compile(r"[{}]")


def _rtf_stdlib_strip(raw_text: str) -> str:
    """Very simple RTF control-word stripper. Best-effort only."""
    text = raw_text
    # Drop \par and \line control words down to newlines before generic stripping.
    text = re.sub(r"\\par[d]?\b", "\n", text)
    text = re.sub(r"\\line\b", "\n", text)
    text = _HEX_ESCAPE_RE.sub("", text)
    text = _CONTROL_WORD_RE.sub("", text)
    text = _BRACE_RE.sub("", text)
    text = text.replace("\\\\", "\\").replace("\\{", "{").replace("\\}", "}")
    # Collapse excess whitespace left by removed control words.
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_rtf(path: pathlib.Path, ctx: ExtractContext, result: ExtractionResult) -> None:
    try:
        raw = read_bytes_readonly(path, ctx.max_bytes)
    except Exception as exc:
        result.error = f"could not read file: {exc}"
        return

    try:
        raw_text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raw_text = raw.decode("cp1252", errors="replace")

    striprtf = optional_import("striprtf")
    if striprtf is not None:
        try:
            from striprtf.striprtf import rtf_to_text

            result.text = rtf_to_text(raw_text)
            result.method = "native"
            result.confidence = 1.0
            return
        except Exception as exc:
            result.warnings.append(f"striprtf failed, falling back to stdlib stripper: {exc}")

    result.warnings.append(
        "striprtf not installed; used a best-effort stdlib control-word stripper "
        "(pip install striprtf for reliable RTF extraction)"
    )
    result.text = _rtf_stdlib_strip(raw_text)
    result.method = "partial"
    result.confidence = 0.6 if result.text.strip() else 0.0
    if not result.text.strip():
        result.error = "stdlib RTF stripper produced no text"
        result.method = "none"


def _extract_doc(path: pathlib.Path, ctx: ExtractContext, result: ExtractionResult) -> None:
    try:
        raw = read_bytes_readonly(path, ctx.max_bytes)
    except Exception as exc:
        result.error = f"could not read file: {exc}"
        return

    # Legacy binary .doc (OLE2 Compound File) has no reliable stdlib parser.
    # Best-effort salvage: pull runs of printable ASCII text out of the binary blob.
    printable = set(bytes(string.printable, "ascii"))
    chunks: list[bytes] = []
    current: list[int] = []
    for byte in raw:
        if byte in printable and byte not in (0x0b, 0x0c):
            current.append(byte)
        else:
            if len(current) >= 4:
                chunks.append(bytes(current))
            current = []
    if len(current) >= 4:
        chunks.append(bytes(current))

    salvaged = " ".join(chunk.decode("ascii", errors="ignore") for chunk in chunks)
    salvaged = re.sub(r"\s{2,}", " ", salvaged).strip()

    result.metadata["salvage_attempted"] = True
    result.error = (
        "legacy binary .doc format has no reliable pure-Python extraction path; "
        "install antiword (system package) or the textract library for real text "
        "(e.g. apt install antiword, or pip install textract)"
    )
    if len(salvaged) > 200:
        result.text = salvaged
        result.method = "partial"
        result.confidence = 0.2
        result.warnings.append(
            "text is a best-effort printable-ASCII salvage from the binary .doc; "
            "expect noise, missing words, and lost formatting"
        )
    else:
        result.method = "none"


def extract(path: pathlib.Path, ctx: ExtractContext) -> ExtractionResult:
    result = ExtractionResult()
    suffix = path.suffix.lower()

    if suffix == ".docx":
        _extract_docx(path, ctx, result)
    elif suffix == ".odt":
        _extract_odt(path, ctx, result)
    elif suffix == ".rtf":
        _extract_rtf(path, ctx, result)
    elif suffix == ".doc":
        _extract_doc(path, ctx, result)
    else:
        result.method = "none"
        result.error = f"unsupported office extension: {suffix}"

    return result
