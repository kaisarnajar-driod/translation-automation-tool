"""DeepL translation provider."""

from __future__ import annotations

import deepl

from transync.providers.base import (
    TranslationError,
    TranslationProvider,
    TranslationRequest,
    TranslationResult,
)

# DeepL uses different language codes than BCP-47 in some cases
_LANG_MAP = {
    "en": "EN-US",
    "pt": "PT-BR",
    "zh": "ZH-HANS",
}


class DeepLProvider(TranslationProvider):
    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise TranslationError("DeepL API key is required")
        self._translator = deepl.Translator(api_key)

    @property
    def name(self) -> str:
        return "deepl"

    def translate_batch(
        self, requests: list[TranslationRequest]
    ) -> list[TranslationResult]:
        if not requests:
            return []

        target_lang = requests[0].target_language
        deepl_lang = _LANG_MAP.get(target_lang, target_lang).upper()
        texts = [r.source_text for r in requests]

        try:
            translations = self._translator.translate_text(
                texts,
                target_lang=deepl_lang,
                tag_handling="xml",
                preserve_formatting=True,
            )
        except deepl.DeepLException as exc:
            raise TranslationError(f"DeepL translation failed: {exc}") from exc

        if not isinstance(translations, list):
            translations = [translations]

        results: list[TranslationResult] = []
        for req, t in zip(requests, translations):
            results.append(
                TranslationResult(
                    key=req.key,
                    source_text=req.source_text,
                    translated_text=t.text,
                    target_language=target_lang,
                    provider=self.name,
                )
            )
        return results
