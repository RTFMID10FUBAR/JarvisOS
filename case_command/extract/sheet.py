"""Spreadsheet extraction: .csv/.tsv via stdlib csv, .xlsx/.xlsm via openpyxl, .xls unsupported."""

from __future__ import annotations

import csv
import io
import pathlib

from .base import (
    ExtractionResult,
    ExtractContext,
    optional_import,
    native_text_is_incomplete,
    read_bytes_readonly,
)


def _sniff_delimiter(sample: str, suffix: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        return dialect.delimiter
    except csv.Error:
        return "\t" if suffix == ".tsv" else ","


def _extract_delimited(path: pathlib.Path, ctx: ExtractContext, result: ExtractionResult) -> None:
    try:
        raw = read_bytes_readonly(path, ctx.max_bytes)
    except Exception as exc:
        result.error = f"could not read file: {exc}"
        return

    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            encoding = enc
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("latin-1", errors="replace")
        encoding = "latin-1 (replace)"

    suffix = path.suffix.lower()
    sample = text[:4096]
    delimiter = _sniff_delimiter(sample, suffix)

    lines_out: list[str] = []
    row_count = 0
    truncated = False
    budget = ctx.max_bytes
    used = 0
    try:
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        for row in reader:
            row_count += 1
            line = "\t".join(row)
            line_bytes = len(line.encode("utf-8")) + 1
            if used + line_bytes > budget:
                truncated = True
                break
            lines_out.append(line)
            used += line_bytes
    except Exception as exc:
        result.warnings.append(f"csv parsing hit an error partway through: {exc}")

    if truncated:
        result.warnings.append(
            f"output truncated at ~{budget} bytes; source has more rows"
        )

    result.text = "\n".join(lines_out)
    result.method = "native" if lines_out else "none"
    result.confidence = 1.0 if lines_out else None
    result.metadata["encoding"] = encoding
    result.metadata["delimiter"] = delimiter
    result.metadata["row_count"] = row_count
    if not lines_out:
        result.error = "no rows could be parsed from delimited file"


def _extract_xlsx(path: pathlib.Path, ctx: ExtractContext, result: ExtractionResult) -> None:
    openpyxl = optional_import("openpyxl")
    if openpyxl is None:
        result.method = "none"
        result.error = (
            "openpyxl is not installed; cannot read .xlsx/.xlsm files "
            "(pip install openpyxl)"
        )
        return

    try:
        size = path.stat().st_size
    except OSError as exc:
        result.error = f"could not stat file: {exc}"
        return
    if size > ctx.max_bytes:
        result.method = "none"
        result.error = f"file is {size} bytes, over the {ctx.max_bytes}-byte extraction limit"
        return

    try:
        workbook = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    except Exception as exc:
        result.method = "none"
        result.error = f"openpyxl failed to open workbook: {exc}"
        return

    result.metadata["sheet_names"] = list(workbook.sheetnames)

    pages: list[str] = []
    budget = ctx.max_bytes
    used = 0
    truncated = False
    try:
        for sheet_name in workbook.sheetnames:
            if truncated:
                break
            try:
                sheet = workbook[sheet_name]
            except Exception as exc:
                result.warnings.append(f"sheet {sheet_name!r}: could not open: {exc}")
                continue

            sheet_lines: list[str] = [f"# {sheet_name}"]
            try:
                for row in sheet.iter_rows(values_only=True):
                    cells = ["" if v is None else str(v) for v in row]
                    line = "\t".join(cells)
                    line_bytes = len(line.encode("utf-8")) + 1
                    if used + line_bytes > budget:
                        truncated = True
                        result.warnings.append(
                            f"output truncated at ~{budget} bytes while reading sheet "
                            f"{sheet_name!r}"
                        )
                        break
                    sheet_lines.append(line)
                    used += line_bytes
            except Exception as exc:
                result.warnings.append(f"sheet {sheet_name!r}: row read failed: {exc}")

            pages.append("\n".join(sheet_lines))
    finally:
        try:
            workbook.close()
        except Exception:
            pass

    result.pages = pages
    result.page_count = len(pages)
    result.text = "\n\n".join(pages)
    result.method = "native" if any(p.strip() for p in pages) else "partial"
    result.confidence = 1.0
    if not any(p.strip() for p in pages):
        result.warnings.append("workbook opened but no cell data was found")


def _extract_xls(path: pathlib.Path, ctx: ExtractContext, result: ExtractionResult) -> None:
    xlrd = optional_import("xlrd")
    if xlrd is None:
        result.method = "none"
        result.error = (
            "xlrd is not installed; cannot read legacy .xls files "
            "(pip install xlrd)"
        )
        return

    try:
        raw = read_bytes_readonly(path, ctx.max_bytes)
    except Exception as exc:
        result.error = f"could not read file: {exc}"
        return

    try:
        book = xlrd.open_workbook(file_contents=raw)
    except Exception as exc:
        result.method = "none"
        result.error = f"xlrd failed to open workbook: {exc}"
        return

    result.metadata["sheet_names"] = book.sheet_names()
    pages: list[str] = []
    for sheet in book.sheets():
        lines = [f"# {sheet.name}"]
        for row_idx in range(sheet.nrows):
            row = sheet.row_values(row_idx)
            lines.append("\t".join(str(v) for v in row))
        pages.append("\n".join(lines))

    result.pages = pages
    result.page_count = len(pages)
    result.text = "\n\n".join(pages)
    result.method = "native"
    result.confidence = 1.0


def extract(path: pathlib.Path, ctx: ExtractContext) -> ExtractionResult:
    result = ExtractionResult()
    suffix = path.suffix.lower()

    if suffix in (".csv", ".tsv"):
        _extract_delimited(path, ctx, result)
    elif suffix in (".xlsx", ".xlsm"):
        _extract_xlsx(path, ctx, result)
    elif suffix == ".xls":
        _extract_xls(path, ctx, result)
    else:
        result.method = "none"
        result.error = f"unsupported spreadsheet extension: {suffix}"

    return result
