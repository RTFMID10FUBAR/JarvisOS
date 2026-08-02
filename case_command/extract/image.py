"""Image handling: metadata always, OCR when Pillow + pytesseract are available."""

from __future__ import annotations

import pathlib
import struct

from .base import (
    ExtractionResult,
    ExtractContext,
    optional_import,
    native_text_is_incomplete,
    read_bytes_readonly,
)


def _dims_from_png(raw: bytes) -> tuple[int, int] | None:
    if len(raw) < 24 or raw[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    width, height = struct.unpack(">II", raw[16:24])
    return width, height


def _dims_from_jpeg(raw: bytes) -> tuple[int, int] | None:
    if len(raw) < 4 or raw[:2] != b"\xff\xd8":
        return None
    pos = 2
    length = len(raw)
    sof_markers = {
        0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
        0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
    }
    while pos < length - 1:
        if raw[pos] != 0xFF:
            pos += 1
            continue
        marker = raw[pos + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            pos += 2
            continue
        if pos + 4 > length:
            break
        seg_len = struct.unpack(">H", raw[pos + 2:pos + 4])[0]
        if marker in sof_markers:
            if pos + 9 > length:
                break
            height, width = struct.unpack(">HH", raw[pos + 5:pos + 9])
            return width, height
        pos += 2 + seg_len
    return None


def _dims_from_gif(raw: bytes) -> tuple[int, int] | None:
    if len(raw) < 10 or raw[:3] != b"GIF":
        return None
    width, height = struct.unpack("<HH", raw[6:10])
    return width, height


def _dims_from_bmp(raw: bytes) -> tuple[int, int] | None:
    if len(raw) < 26 or raw[:2] != b"BM":
        return None
    width, height = struct.unpack("<ii", raw[18:26])
    return width, abs(height)


def _struct_dims(raw: bytes) -> tuple[int, int] | None:
    for probe in (_dims_from_png, _dims_from_jpeg, _dims_from_gif, _dims_from_bmp):
        try:
            dims = probe(raw)
        except Exception:
            dims = None
        if dims:
            return dims
    return None


def _metadata_via_pil(raw: bytes, result: ExtractionResult) -> bool:
    PIL_Image = optional_import("PIL.Image")
    if PIL_Image is None:
        return False
    import io

    try:
        with PIL_Image.open(io.BytesIO(raw)) as img:
            result.metadata["width"] = img.width
            result.metadata["height"] = img.height
            result.metadata["mode"] = img.mode
            result.metadata["format"] = img.format
            try:
                exif = img.getexif()
                if exif:
                    # 0x9003 = DateTimeOriginal
                    date_original = exif.get(0x9003) or exif.get(36867)
                    if date_original:
                        result.metadata["exif_date_original"] = str(date_original)
                    make = exif.get(0x010F)
                    model = exif.get(0x0110)
                    if make:
                        result.metadata["exif_make"] = str(make)
                    if model:
                        result.metadata["exif_model"] = str(model)
            except Exception as exc:
                result.warnings.append(f"could not read EXIF data: {exc}")
    except Exception as exc:
        result.warnings.append(f"Pillow failed to open image: {exc}")
        return False
    return True


def _ocr_via_pytesseract(raw: bytes, ctx: ExtractContext, result: ExtractionResult) -> bool:
    PIL_Image = optional_import("PIL.Image")
    pytesseract = optional_import("pytesseract")
    if PIL_Image is None or pytesseract is None:
        missing = []
        if PIL_Image is None:
            missing.append("Pillow")
        if pytesseract is None:
            missing.append("pytesseract")
        result.warnings.append(
            f"OCR unavailable, missing: {', '.join(missing)} "
            f"(pip install {' '.join(m.lower() for m in missing)}); "
            "image was indexed without text"
        )
        return False

    import io

    try:
        with PIL_Image.open(io.BytesIO(raw)) as img:
            text = pytesseract.image_to_string(img, lang=ctx.ocr_language)
            confidence = 0.5
            try:
                data = pytesseract.image_to_data(
                    img, lang=ctx.ocr_language, output_type=pytesseract.Output.DICT
                )
                confs = [float(c) for c in data.get("conf", []) if float(c) > 0]
                if confs:
                    confidence = sum(confs) / len(confs) / 100.0
            except Exception:
                pass
    except Exception as exc:
        result.warnings.append(f"pytesseract OCR failed: {exc}")
        return False

    result.text = text
    result.method = "ocr"
    result.confidence = round(confidence, 3)
    return True


def extract(path: pathlib.Path, ctx: ExtractContext) -> ExtractionResult:
    result = ExtractionResult()

    try:
        raw = read_bytes_readonly(path, ctx.max_bytes)
    except Exception as exc:
        result.error = f"could not read file: {exc}"
        return result

    result.metadata["byte_count"] = len(raw)

    got_pil_meta = _metadata_via_pil(raw, result)
    if not got_pil_meta:
        dims = _struct_dims(raw)
        if dims:
            result.metadata["width"], result.metadata["height"] = dims
        else:
            result.warnings.append(
                "Pillow not installed and could not parse dimensions from raw bytes "
                "(pip install Pillow for full image metadata)"
            )

    if ctx.allow_ocr:
        ocr_ok = _ocr_via_pytesseract(raw, ctx, result)
        if not ocr_ok:
            result.method = "none"
    else:
        result.method = "none"
        result.warnings.append("OCR disabled for this extraction context")

    # Metadata-only outcomes are expected behavior, not an error condition.
    return result
