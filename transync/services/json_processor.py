"""JSON parser/writer for string resource files.

Handles flat key-value JSON files of the form: {"key": "value", ...}
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from transync.models.project import StringEntry

logger = logging.getLogger(__name__)


class JsonError(Exception):
    """Raised on JSON parsing or writing failures."""


class JsonProcessor:
    """Read and write JSON string resource files."""

    # ── Parsing ───────────────────────────────────────────────────

    @staticmethod
    def parse_strings(path: Path) -> list[StringEntry]:
        """Parse a JSON file into a list of StringEntry objects."""
        if not path.is_file():
            raise JsonError(f"File not found: {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError) as exc:
            raise JsonError(f"JSON parse error in {path}: {exc}") from exc

        if not isinstance(data, dict):
            raise JsonError(f"Expected a JSON object in {path}, got {type(data).__name__}")

        return [
            StringEntry(key=k, value=v, translatable=True)
            for k, v in data.items()
            if isinstance(v, str)
        ]

    @staticmethod
    def parse_strings_from_content(content: str) -> list[StringEntry]:
        """Parse string entries from a raw JSON string."""
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, ValueError) as exc:
            raise JsonError(f"JSON parse error: {exc}") from exc

        if not isinstance(data, dict):
            raise JsonError(f"Expected a JSON object, got {type(data).__name__}")

        return [
            StringEntry(key=k, value=v, translatable=True)
            for k, v in data.items()
            if isinstance(v, str)
        ]

    # ── Writing ───────────────────────────────────────────────────

    @staticmethod
    def write_strings(path: Path, entries: list[StringEntry], sort_keys: bool = True) -> None:
        """Write a list of StringEntry objects to a JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)

        if sort_keys:
            entries = sorted(entries, key=lambda e: e.key)

        data = {e.key: e.value for e in entries}
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        logger.debug("Wrote %d entries to %s", len(entries), path)

    # ── Merge ─────────────────────────────────────────────────────

    @staticmethod
    def merge_into_file(
        path: Path,
        new_entries: list[StringEntry],
        sort_keys: bool = True,
    ) -> list[str]:
        """Merge new entries into an existing JSON file, skipping duplicates.

        Returns list of actually added keys.
        """
        existing: list[StringEntry] = []
        if path.is_file():
            existing = JsonProcessor.parse_strings(path)

        existing_keys = {e.key for e in existing}
        added_keys: list[str] = []
        for entry in new_entries:
            if entry.key not in existing_keys:
                existing.append(entry)
                existing_keys.add(entry.key)
                added_keys.append(entry.key)

        JsonProcessor.write_strings(path, existing, sort_keys=sort_keys)
        return added_keys

    # ── Removal ───────────────────────────────────────────────────

    @staticmethod
    def remove_keys_from_file(
        path: Path,
        keys_to_remove: list[str],
        sort_keys: bool = True,
    ) -> list[str]:
        """Remove keys from an existing JSON file. Returns actually removed keys."""
        if not path.is_file():
            return []

        existing = JsonProcessor.parse_strings(path)
        remove_set = set(keys_to_remove)
        removed: list[str] = []
        kept: list[StringEntry] = []

        for entry in existing:
            if entry.key in remove_set:
                removed.append(entry.key)
            else:
                kept.append(entry)

        if removed:
            JsonProcessor.write_strings(path, kept, sort_keys=sort_keys)
            logger.debug("Removed %d keys from %s", len(removed), path)

        return removed

    # ── Utilities ─────────────────────────────────────────────────

    @staticmethod
    def entries_to_dict(entries: list[StringEntry]) -> dict[str, str]:
        return {e.key: e.value for e in entries}
