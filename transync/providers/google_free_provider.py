"""Free Google Translate provider using deep-translator (no API key required).

Uses the same Google Neural Machine Translation models that power ML Kit
On-Device Translation, but accessible from Python without needing an
Android/iOS device.
"""

from __future__ import annotations

import logging
import time

from transync.providers.base import (
    TranslationError,
    TranslationProvider,
    TranslationRequest,
    TranslationResult,
)

logger = logging.getLogger(__name__)

_MAX_CHARS_PER_REQUEST = 4500


class GoogleFreeProvider(TranslationProvider):
    """Translates via Google Translate's free web API (no key needed)."""

    @property
    def name(self) -> str:
        return "google_free"

    def translate_batch(
        self, requests: list[TranslationRequest]
    ) -> list[TranslationResult]:
        if not requests:
            return []

        try:
            from deep_translator import GoogleTranslator
        except ImportError as exc:
            raise TranslationError(
                "deep-translator is required for google_free provider. "
                "Install it with: pip install deep-translator"
            ) from exc

        target_lang = requests[0].target_language
        results: list[TranslationResult] = []

        for req in requests:
            translated_text = self._translate_single(
                GoogleTranslator, req.source_text, target_lang
            )
            results.append(
                TranslationResult(
                    key=req.key,
                    source_text=req.source_text,
                    translated_text=translated_text,
                    target_language=target_lang,
                    provider=self.name,
                )
            )

        return results

    def _translate_single(
        self,
        translator_cls: type,
        text: str,
        target_lang: str,
    ) -> str:
        """Translate a single string, handling long texts by chunking."""
        if not text.strip():
            return text

        try:
            translator = translator_cls(source="en", target=target_lang)

            if len(text) <= _MAX_CHARS_PER_REQUEST:
                result = translator.translate(text)
                time.sleep(0.15)
                return result or text

            chunks = self._split_text(text)
            translated_parts = []
            for chunk in chunks:
                part = translator.translate(chunk)
                translated_parts.append(part or chunk)
                time.sleep(0.15)
            return " ".join(translated_parts)

        except Exception as exc:
            logger.warning("Translation failed for text (%.40s...): %s", text, exc)
            raise TranslationError(f"Google free translation failed: {exc}") from exc

    @staticmethod
    def _split_text(text: str) -> list[str]:
        """Split long text into chunks that fit within the API limit."""
        words = text.split()
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0

        for word in words:
            if current_len + len(word) + 1 > _MAX_CHARS_PER_REQUEST and current:
                chunks.append(" ".join(current))
                current = []
                current_len = 0
            current.append(word)
            current_len += len(word) + 1

        if current:
            chunks.append(" ".join(current))
        return chunks
