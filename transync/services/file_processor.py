"""Factory for selecting the correct file processor and resolving
platform-specific output paths for translated string files.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Union

from transync.services.json_processor import JsonProcessor
from transync.services.strings_processor import StringsProcessor
from transync.services.xml_processor import XmlProcessor

if TYPE_CHECKING:
    from transync.models.project import Project

ProcessorType = Union[XmlProcessor, JsonProcessor, StringsProcessor]


def get_processor(strings_path: str) -> ProcessorType:
    """Return the appropriate processor based on the file extension."""
    if strings_path.endswith(".json"):
        return JsonProcessor()
    if strings_path.endswith(".strings"):
        return StringsProcessor()
    return XmlProcessor()


def get_lang_file_path(project: Project, lang: str) -> Path:
    """Return the absolute path for a language-specific strings file.

    Auto-detects platform convention from the source strings_path:
      - Android:  values/strings.xml          -> values-{lang}/strings.xml
      - iOS:      en.lproj/Localizable.strings -> {lang}.lproj/Localizable.strings
      - Generic:  locales/en/strings.json      -> locales/{lang}/strings.json
    """
    source = project.absolute_strings_path
    parent_name = source.parent.name
    grandparent = source.parent.parent
    filename = source.name

    if parent_name == "values" or parent_name.startswith("values-"):
        return grandparent / f"values-{lang}" / filename

    if parent_name.endswith(".lproj"):
        return grandparent / f"{lang}.lproj" / filename

    return grandparent / lang / filename
