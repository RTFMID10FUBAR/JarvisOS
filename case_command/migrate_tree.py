"""Migration of an existing, disorganized litigation tree.

The seven-step sequence from the specification:

    1. inventory existing files
    2. calculate hashes
    3. detect duplicates
    4. propose moves
    5. perform a dry run
    6. require approval before changing original locations
    7. preserve a rollback manifest

Steps 1-5 are always safe: they read, hash, and write plans. Step 6 is the only
place a file is touched, it is off unless `approved=True` is passed explicitly,
and it writes a rollback manifest before the first move.

This is built for a tree that has accumulated several competing organizational
schemes with content-identical copies scattered across them. Identity is
determined by SHA-256 of file bytes, never by filename or location, so copies
made by another tool collapse into one canonical document plus flagged
duplicates.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import audit
from .classify import classify_text
from .config import ARCHIVE, Config, INBOX, LITIGATION_FOLDERS
from .db import atomic_write_json, utcnow
from .extract import ExtractContext, extract_file
from .hashing import FileRecord, find_duplicates, inventory, sha256_file, write_manifest


@dataclass
class Move:
    """A proposed relocation. Nothing acts on this without explicit approval."""

    source: str
    destination: str
    reason: str
    sha256: str
    byte_size: int
    kind: str            # CLASSIFY | DEDUPE | ARCHIVE
    confidence: float = 0.0
    keep_original: bool = False
    conflict: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source, "destination": self.destination,
            "reason": self.reason, "sha256": self.sha256,
            "byte_size": self.byte_size, "kind": self.kind,
            "confidence": round(self.confidence, 3),
            "keep_original": self.keep_original, "conflict": self.conflict,
        }


@dataclass
class MigrationPlan:
    generated_at: str
    data_root: str
    file_count: int
    total_bytes: int
    duplicate_groups: int
    duplicate_wasted_bytes: int
    moves: list[Move] = field(default_factory=list)
    unreadable: list[str] = field(default_factory=list)
    unexpected_folders: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    inventory_manifest: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "data_root": self.data_root,
            "file_count": self.file_count,
            "total_bytes": self.total_bytes,
            "duplicate_groups": self.duplicate_groups,
            "duplicate_wasted_bytes": self.duplicate_wasted_bytes,
            "move_count": len(self.moves),
            "moves_by_kind": {
                kind: sum(1 for m in self.moves if m.kind == kind)
                for kind in ("CLASSIFY", "DEDUPE", "ARCHIVE")
            },
            "conflicts": sum(1 for m in self.moves if m.conflict),
            "unreadable": self.unreadable,
            "unexpected_folders": self.unexpected_folders,
            "warnings": self.warnings,
            "inventory_manifest": self.inventory_manifest,
            "moves": [m.to_dict() for m in self.moves],
        }


def _unique_destination(destination: Path, taken: set[str]) -> Path:
    """Never overwrite. Append a numeric suffix if the name is already used."""
    candidate = destination
    index = 1
    while candidate.exists() or str(candidate) in taken:
        candidate = destination.with_name(f"{destination.stem}__{index}{destination.suffix}")
        index += 1
    return candidate


def build_plan(config: Config, *, sample_text_bytes: int = 200_000,
               classify_contents: bool = True) -> MigrationPlan:
    """Steps 1-4: inventory, hash, detect duplicates, propose moves. Read-only."""
    from .config import unexpected_top_level_folders

    records: list[FileRecord] = inventory(config)
    readable = [r for r in records if not r.sha256.startswith("ERROR:")]
    unreadable = [r.path for r in records if r.sha256.startswith("ERROR:")]

    duplicates = find_duplicates(readable)
    wasted = sum(
        files[0].byte_size * (len(files) - 1)
        for files in duplicates.values() if files[0].byte_size > 0
    )

    manifest_path = write_manifest(config, "pre_migration_inventory", records, extra={
        "purpose": "Read-only inventory taken before any migration. Rollback baseline.",
    })

    plan = MigrationPlan(
        generated_at=utcnow(),
        data_root=str(config.data_root),
        file_count=len(records),
        total_bytes=sum(r.byte_size for r in readable),
        duplicate_groups=len(duplicates),
        duplicate_wasted_bytes=wasted,
        unreadable=unreadable,
        unexpected_folders=unexpected_top_level_folders(config),
        inventory_manifest=str(manifest_path),
    )

    if unreadable:
        plan.warnings.append(
            f"{len(unreadable)} file(s) could not be read or hashed. They are listed "
            "and excluded from every proposal — never silently skipped."
        )
    if plan.unexpected_folders:
        plan.warnings.append(
            "Top-level folders outside the approved structure: "
            + ", ".join(plan.unexpected_folders)
            + ". No proposal touches them; consolidating them is a separate decision."
        )

    taken: set[str] = set()

    # --- step 3/4a: duplicates -> propose archiving the redundant copies ----
    duplicate_paths: set[str] = set()
    for digest, files in duplicates.items():
        # Keep the copy in the most specific matter folder; prefer the oldest.
        ranked = sorted(files, key=lambda r: (r.folder in (INBOX, ARCHIVE, ""), r.modified))
        keeper = ranked[0]
        for redundant in ranked[1:]:
            duplicate_paths.add(redundant.path)
            destination = _unique_destination(
                config.folder(ARCHIVE) / "duplicates" / Path(redundant.relative_path).name,
                taken,
            )
            taken.add(str(destination))
            plan.moves.append(Move(
                source=redundant.path,
                destination=str(destination),
                reason=(f"Byte-identical to {keeper.relative_path} (sha256 {digest[:12]}…). "
                        "The canonical copy stays where it is; this copy is proposed for "
                        "archive so the record has one physical location per document."),
                sha256=digest, byte_size=redundant.byte_size, kind="DEDUPE",
                confidence=1.0,
            ))

    # --- step 4b: misfiled originals -> propose reclassification -----------
    if classify_contents:
        for record in readable:
            if record.path in duplicate_paths:
                continue
            if record.folder not in (INBOX, ""):
                continue  # only material sitting in the inbox is proposed for routing

            path = Path(record.path)
            text = ""
            try:
                result = extract_file(path, ExtractContext(allow_ocr=False,
                                                           max_bytes=sample_text_bytes))
                text = result.text
            except Exception as exc:  # a bad file never stops the plan
                plan.warnings.append(f"could not read text of {record.relative_path}: {exc}")

            classification = classify_text(text, filename=path.name,
                                           current_folder=record.folder)
            if classification.folder in (INBOX, record.folder):
                continue
            if classification.confidence < 0.35:
                continue  # too uncertain to propose; it stays in the inbox

            destination = _unique_destination(
                config.folder(classification.folder) / path.name, taken)
            taken.add(str(destination))
            conflict = None
            if classification.cross_reference_folders:
                conflict = (
                    "Also matches " + ", ".join(classification.cross_reference_folders)
                    + ". Stored once here; the other matters get database links, not copies."
                )
            plan.moves.append(Move(
                source=record.path,
                destination=str(destination),
                reason=f"{classification.rule}: " + "; ".join(classification.reasons),
                sha256=record.sha256, byte_size=record.byte_size, kind="CLASSIFY",
                confidence=classification.confidence, conflict=conflict,
            ))

    return plan


def write_plan(config: Config, plan: MigrationPlan) -> Path:
    config.manifests_dir.mkdir(parents=True, exist_ok=True)
    stamp = utcnow().replace(":", "").replace("-", "").replace(".", "")
    path = config.manifests_dir / f"migration_plan_{stamp}.json"
    atomic_write_json(path, plan.to_dict())
    return path


def dry_run(config: Config, plan: MigrationPlan) -> dict[str, Any]:
    """Step 5: verify every move would succeed, without performing any of them."""
    issues: list[str] = []
    ok = 0
    for move in plan.moves:
        source = Path(move.source)
        destination = Path(move.destination)
        if not source.exists():
            issues.append(f"source missing: {source}")
            continue
        if destination.exists():
            issues.append(f"destination already occupied: {destination}")
            continue
        try:
            if sha256_file(source) != move.sha256:
                issues.append(f"content changed since the plan was built: {source}")
                continue
        except OSError as exc:
            issues.append(f"unreadable: {source} ({exc})")
            continue
        if not os.access(source, os.R_OK):
            issues.append(f"not readable: {source}")
            continue
        parent = destination.parent
        probe = parent
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        if not os.access(probe, os.W_OK):
            issues.append(f"destination not writable: {parent}")
            continue
        ok += 1

    return {
        "dry_run": True,
        "moves_planned": len(plan.moves),
        "would_succeed": ok,
        "would_fail": len(issues),
        "issues": issues,
        "verdict": "READY" if not issues else "NOT_READY",
        "note": "No file was touched. Approval is still required to execute.",
    }


def execute(config: Config, conn: sqlite3.Connection, plan: MigrationPlan, *,
            approved: bool = False, actor: str = "migration") -> dict[str, Any]:
    """Step 6/7: perform the plan. Refuses to act unless *approved* is True.

    A rollback manifest is written before the first move, so every relocation
    can be reversed with :func:`rollback`.
    """
    if not approved:
        # This is the guard the specification requires: original locations do
        # not change without Jacob's explicit approval.
        return {
            "executed": False,
            "reason": "approval required",
            "detail": ("execute() refuses to move originals unless approved=True is passed "
                       "explicitly. Review the plan and the dry run first."),
            "moves_planned": len(plan.moves),
        }

    check = dry_run(config, plan)
    if check["verdict"] != "READY":
        return {"executed": False, "reason": "dry run failed", "dry_run": check}

    stamp = utcnow().replace(":", "").replace("-", "").replace(".", "")
    rollback_path = config.manifests_dir / f"rollback_{stamp}.json"
    entries: list[dict[str, Any]] = []
    # Write the rollback manifest BEFORE moving anything, so an interruption
    # still leaves a reversible record.
    atomic_write_json(rollback_path, {
        "created_at": utcnow(), "data_root": str(config.data_root),
        "status": "IN_PROGRESS", "moves": [m.to_dict() for m in plan.moves],
        "completed": entries,
    })

    completed = 0
    failures: list[str] = []
    for move in plan.moves:
        source, destination = Path(move.source), Path(move.destination)
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            after = sha256_file(destination)
            if after != move.sha256:
                # Content changed in transit: put it back immediately.
                shutil.move(str(destination), str(source))
                failures.append(f"hash mismatch after move, reverted: {source}")
                continue
            entries.append({"from": str(source), "to": str(destination),
                            "sha256": move.sha256, "at": utcnow()})
            completed += 1
            conn.execute("UPDATE documents SET storage_path=?, folder=? WHERE sha256=?",
                         (str(destination),
                          Path(destination).relative_to(config.data_root).parts[0],
                          move.sha256))
        except Exception as exc:
            failures.append(f"{source}: {type(exc).__name__}: {exc}")
        finally:
            atomic_write_json(rollback_path, {
                "created_at": utcnow(), "data_root": str(config.data_root),
                "status": "IN_PROGRESS", "moves": [m.to_dict() for m in plan.moves],
                "completed": entries,
            })

    atomic_write_json(rollback_path, {
        "created_at": utcnow(), "data_root": str(config.data_root),
        "status": "COMPLETE", "moves": [m.to_dict() for m in plan.moves],
        "completed": entries, "failures": failures,
    })

    audit.record(conn, actor=actor, action="MIGRATION_EXECUTED",
                 summary=f"{completed}/{len(plan.moves)} move(s)",
                 payload={"rollback_manifest": str(rollback_path), "failures": failures})

    return {
        "executed": True, "moves_completed": completed, "failures": failures,
        "rollback_manifest": str(rollback_path),
        "rollback_command": f"case-command migrate rollback --manifest {rollback_path}",
    }


def rollback(config: Config, conn: sqlite3.Connection, manifest_path: Path, *,
             actor: str = "migration") -> dict[str, Any]:
    """Reverse a completed migration using its rollback manifest."""
    import json

    data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    restored, failures = 0, []
    # Reverse order, so nested directory creation unwinds cleanly.
    for entry in reversed(data.get("completed", [])):
        source, destination = Path(entry["to"]), Path(entry["from"])
        try:
            if not source.exists():
                failures.append(f"missing, cannot restore: {source}")
                continue
            if destination.exists():
                failures.append(f"original location occupied: {destination}")
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            restored += 1
            conn.execute("UPDATE documents SET storage_path=?, folder=? WHERE sha256=?",
                         (str(destination),
                          Path(destination).relative_to(config.data_root).parts[0],
                          entry["sha256"]))
        except Exception as exc:
            failures.append(f"{source}: {type(exc).__name__}: {exc}")

    audit.record(conn, actor=actor, action="MIGRATION_ROLLED_BACK",
                 summary=f"{restored} file(s) restored",
                 payload={"manifest": str(manifest_path), "failures": failures})

    return {"restored": restored, "failures": failures, "manifest": str(manifest_path)}


def summarize_plan(plan: MigrationPlan, limit: int = 15) -> str:
    """Human-readable plan summary for the CLI."""
    lines = [
        f"Data root:          {plan.data_root}",
        f"Files inventoried:  {plan.file_count:,} ({plan.total_bytes / 1_048_576:.1f} MiB)",
        f"Duplicate groups:   {plan.duplicate_groups:,} "
        f"({plan.duplicate_wasted_bytes / 1_048_576:.1f} MiB redundant)",
        f"Moves proposed:     {len(plan.moves):,}",
        f"Unreadable files:   {len(plan.unreadable)}",
        f"Baseline manifest:  {plan.inventory_manifest}",
    ]
    if plan.unexpected_folders:
        lines.append("Folders outside the approved structure: "
                     + ", ".join(plan.unexpected_folders))
    for warning in plan.warnings:
        lines.append(f"  ! {warning}")
    if plan.moves:
        lines.append("")
        lines.append(f"First {min(limit, len(plan.moves))} proposed move(s):")
        for move in plan.moves[:limit]:
            lines.append(f"  [{move.kind}] {Path(move.source).name}")
            lines.append(f"      -> {move.destination}")
            lines.append(f"      {move.reason[:160]}")
    lines.append("")
    lines.append("Nothing has been moved. Run the dry run, then execute with approval.")
    return "\n".join(lines)
