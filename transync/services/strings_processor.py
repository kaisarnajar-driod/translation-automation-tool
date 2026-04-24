"""iOS .strings parser/writer for Localizable.strings resource files.

Handles the Apple .strings format: "key" = "value";
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from transync.models.project import StringEntry

logger = logging.getLogger(__name__)

_LINE_RE = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"\s*=\s*"([^"\\]*(?:\\.[^"\\]*)*)"\s*;')


class StringsError(Exception):
    """Raised on .strings parsing or writing failures."""


class StringsProcessor:
    """Read and write iOS Localizable.strings files."""

    # ── Parsing ───────────────────────────────────────────────────

    @staticmethod
    def parse_strings(path: Path) -> list[StringEntry]:
        """Parse a .strings file into a list of StringEntry objects."""
        if not path.is_file():
            raise StringsError(f"File not found: {path}")
        content = path.read_text(encoding="utf-8")
        return StringsProcessor._parse(content, str(path))

    @staticmethod
    def parse_strings_from_content(content: str) -> list[StringEntry]:
        """Parse string entries from raw .strings content."""
        return StringsProcessor._parse(content, "<content>")

    @staticmethod
    def _parse(content: str, source_label: str) -> list[StringEntry]:
        entries: list[StringEntry] = []
        for match in _LINE_RE.finditer(content):
            key = match.group(1).replace('\\"', '"').replace("\\n", "\n")
            value = match.group(2).replace('\\"', '"').replace("\\n", "\n")
            entries.append(StringEntry(key=key, value=value, translatable=True))
        if not entries and content.strip():
            logger.warning("No entries parsed from %s — check the file format", source_label)
        return entries

    # ── Writing ───────────────────────────────────────────────────

    @staticmethod
    def write_strings(path: Path, entries: list[StringEntry], sort_keys: bool = True) -> None:
        """Write a list of StringEntry objects to a .strings file."""
        path.parent.mkdir(parents=True, exist_ok=True)

        if sort_keys:
            entries = sorted(entries, key=lambda e: e.key)

        lines: list[str] = []
        for e in entries:
            escaped_key = e.key.replace('"', '\\"')
            escaped_val = e.value.replace('"', '\\"')
            lines.append(f'"{escaped_key}" = "{escaped_val}";')

        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        logger.debug("Wrote %d entries to %s", len(entries), path)

    # ── Merge ─────────────────────────────────────────────────────

    @staticmethod
    def merge_into_file(
        path: Path,
        new_entries: list[StringEntry],
        sort_keys: bool = True,
    ) -> list[str]:
        """Merge new entries into an existing .strings file, skipping duplicates.

        Returns list of actually added keys.
        """
        existing: list[StringEntry] = []
        if path.is_file():
            existing = StringsProcessor.parse_strings(path)

        existing_keys = {e.key for e in existing}
        added_keys: list[str] = []
        for entry in new_entries:
            if entry.key not in existing_keys:
                existing.append(entry)
                existing_keys.add(entry.key)
                added_keys.append(entry.key)

        StringsProcessor.write_strings(path, existing, sort_keys=sort_keys)
        return added_keys

    # ── Removal ───────────────────────────────────────────────────

    @staticmethod
    def remove_keys_from_file(
        path: Path,
        keys_to_remove: list[str],
        sort_keys: bool = True,
    ) -> list[str]:
        """Remove keys from an existing .strings file. Returns actually removed keys."""
        if not path.is_file():
            return []

        existing = StringsProcessor.parse_strings(path)
        remove_set = set(keys_to_remove)
        removed: list[str] = []
        kept: list[StringEntry] = []

        for entry in existing:
            if entry.key in remove_set:
                removed.append(entry.key)
            else:
                kept.append(entry)

        if removed:
            StringsProcessor.write_strings(path, kept, sort_keys=sort_keys)
            logger.debug("Removed %d keys from %s", len(removed), path)

        return removed

    # ── Utilities ─────────────────────────────────────────────────

    @staticmethod
    def entries_to_dict(entries: list[StringEntry]) -> dict[str, str]:
        return {e.key: e.value for e in entries}
