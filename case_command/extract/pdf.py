"""PDF text extraction: native text via pypdf, OCR fallback for scanned pages."""

from __future__ import annotations

import pathlib

from .base import (
    ExtractionResult,
    ExtractContext,
    optional_import,
    native_text_is_incomplete,
    read_bytes_readonly,
)


def _meta_str(value) -> str | None:
    if value is None:
        return None
    try:
        return str(value)
    except Exception:
        return None


def _native_extract(path: pathlib.Path, ctx: ExtractContext, result: ExtractionResult):
    """Attempt native text extraction with pypdf. Returns (pages, reader_or_None)."""
    pypdf = optional_import("pypdf")
    if pypdf is None:
        result.warnings.append(
            "pypdf is not installed; native PDF text extraction unavailable "
            "(pip install pypdf)"
        )
        return None, None

    try:
        raw = read_bytes_readonly(path, ctx.max_bytes)
    except Exception as exc:
        result.error = f"could not read file: {exc}"
        return None, None

    import io

    try:
        reader = pypdf.PdfReader(io.BytesIO(raw))
    except Exception as exc:
        result.warnings.append(f"pypdf failed to open file: {exc}")
        return None, None

    if getattr(reader, "is_encrypted", False):
        # Attempt an empty-password decrypt (common for "owner-only" restricted PDFs);
        # if that fails, report the encryption clearly rather than silently returning nothing.
        try:
            decrypt_result = reader.decrypt("")
        except Exception:
            decrypt_result = 0
        if not decrypt_result:
            result.error = (
                "PDF is encrypted/password-protected; cannot extract text without "
                "the password"
            )
            result.metadata["encrypted"] = True
            return None, None
        result.warnings.append("PDF was encrypted; decrypted with empty password")

    try:
        info = reader.metadata
        if info:
            title = _meta_str(getattr(info, "title", None))
            author = _meta_str(getattr(info, "author", None))
            creation_date = _meta_str(getattr(info, "creation_date", None))
            if title:
                result.metadata["title"] = title
            if author:
                result.metadata["author"] = author
            if creation_date:
                result.metadata["creation_date"] = creation_date
    except Exception as exc:
        result.warnings.append(f"could not read PDF metadata: {exc}")

    pages: list[str] = []
    for idx, page in enumerate(reader.pages):
        try:
            pages.append(page.extract_text() or "")
        except Exception as exc:
            pages.append("")
            result.warnings.append(f"page {idx + 1}: native text extraction failed: {exc}")

    return pages, reader


def _ocr_via_pdf2image(path: pathlib.Path, ctx: ExtractContext, result: ExtractionResult):
    pdf2image = optional_import("pdf2image")
    pytesseract = optional_import("pytesseract")
    if pdf2image is None or pytesseract is None:
        return None
    try:
        images = pdf2image.convert_from_path(str(path))
    except Exception as exc:
        result.warnings.append(f"pdf2image failed to render pages: {exc}")
        return None

    ocr_pages: list[str] = []
    confidences: list[float] = []
    for idx, image in enumerate(images):
        try:
            page_text = pytesseract.image_to_string(image, lang=ctx.ocr_language)
            ocr_pages.append(page_text)
            try:
                data = pytesseract.image_to_data(
                    image, lang=ctx.ocr_language, output_type=pytesseract.Output.DICT
                )
                confs = [float(c) for c in data.get("conf", []) if float(c) > 0]
                if confs:
                    confidences.append(sum(confs) / len(confs) / 100.0)
            except Exception:
                pass
        except Exception as exc:
            ocr_pages.append("")
            result.warnings.append(f"page {idx + 1}: OCR failed: {exc}")
    return ocr_pages, (sum(confidences) / len(confidences) if confidences else 0.5)


def _ocr_via_fitz(path: pathlib.Path, ctx: ExtractContext, result: ExtractionResult):
    fitz = optional_import("fitz")
    pytesseract = optional_import("pytesseract")
    PIL = optional_import("PIL.Image")
    if fitz is None or pytesseract is None or PIL is None:
        return None
    try:
        doc = fitz.open(str(path))
    except Exception as exc:
        result.warnings.append(f"fitz (PyMuPDF) failed to open file: {exc}")
        return None

    ocr_pages: list[str] = []
    confidences: list[float] = []
    try:
        for idx, page in enumerate(doc):
            try:
                pix = page.get_pixmap()
                img = PIL.frombytes("RGB", (pix.width, pix.height), pix.samples)
                page_text = pytesseract.image_to_string(img, lang=ctx.ocr_language)
                ocr_pages.append(page_text)
                try:
                    data = pytesseract.image_to_data(
                        img, lang=ctx.ocr_language, output_type=pytesseract.Output.DICT
                    )
                    confs = [float(c) for c in data.get("conf", []) if float(c) > 0]
                    if confs:
                        confidences.append(sum(confs) / len(confs) / 100.0)
                except Exception:
                    pass
            except Exception as exc:
                ocr_pages.append("")
                result.warnings.append(f"page {idx + 1}: OCR via fitz failed: {exc}")
    finally:
        try:
            doc.close()
        except Exception:
            pass
    return ocr_pages, (sum(confidences) / len(confidences) if confidences else 0.5)


def extract(path: pathlib.Path, ctx: ExtractContext) -> ExtractionResult:
    result = ExtractionResult()

    native_pages, reader = _native_extract(path, ctx, result)
    if result.error:
        return result

    if native_pages is not None:
        result.page_count = len(native_pages)
        result.pages = list(native_pages)
        result.text = "\n\n".join(native_pages)
        result.method = "native"
        result.confidence = 1.0

    needs_ocr = native_pages is None or native_text_is_incomplete(
        result.text, result.page_count or (len(native_pages) if native_pages else 1)
    )

    if needs_ocr and ctx.allow_ocr:
        ocr_out = _ocr_via_pdf2image(path, ctx, result)
        if ocr_out is None:
            ocr_out = _ocr_via_fitz(path, ctx, result)

        if ocr_out is None:
            if native_pages is None:
                result.method = "none"
                result.error = (
                    "no PDF text extraction path available: install pypdf for native "
                    "text, and pdf2image+pytesseract (or PyMuPDF/fitz+pytesseract) for "
                    "OCR of scanned pages (pip install pypdf pdf2image pytesseract "
                    "or pip install pymupdf pytesseract)"
                )
            else:
                result.warnings.append(
                    "native text looked incomplete but no OCR backend is installed "
                    "(pip install pdf2image pytesseract, or pymupdf pytesseract); "
                    "returning native text as-is"
                )
        else:
            ocr_pages, avg_conf = ocr_out
            if native_pages is None:
                # Pure OCR path.
                result.pages = ocr_pages
                result.page_count = len(ocr_pages)
                result.text = "\n\n".join(ocr_pages)
                result.method = "ocr"
                result.confidence = round(avg_conf, 3)
            else:
                # Merge: use OCR text on pages where native text was thin.
                merged_pages: list[str] = []
                mixed = False
                per_page_min = 40
                for idx, native_page_text in enumerate(native_pages):
                    ocr_page_text = ocr_pages[idx] if idx < len(ocr_pages) else ""
                    if len(native_page_text.strip()) < per_page_min and ocr_page_text.strip():
                        merged_pages.append(ocr_page_text)
                        mixed = True
                    else:
                        merged_pages.append(native_page_text)
                result.pages = merged_pages
                result.text = "\n\n".join(merged_pages)
                if mixed:
                    result.method = "native+ocr"
                    result.confidence = round(avg_conf, 3)
                    result.warnings.append(
                        "some pages had thin native text and were replaced with OCR output"
                    )
                # else: native text was fine on every page; keep method=native, confidence=1.0

    if native_pages is not None:
        result.metadata.setdefault("page_count", len(native_pages))
    elif result.pages:
        result.metadata.setdefault("page_count", len(result.pages))

    if not result.text.strip() and not result.error:
        result.method = "none"
        result.error = "no extractable text found in PDF (native or OCR)"

    return result
