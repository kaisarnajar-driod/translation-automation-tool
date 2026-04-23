"""Domain models for managed projects and sync history."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class SyncStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class Project:
    id: int | None
    name: str
    repo_url: str
    local_path: str
    branch: str = "main"
    strings_path: str = "strings.xml"
    target_languages: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def absolute_strings_path(self) -> Path:
        return Path(self.local_path) / self.strings_path

    @property
    def absolute_res_directory(self) -> Path:
        """Derived from strings_path: the grandparent of the strings file."""
        return self.absolute_strings_path.parent.parent


@dataclass
class SyncRecord:
    id: int | None
    project_id: int
    status: SyncStatus
    new_keys: int = 0
    modified_keys: int = 0
    removed_keys: int = 0
    languages_synced: int = 0
    commit_sha: str = ""
    error_message: str = ""
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str = ""


@dataclass
class StringEntry:
    """A single <string> element from a strings XML resource file."""
    key: str
    value: str
    translatable: bool = True
