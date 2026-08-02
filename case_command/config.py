"""Canonical paths and folder policy for Case Command.

Every path in the system resolves through this module. The defaults are the
production locations on Jacob's machine; each may be overridden by environment
variable so the exact same code runs on a laptop, a test fixture tree, or CI
without edits.

    CASE_COMMAND_APP_ROOT    default /opt/JarvisOS
    CASE_COMMAND_DATA_ROOT   default /Volumes/JarvisSSD/Kerr_Court_Cases
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_APP_ROOT = Path("/opt/JarvisOS")
DEFAULT_DATA_ROOT = Path("/Volumes/JarvisSSD/Kerr_Court_Cases")

# The complete, closed set of litigation folders. Nothing else is created at the
# top level of the data root, and ingestion refuses to route outside this set.
INBOX = "00_INBOX"
PSC_AEP = "01_PSC_AEP"
MORTGAGE = "02_MORTGAGE"
BRIDGEPORT = "03_BRIDGEPORT"
VETERANS = "04_VETERANS"
OTHER_CASES = "05_OTHER_CASES"
SHARED_EVIDENCE = "06_SHARED_EVIDENCE"
FINAL_FILINGS = "07_FINAL_FILINGS"
ARCHIVE = "99_ARCHIVE"

LITIGATION_FOLDERS = (
    INBOX,
    PSC_AEP,
    MORTGAGE,
    BRIDGEPORT,
    VETERANS,
    OTHER_CASES,
    SHARED_EVIDENCE,
    FINAL_FILINGS,
    ARCHIVE,
)

FOLDER_PURPOSE = {
    INBOX: "New, unsorted, scanned, emailed, downloaded, or manually added material.",
    PSC_AEP: "PSC, Appalachian Power, AEP, utility shutoff, tariff, meter, hearing, appeal, mandamus, Rule 60.",
    MORTGAGE: "Rocket, PHH, Onity, VA mortgage, RESPA, foreclosure, servicing, loss mitigation, settlement.",
    BRIDGEPORT: "Bridgeport, Belmont County, ADA, trial, motions, exhibits, correspondence.",
    VETERANS: "VA disability, benefits, housing, mortgage assistance, SMC, dependent, appeal.",
    OTHER_CASES: "Any legal matter not covered by another folder.",
    SHARED_EVIDENCE: "Evidence used across multiple matters. Stored once, linked many times.",
    FINAL_FILINGS: "Only documents actually filed, sent, served, accepted, docketed, or entered. No drafts.",
    ARCHIVE: "Superseded drafts, duplicates, obsolete exports, rejected versions, historical material.",
}

# Folders whose contents are watched for new material. 99_ARCHIVE is watched so
# that archived material stays indexed, but nothing is ever auto-promoted out of
# it.
WATCHED_FOLDERS = LITIGATION_FOLDERS


@dataclass(frozen=True)
class Config:
    """Resolved filesystem layout. Construct via :func:`load_config`."""

    app_root: Path
    data_root: Path

    # -- derived control-plane locations -------------------------------------
    @property
    def control_root(self) -> Path:
        return self.data_root / ".case_command"

    @property
    def db_path(self) -> Path:
        return self.control_root / "case_command.sqlite3"

    @property
    def text_dir(self) -> Path:
        return self.control_root / "text"

    @property
    def previews_dir(self) -> Path:
        return self.control_root / "previews"

    @property
    def manifests_dir(self) -> Path:
        return self.control_root / "manifests"

    @property
    def fleet_dir(self) -> Path:
        return self.control_root / "fleet"

    @property
    def backups_dir(self) -> Path:
        return self.control_root / "backups"

    @property
    def queue_dir(self) -> Path:
        """Durable ingestion queue. Survives restarts."""
        return self.control_root / "queue"

    @property
    def logs_dir(self) -> Path:
        return self.control_root / "logs"

    @property
    def source_root(self) -> Path:
        return self.app_root / "case_command"

    def folder(self, name: str) -> Path:
        if name not in LITIGATION_FOLDERS:
            raise ValueError(
                f"{name!r} is not an approved litigation folder. "
                f"Approved: {', '.join(LITIGATION_FOLDERS)}"
            )
        return self.data_root / name

    @property
    def control_dirs(self) -> tuple[Path, ...]:
        return (
            self.control_root,
            self.text_dir,
            self.previews_dir,
            self.manifests_dir,
            self.fleet_dir,
            self.backups_dir,
            self.queue_dir,
            self.logs_dir,
        )

    def is_control_path(self, path: Path) -> bool:
        """True when *path* lives under .case_command (never ingested as evidence)."""
        try:
            path.resolve().relative_to(self.control_root.resolve())
            return True
        except (ValueError, OSError):
            return False


def load_config(data_root: str | os.PathLike[str] | None = None,
                app_root: str | os.PathLike[str] | None = None) -> Config:
    """Resolve configuration from explicit arguments, then environment, then defaults."""
    resolved_data = Path(
        data_root
        or os.environ.get("CASE_COMMAND_DATA_ROOT")
        or DEFAULT_DATA_ROOT
    ).expanduser()
    resolved_app = Path(
        app_root
        or os.environ.get("CASE_COMMAND_APP_ROOT")
        or DEFAULT_APP_ROOT
    ).expanduser()
    return Config(app_root=resolved_app, data_root=resolved_data)


def ensure_layout(config: Config) -> list[Path]:
    """Create the approved folder structure and control directories.

    Creation only. This function never deletes, moves, or renames anything.
    Returns the list of directories that did not previously exist.
    """
    created: list[Path] = []
    targets = [config.data_root]
    targets += [config.data_root / name for name in LITIGATION_FOLDERS]
    targets += list(config.control_dirs)
    for path in targets:
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            created.append(path)
    return created


def unexpected_top_level_folders(config: Config) -> list[str]:
    """Top-level directories in the data root that are not part of the approved set.

    Reported by the health check so folder sprawl is visible, never auto-removed.
    """
    if not config.data_root.exists():
        return []
    approved = set(LITIGATION_FOLDERS) | {".case_command"}
    found = []
    for child in sorted(config.data_root.iterdir()):
        if child.is_dir() and child.name not in approved:
            found.append(child.name)
    return found
