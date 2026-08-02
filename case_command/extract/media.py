"""Audio/video container metadata only. No transcription is attempted here."""

from __future__ import annotations

import pathlib
import struct
import wave

from .base import (
    ExtractionResult,
    ExtractContext,
    optional_import,
    native_text_is_incomplete,
    read_bytes_readonly,
)

_NO_TRANSCRIPT_WARNING = (
    "no transcript was generated; audio/video content requires a separately "
    "supplied transcript document to be text-searchable"
)


def _wav_metadata(path: pathlib.Path, result: ExtractionResult) -> None:
    try:
        with wave.open(str(path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            duration = frames / rate if rate else None
            result.metadata["channels"] = channels
            result.metadata["sample_rate_hz"] = rate
            result.metadata["sample_width_bytes"] = sampwidth
            result.metadata["frame_count"] = frames
            if duration is not None:
                result.metadata["duration_seconds"] = round(duration, 3)
    except Exception as exc:
        result.warnings.append(f"could not read WAV header: {exc}")


def _mp4_mvhd_metadata(path: pathlib.Path, result: ExtractionResult) -> None:
    """Best-effort parse of the mvhd atom for duration/timescale."""
    try:
        with open(path, "rb") as f:
            data = f.read(min(path.stat().st_size, 8 * 1024 * 1024))
    except OSError as exc:
        result.warnings.append(f"could not read file for atom scan: {exc}")
        return

    idx = data.find(b"mvhd")
    if idx == -1 or idx < 4:
        result.warnings.append(
            "mvhd atom not found within the scanned header region; reporting file "
            "size only"
        )
        return

    try:
        # 'mvhd' tag is preceded by 4-byte atom size; version/flags follow the tag.
        pos = idx + 4
        version = data[pos]
        if version == 1:
            # 64-bit variant: creation(8) modification(8) timescale(4) duration(8)
            timescale = struct.unpack(">I", data[pos + 17:pos + 21])[0]
            duration_units = struct.unpack(">Q", data[pos + 21:pos + 29])[0]
        else:
            # 32-bit variant: creation(4) modification(4) timescale(4) duration(4)
            timescale = struct.unpack(">I", data[pos + 13:pos + 17])[0]
            duration_units = struct.unpack(">I", data[pos + 17:pos + 21])[0]
        if timescale:
            result.metadata["timescale"] = timescale
            result.metadata["duration_seconds"] = round(duration_units / timescale, 3)
    except (struct.error, IndexError) as exc:
        result.warnings.append(f"could not parse mvhd atom: {exc}")


def _mp3_id3_metadata(path: pathlib.Path, result: ExtractionResult) -> None:
    try:
        with open(path, "rb") as f:
            header = f.read(10)
    except OSError as exc:
        result.warnings.append(f"could not read file header: {exc}")
        return

    if len(header) < 10 or header[:3] != b"ID3":
        result.warnings.append("no ID3v2 header found at start of file")
        return

    major_version = header[3]
    # Size is a 28-bit synchsafe integer across bytes 6-9.
    size_bytes = header[6:10]
    size = 0
    for b in size_bytes:
        size = (size << 7) | (b & 0x7F)

    result.metadata["id3_version"] = f"2.{major_version}"
    result.metadata["id3_tag_size_bytes"] = size

    # Best-effort: scan for common text frames (TIT2=title, TPE1=artist, TALB=album)
    # without a full frame parser.
    try:
        with open(path, "rb") as f:
            tag_data = f.read(min(10 + size, path.stat().st_size))
        frame_map = {b"TIT2": "title", b"TPE1": "artist", b"TALB": "album"}
        for frame_id, key in frame_map.items():
            idx = tag_data.find(frame_id)
            if idx == -1:
                continue
            try:
                frame_size = struct.unpack(">I", tag_data[idx + 4:idx + 8])[0]
                frame_body = tag_data[idx + 10:idx + 10 + frame_size]
                # First byte is text encoding; strip it and null padding.
                text = frame_body[1:].split(b"\x00")[0]
                decoded = text.decode("utf-8", errors="ignore") or text.decode(
                    "latin-1", errors="ignore"
                )
                if decoded.strip():
                    result.metadata[key] = decoded.strip()
            except Exception:
                continue
    except Exception as exc:
        result.warnings.append(f"ID3 frame scan failed: {exc}")


def extract(path: pathlib.Path, ctx: ExtractContext) -> ExtractionResult:
    result = ExtractionResult()

    try:
        size = path.stat().st_size
    except OSError as exc:
        result.error = f"could not stat file: {exc}"
        return result

    result.metadata["byte_count"] = size
    suffix = path.suffix.lower()

    if suffix == ".wav":
        _wav_metadata(path, result)
    elif suffix in (".mp4", ".mov", ".m4v", ".m4a"):
        _mp4_mvhd_metadata(path, result)
    elif suffix == ".mp3":
        _mp3_id3_metadata(path, result)
    else:
        result.warnings.append(
            f"no dedicated metadata parser for {suffix}; reporting file size only"
        )

    result.text = ""
    result.method = "none"
    result.error = None
    result.warnings.append(_NO_TRANSCRIPT_WARNING)
    return result
