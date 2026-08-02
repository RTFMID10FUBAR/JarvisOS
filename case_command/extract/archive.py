"""ZIP archive handling: in-memory member extraction, no disk writes.

Also disambiguates ZIP-based Office formats (.docx/.xlsx saved with a .zip
extension, or otherwise misidentified by magic bytes) by delegating to the
appropriate handler.
"""

from __future__ import annotations

import pathlib
import zipfile

from .base import (
    ExtractionResult,
    ExtractContext,
    optional_import,
    native_text_is_incomplete,
    read_bytes_readonly,
)

_MAX_MEMBER_COUNT = 2000


def _is_traversal_unsafe(name: str) -> bool:
    if name.startswith("/") or name.startswith("\\"):
        return True
    # Windows drive letters, e.g. "C:\..."
    if len(name) > 1 and name[1] == ":":
        return True
    parts = name.replace("\\", "/").split("/")
    return any(part == ".." for part in parts)


def _looks_like_docx_or_xlsx(names: list[str]) -> str | None:
    if "word/document.xml" in names:
        return "office"
    if "xl/workbook.xml" in names:
        return "sheet"
    return None


def extract(path: pathlib.Path, ctx: ExtractContext) -> ExtractionResult:
    result = ExtractionResult()

    try:
        size = path.stat().st_size
    except OSError as exc:
        result.error = f"could not stat file: {exc}"
        return result
    if size > ctx.max_bytes:
        result.method = "none"
        result.error = f"file is {size} bytes, over the {ctx.max_bytes}-byte extraction limit"
        return result

    try:
        zf = zipfile.ZipFile(str(path))
    except zipfile.BadZipFile as exc:
        result.method = "none"
        result.error = f"not a valid ZIP archive: {exc}"
        return result
    except Exception as exc:
        result.method = "none"
        result.error = f"could not open ZIP archive: {exc}"
        return result

    try:
        infos = zf.infolist()
        names = [info.filename for info in infos]

        # An Office document masquerading as/detected as a ZIP: delegate.
        delegate_kind = _looks_like_docx_or_xlsx(names)
        if delegate_kind == "office":
            from . import office

            zf.close()
            sub_result = ExtractionResult()
            office._extract_docx(path, ctx, sub_result)
            sub_result.metadata.setdefault("delegated_from", "archive")
            return sub_result
        if delegate_kind == "sheet":
            from . import sheet

            zf.close()
            sub_result = ExtractionResult()
            sheet._extract_xlsx(path, ctx, sub_result)
            sub_result.metadata.setdefault("delegated_from", "archive")
            return sub_result

        result.metadata["member_count_total"] = len(infos)

        if ctx.depth >= ctx.max_depth:
            manifest_lines = [f"{info.filename}\t{info.file_size} bytes" for info in infos]
            result.text = "\n".join(manifest_lines)
            result.method = "partial"
            result.warnings.append(
                f"max container nesting depth ({ctx.max_depth}) reached; listing "
                "members without reading their contents"
            )
            result.metadata["listed_only"] = True
            zf.close()
            return result

        manifest_lines: list[str] = []
        total_uncompressed = 0
        member_count = 0
        capped_by_count = False
        capped_by_size = False

        for info in infos:
            if info.is_dir():
                continue

            if _is_traversal_unsafe(info.filename):
                result.warnings.append(
                    f"rejected member with unsafe path (traversal/absolute): {info.filename!r}"
                )
                continue

            if member_count >= _MAX_MEMBER_COUNT:
                capped_by_count = True
                break

            if info.file_size > ctx.max_bytes:
                result.warnings.append(
                    f"skipped member over the byte limit: {info.filename!r} "
                    f"({info.file_size} bytes)"
                )
                manifest_lines.append(f"{info.filename}\t{info.file_size} bytes\t[skipped: too large]")
                continue

            if total_uncompressed + info.file_size > ctx.max_bytes:
                capped_by_size = True
                break

            try:
                data = zf.read(info)
            except Exception as exc:
                result.warnings.append(f"could not read member {info.filename!r}: {exc}")
                continue

            result.members.append((info.filename, data))
            manifest_lines.append(f"{info.filename}\t{info.file_size} bytes")
            total_uncompressed += info.file_size
            member_count += 1

        if capped_by_count:
            result.warnings.append(
                f"archive has more than {_MAX_MEMBER_COUNT} members; stopped reading "
                "after the cap to guard against zip bombs"
            )
        if capped_by_size:
            result.warnings.append(
                f"stopped reading members after total uncompressed size reached the "
                f"{ctx.max_bytes}-byte limit (zip bomb guard)"
            )

        result.text = "\n".join(manifest_lines)
        result.metadata["member_count_read"] = member_count
        result.metadata["total_uncompressed_bytes"] = total_uncompressed
        result.method = "native" if manifest_lines else "none"
        if not manifest_lines:
            result.error = "archive contained no readable members"
    finally:
        try:
            zf.close()
        except Exception:
            pass

    return result
