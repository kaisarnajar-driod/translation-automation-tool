"""Robust XML parser/writer for strings.xml resources.

Uses lxml for parsing to handle edge cases: CDATA, HTML entities, namespaces.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from lxml import etree

from transync.models.project import StringEntry

logger = logging.getLogger(__name__)

_XML_HEADER = '<?xml version="1.0" encoding="utf-8"?>\n'

# Matches format placeholders: %s, %d, %1$s, %2$d, etc.
PLACEHOLDER_RE = re.compile(r"%(\d+\$)?[sdfc]")


class XmlError(Exception):
    """Raised on XML parsing or writing failures."""


class XmlProcessor:
    """Read and write strings.xml files."""

    # ── Parsing ───────────────────────────────────────────────────

    @staticmethod
    def parse_strings(path: Path) -> list[StringEntry]:
        """Parse a strings.xml file into a list of StringEntry objects."""
        if not path.is_file():
            raise XmlError(f"File not found: {path}")
        try:
            tree = etree.parse(str(path))  # noqa: S320
        except etree.XMLSyntaxError as exc:
            raise XmlError(f"XML parse error in {path}: {exc}") from exc

        entries: list[StringEntry] = []
        root = tree.getroot()
        if root.tag != "resources":
            raise XmlError(f"Expected <resources> root, got <{root.tag}>")

        for elem in root.iterchildren("string"):
            name = elem.get("name")
            if not name:
                continue
            translatable = elem.get("translatable", "true").lower() != "false"
            value = XmlProcessor._extract_text(elem)
            entries.append(StringEntry(key=name, value=value, translatable=translatable))
        return entries

    @staticmethod
    def parse_strings_from_content(content: str) -> list[StringEntry]:
        """Parse strings.xml content from a raw XML string."""
        try:
            root = etree.fromstring(content.encode("utf-8"))  # noqa: S320
        except etree.XMLSyntaxError as exc:
            raise XmlError(f"XML parse error: {exc}") from exc

        entries: list[StringEntry] = []
        for elem in root.iterchildren("string"):
            name = elem.get("name")
            if not name:
                continue
            translatable = elem.get("translatable", "true").lower() != "false"
            value = XmlProcessor._extract_text(elem)
            entries.append(StringEntry(key=name, value=value, translatable=translatable))
        return entries

    @staticmethod
    def _extract_text(elem: etree._Element) -> str:
        """Extract full inner text including mixed content (HTML tags inside strings)."""
        parts: list[str] = []
        if elem.text:
            parts.append(elem.text)
        for child in elem:
            parts.append(etree.tostring(child, encoding="unicode"))
        return "".join(parts).strip()

    # ── Writing ───────────────────────────────────────────────────

    @staticmethod
    def write_strings(path: Path, entries: list[StringEntry], sort_keys: bool = True) -> None:
        """Write a list of StringEntry objects to a strings.xml file."""
        path.parent.mkdir(parents=True, exist_ok=True)

        if sort_keys:
            entries = sorted(entries, key=lambda e: e.key)

        root = etree.Element("resources")
        root.text = "\n    "

        for i, entry in enumerate(entries):
            string_elem = etree.SubElement(root, "string")
            string_elem.set("name", entry.key)
            if not entry.translatable:
                string_elem.set("translatable", "false")

            # Preserve inner HTML/entities by parsing the value as a fragment
            if _looks_like_html(entry.value):
                try:
                    fragment = etree.fromstring(f"<wrapper>{entry.value}</wrapper>")
                    string_elem.text = fragment.text
                    for child in fragment:
                        string_elem.append(child)
                except etree.XMLSyntaxError:
                    string_elem.text = entry.value
            else:
                string_elem.text = entry.value

            is_last = i == len(entries) - 1
            string_elem.tail = "\n" if is_last else "\n    "

        xml_bytes = etree.tostring(root, encoding="unicode", pretty_print=False)
        path.write_text(_XML_HEADER + xml_bytes + "\n", encoding="utf-8")
        logger.debug("Wrote %d entries to %s", len(entries), path)

    # ── Merge ─────────────────────────────────────────────────────

    @staticmethod
    def merge_into_file(
        path: Path,
        new_entries: list[StringEntry],
        sort_keys: bool = True,
    ) -> list[str]:
        """Merge new entries into an existing strings.xml, skipping duplicates.

        Returns list of actually added keys.
        """
        existing: list[StringEntry] = []
        if path.is_file():
            existing = XmlProcessor.parse_strings(path)

        existing_keys = {e.key for e in existing}
        added_keys: list[str] = []
        for entry in new_entries:
            if entry.key not in existing_keys:
                existing.append(entry)
                existing_keys.add(entry.key)
                added_keys.append(entry.key)

        XmlProcessor.write_strings(path, existing, sort_keys=sort_keys)
        return added_keys

    # ── Removal ───────────────────────────────────────────────────

    @staticmethod
    def remove_keys_from_file(
        path: Path,
        keys_to_remove: list[str],
        sort_keys: bool = True,
    ) -> list[str]:
        """Remove keys from an existing strings.xml. Returns actually removed keys."""
        if not path.is_file():
            return []

        existing = XmlProcessor.parse_strings(path)
        remove_set = set(keys_to_remove)
        removed: list[str] = []
        kept: list[StringEntry] = []

        for entry in existing:
            if entry.key in remove_set:
                removed.append(entry.key)
            else:
                kept.append(entry)

        if removed:
            XmlProcessor.write_strings(path, kept, sort_keys=sort_keys)
            logger.debug("Removed %d keys from %s", len(removed), path)

        return removed

    # ── Utilities ─────────────────────────────────────────────────

    @staticmethod
    def entries_to_dict(entries: list[StringEntry]) -> dict[str, str]:
        return {e.key: e.value for e in entries}

    @staticmethod
    def validate_placeholders(original: str, translated: str) -> bool:
        """Verify that format placeholders survive translation intact."""
        orig_phs = sorted(PLACEHOLDER_RE.findall(original))
        trans_phs = sorted(PLACEHOLDER_RE.findall(translated))
        return orig_phs == trans_phs


def _looks_like_html(text: str) -> bool:
    return bool(re.search(r"<[a-zA-Z]", text))
