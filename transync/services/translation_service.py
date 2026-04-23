"""Translation service — facade over pluggable translation providers."""

from __future__ import annotations

import logging
import re

from transync.config import AppConfig
from transync.models.project import StringEntry
from transync.providers.base import (
    TranslationError,
    TranslationProvider,
    TranslationRequest,
)
from transync.services.xml_processor import PLACEHOLDER_RE

logger = logging.getLogger(__name__)


class TranslationService:
    """Orchestrates translation using a configured provider."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._provider = self._build_provider(config)

    @staticmethod
    def _build_provider(config: AppConfig) -> TranslationProvider:
        name = config.translation.provider.lower()
        if name == "openai":
            from transync.providers.openai_provider import OpenAIProvider

            c = config.translation.openai
            return OpenAIProvider(
                api_key=c.api_key,
                model=c.model,
                max_batch_size=c.max_batch_size,
                temperature=c.temperature,
            )
        if name == "deepl":
            from transync.providers.deepl_provider import DeepLProvider

            return DeepLProvider(api_key=config.translation.deepl.api_key)
        if name == "google":
            from transync.providers.google_provider import GoogleTranslateProvider

            return GoogleTranslateProvider(api_key=config.translation.google.api_key)
        if name == "google_free":
            from transync.providers.google_free_provider import GoogleFreeProvider

            return GoogleFreeProvider()
        if name == "mock":
            from transync.providers.mock_provider import MockProvider

            return MockProvider()
        raise TranslationError(f"Unknown translation provider: {name}")

    @property
    def provider_name(self) -> str:
        return self._provider.name

    def translate_entries(
        self,
        entries: list[StringEntry],
        target_language: str,
    ) -> list[StringEntry]:
        """Translate a list of StringEntry to the target language.

        Returns new StringEntry objects with translated values. Validates that
        placeholders survive translation; falls back to source on corruption.
        """
        requests = [
            TranslationRequest(key=e.key, source_text=e.value, target_language=target_language)
            for e in entries
        ]

        logger.info(
            "Translating %d strings to '%s' via %s",
            len(requests),
            target_language,
            self._provider.name,
        )

        results = self._provider.translate_batch(requests)
        translated: list[StringEntry] = []

        for entry, result in zip(entries, results):
            text = result.translated_text
            if not self._validate_translation(entry.value, text):
                logger.warning(
                    "Placeholder mismatch for key '%s' (lang=%s), using source text",
                    entry.key,
                    target_language,
                )
                text = entry.value
            translated.append(StringEntry(key=entry.key, value=text, translatable=entry.translatable))

        return translated

    @staticmethod
    def _validate_translation(source: str, translated: str) -> bool:
        """Verify placeholders and critical patterns are intact."""
        src_phs = sorted(PLACEHOLDER_RE.findall(source))
        tgt_phs = sorted(PLACEHOLDER_RE.findall(translated))
        if src_phs != tgt_phs:
            return False

        # Also check that HTML-like tags are roughly preserved
        src_tags = sorted(re.findall(r"</?[a-zA-Z][^>]*>", source))
        tgt_tags = sorted(re.findall(r"</?[a-zA-Z][^>]*>", translated))
        if src_tags != tgt_tags:
            return False

        return True
