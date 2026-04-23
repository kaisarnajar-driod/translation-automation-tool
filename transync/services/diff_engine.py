"""Detect new and modified strings between two versions of strings.xml."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from transync.models.project import StringEntry

logger = logging.getLogger(__name__)


@dataclass
class DiffResult:
    new_entries: list[StringEntry] = field(default_factory=list)
    modified_entries: list[StringEntry] = field(default_factory=list)
    removed_keys: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.new_entries or self.modified_entries)

    @property
    def summary(self) -> str:
        parts = []
        if self.new_entries:
            parts.append(f"{len(self.new_entries)} new")
        if self.modified_entries:
            parts.append(f"{len(self.modified_entries)} modified")
        if self.removed_keys:
            parts.append(f"{len(self.removed_keys)} removed")
        return ", ".join(parts) if parts else "no changes"


class DiffEngine:
    """Compare two sets of string entries to find what changed."""

    @staticmethod
    def compute(
        previous: list[StringEntry],
        current: list[StringEntry],
        detect_modified: bool = False,
    ) -> DiffResult:
        prev_map: dict[str, StringEntry] = {e.key: e for e in previous}
        curr_map: dict[str, StringEntry] = {e.key: e for e in current}

        result = DiffResult()

        for key, entry in curr_map.items():
            if not entry.translatable:
                continue
            if key not in prev_map:
                result.new_entries.append(entry)
                logger.debug("New key: %s", key)
            elif detect_modified and prev_map[key].value != entry.value:
                result.modified_entries.append(entry)
                logger.debug("Modified key: %s", key)

        for key in prev_map:
            if key not in curr_map:
                result.removed_keys.append(key)

        logger.info("Diff result: %s", result.summary)
        return result

    @staticmethod
    def compute_from_dicts(
        previous: dict[str, str],
        current: dict[str, str],
        detect_modified: bool = False,
    ) -> DiffResult:
        """Convenience method when working with dict snapshots."""
        prev_entries = [StringEntry(key=k, value=v) for k, v in previous.items()]
        curr_entries = [StringEntry(key=k, value=v) for k, v in current.items()]
        return DiffEngine.compute(prev_entries, curr_entries, detect_modified=detect_modified)
