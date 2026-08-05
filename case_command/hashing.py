"""Content hashing, manifests, and duplicate detection."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from .config import Config, LITIGATION_FOLDERS
from .db import atomic_write_json, utcnow

CHUNK = 1024 * 1024


def sha256_file(path: Path) -> str:
    """Hash a file without loading it into memory. Read-only."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class FileRecord:
    path: str
    relative_path: str
    folder: str
    sha256: str
    byte_size: int
    modified: str

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "relative_path": self.relative_path,
            "folder": self.folder,
            "sha256": self.sha256,
            "byte_size": self.byte_size,
            "modified": self.modified,
        }


def iter_litigation_files(config: Config,
                          folders: Iterable[str] | None = None) -> Iterator[Path]:
    """Yield every real file in the approved folders.

    Skips the .case_command control tree, dotfiles, macOS resource forks, and
    partial-write temp files so ingestion never picks up its own output.
    """
    from datetime import datetime, timezone  # local import keeps module import cheap
    _ = datetime, timezone

    for folder_name in (folders or LITIGATION_FOLDERS):
        root = config.data_root / folder_name
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if config.is_control_path(path):
                continue
            name = path.name
            if name.startswith(".") or name.startswith("._") or name.startswith("~$"):
                continue
            if name.endswith(".part") or name.endswith(".crdownload"):
                continue
            yield path


def folder_of(config: Config, path: Path) -> str:
    """Which approved top-level folder a path lives in ('' when outside)."""
    try:
        relative = path.resolve().relative_to(config.data_root.resolve())
    except (ValueError, OSError):
        return ""
    return relative.parts[0] if relative.parts else ""


def inventory(config: Config, folders: Iterable[str] | None = None) -> list[FileRecord]:
    """Read-only inventory of the litigation tree. Modifies nothing."""
    from datetime import datetime, timezone

    records: list[FileRecord] = []
    for path in iter_litigation_files(config, folders):
        try:
            stat = path.stat()
            digest = sha256_file(path)
        except OSError as exc:  # unreadable file is reported, never skipped silently
            records.append(FileRecord(
                path=str(path),
                relative_path=str(path.relative_to(config.data_root)),
                folder=folder_of(config, path),
                sha256=f"ERROR:{exc.__class__.__name__}",
                byte_size=-1,
                modified="",
            ))
            continue
        records.append(FileRecord(
            path=str(path),
            relative_path=str(path.relative_to(config.data_root)),
            folder=folder_of(config, path),
            sha256=digest,
            byte_size=stat.st_size,
            modified=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        ))
    return records


def find_duplicates(records: list[FileRecord]) -> dict[str, list[FileRecord]]:
    """Group records by hash, returning only hashes with more than one file."""
    buckets: dict[str, list[FileRecord]] = {}
    for record in records:
        if record.sha256.startswith("ERROR:"):
            continue
        buckets.setdefault(record.sha256, []).append(record)
    return {h: files for h, files in buckets.items() if len(files) > 1}


def write_manifest(config: Config, name: str, records: list[FileRecord],
                   extra: dict[str, object] | None = None) -> Path:
    """Write a timestamped manifest. Manifests are never overwritten in place."""
    config.manifests_dir.mkdir(parents=True, exist_ok=True)
    stamp = utcnow().replace(":", "").replace("-", "").replace(".", "")
    path = config.manifests_dir / f"{name}_{stamp}.json"
    payload = {
        "manifest": name,
        "generated_at": utcnow(),
        "data_root": str(config.data_root),
        "file_count": len(records),
        "total_bytes": sum(r.byte_size for r in records if r.byte_size > 0),
        "files": [r.to_dict() for r in records],
    }
    if extra:
        payload.update(extra)
    atomic_write_json(path, payload)
    return path


def read_manifest(path: Path) -> dict[str, object]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify_manifest(config: Config, manifest_path: Path) -> dict[str, list[str]]:
    """Re-hash everything a manifest lists and report drift.

    Used after a restore to prove nothing changed, and by the health check.
    """
    data = read_manifest(manifest_path)
    problems: dict[str, list[str]] = {"missing": [], "changed": [], "ok": []}
    for entry in data.get("files", []):
        path = Path(str(entry["path"]))
        if not path.exists():
            problems["missing"].append(str(path))
            continue
        try:
            digest = sha256_file(path)
        except OSError as exc:
            problems["missing"].append(f"{path} ({exc})")
            continue
        if digest != entry["sha256"]:
            problems["changed"].append(str(path))
        else:
            problems["ok"].append(str(path))
    return problems
