"""Email extraction: .eml, .mbox (stdlib), .msg (optional extract_msg)."""

from __future__ import annotations

import mailbox
import pathlib
import tempfile
from email import policy
from email.parser import BytesParser
from email.message import Message

from .base import (
    ExtractionResult,
    ExtractContext,
    optional_import,
    native_text_is_incomplete,
    read_bytes_readonly,
)
from .plaintext import _strip_html

_HEADER_FIELDS = ("From", "To", "Cc", "Bcc", "Date", "Subject", "Message-ID", "Reply-To")


def _header_block(msg: Message) -> str:
    lines = []
    for field in _HEADER_FIELDS:
        value = msg.get(field)
        if value:
            lines.append(f"{field}: {value}")
    return "\n".join(lines)


def _body_text(msg: Message, warnings: list[str]) -> str:
    """Prefer text/plain; fall back to stripped text/html."""
    plain_parts: list[str] = []
    html_parts: list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            if part.is_multipart():
                continue
            content_type = part.get_content_type()
            disposition = (part.get_content_disposition() or "").lower()
            if disposition == "attachment":
                continue
            try:
                if content_type == "text/plain":
                    plain_parts.append(part.get_content())
                elif content_type == "text/html":
                    html_parts.append(part.get_content())
            except Exception as exc:
                warnings.append(f"could not decode a message part ({content_type}): {exc}")
    else:
        content_type = msg.get_content_type()
        try:
            if content_type == "text/html":
                html_parts.append(msg.get_content())
            else:
                plain_parts.append(msg.get_content())
        except Exception as exc:
            warnings.append(f"could not decode message body: {exc}")

    if plain_parts:
        return "\n\n".join(p if isinstance(p, str) else str(p) for p in plain_parts)
    if html_parts:
        return "\n\n".join(_strip_html(h if isinstance(h, str) else str(h)) for h in html_parts)
    return ""


def _collect_attachments(msg: Message, result: ExtractionResult) -> None:
    if not msg.is_multipart():
        return
    for part in msg.walk():
        if part.is_multipart():
            continue
        disposition = (part.get_content_disposition() or "").lower()
        filename = part.get_filename()
        is_attachment = disposition == "attachment" or (
            disposition != "inline" and filename and part.get_content_maintype() != "text"
        )
        if not is_attachment or not filename:
            continue
        try:
            payload = part.get_payload(decode=True)
        except Exception as exc:
            result.warnings.append(f"could not decode attachment {filename!r}: {exc}")
            continue
        if payload is None:
            continue
        result.members.append((filename, payload))


def _extract_eml(path: pathlib.Path, ctx: ExtractContext, result: ExtractionResult) -> None:
    try:
        raw = read_bytes_readonly(path, ctx.max_bytes)
    except Exception as exc:
        result.error = f"could not read file: {exc}"
        return

    try:
        msg = BytesParser(policy=policy.default).parsebytes(raw)
    except Exception as exc:
        result.method = "none"
        result.error = f"could not parse .eml message: {exc}"
        return

    for field in _HEADER_FIELDS:
        value = msg.get(field)
        if value:
            result.metadata[field.lower().replace("-", "_")] = str(value)

    body = _body_text(msg, result.warnings)
    result.text = _header_block(msg) + "\n\n" + body
    result.method = "native"
    result.confidence = 1.0

    try:
        _collect_attachments(msg, result)
    except Exception as exc:
        result.warnings.append(f"attachment collection failed: {exc}")

    if not body.strip():
        result.warnings.append("message has headers but no readable body text")


def _extract_mbox(path: pathlib.Path, ctx: ExtractContext, result: ExtractionResult) -> None:
    try:
        size = path.stat().st_size
    except OSError as exc:
        result.error = f"could not stat file: {exc}"
        return
    if size > ctx.max_bytes:
        result.method = "none"
        result.error = f"file is {size} bytes, over the {ctx.max_bytes}-byte extraction limit"
        return

    # mailbox.mbox requires a real path; it opens read-only here and is never
    # asked to save/flush, so the source file is not modified. A custom factory
    # yields policy.default EmailMessage objects so the same body/attachment
    # helpers used for .eml can be reused.
    def _factory(fp):
        return BytesParser(policy=policy.default).parse(fp)

    try:
        box = mailbox.mbox(str(path), factory=_factory, create=False)
    except Exception as exc:
        result.method = "none"
        result.error = f"could not open .mbox file: {exc}"
        return

    messages_text: list[str] = []
    message_count = 0
    try:
        for i, msg in enumerate(box):
            message_count += 1
            try:
                header_block = _header_block(msg)
                body = _body_text(msg, result.warnings)
                messages_text.append(f"--- message {i + 1} ---\n{header_block}\n\n{body}")
                _collect_attachments(msg, result)
            except Exception as exc:
                result.warnings.append(f"message {i + 1}: extraction failed: {exc}")
    finally:
        try:
            box.close()
        except Exception:
            pass

    result.metadata["message_count"] = message_count
    result.pages = messages_text
    result.page_count = len(messages_text)
    result.text = "\n\n".join(messages_text)
    result.method = "native" if messages_text else "none"
    result.confidence = 1.0 if messages_text else None
    if not messages_text:
        result.error = "no messages could be read from .mbox file"


def _extract_msg(path: pathlib.Path, ctx: ExtractContext, result: ExtractionResult) -> None:
    extract_msg = optional_import("extract_msg")
    if extract_msg is None:
        result.method = "none"
        result.error = (
            "extract_msg is not installed; cannot read Outlook .msg files "
            "(pip install extract-msg)"
        )
        return

    try:
        msg = extract_msg.Message(str(path))
    except Exception as exc:
        result.method = "none"
        result.error = f"extract_msg failed to open .msg file: {exc}"
        return

    try:
        for field, attr in (
            ("From", "sender"), ("To", "to"), ("Cc", "cc"),
            ("Date", "date"), ("Subject", "subject"),
        ):
            value = getattr(msg, attr, None)
            if value:
                result.metadata[field.lower()] = str(value)

        header_lines = [f"{k}: {v}" for k, v in result.metadata.items() if k in
                         ("from", "to", "cc", "date", "subject")]
        body = msg.body or ""
        result.text = "\n".join(header_lines) + "\n\n" + body
        result.method = "native"
        result.confidence = 1.0

        try:
            for attachment in getattr(msg, "attachments", []) or []:
                filename = getattr(attachment, "longFilename", None) or getattr(
                    attachment, "shortFilename", None
                ) or "attachment"
                data = getattr(attachment, "data", None)
                if data:
                    result.members.append((filename, data))
        except Exception as exc:
            result.warnings.append(f"attachment collection failed: {exc}")
    except Exception as exc:
        result.method = "none"
        result.error = f"could not extract content from .msg file: {exc}"
    finally:
        try:
            msg.close()
        except Exception:
            pass


def extract(path: pathlib.Path, ctx: ExtractContext) -> ExtractionResult:
    result = ExtractionResult()
    suffix = path.suffix.lower()

    if suffix == ".eml":
        _extract_eml(path, ctx, result)
    elif suffix == ".mbox":
        _extract_mbox(path, ctx, result)
    elif suffix == ".msg":
        _extract_msg(path, ctx, result)
    else:
        result.method = "none"
        result.error = f"unsupported mail extension: {suffix}"

    return result
