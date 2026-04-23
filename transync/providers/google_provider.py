"""Google Translate provider (REST API v2)."""

from __future__ import annotations

import httpx

from transync.providers.base import (
    TranslationError,
    TranslationProvider,
    TranslationRequest,
    TranslationResult,
)

_TRANSLATE_URL = "https://translation.googleapis.com/language/translate/v2"


class GoogleTranslateProvider(TranslationProvider):
    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise TranslationError("Google Translate API key is required")
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "google"

    def translate_batch(
        self, requests: list[TranslationRequest]
    ) -> list[TranslationResult]:
        if not requests:
            return []

        target_lang = requests[0].target_language
        texts = [r.source_text for r in requests]

        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(
                    _TRANSLATE_URL,
                    params={"key": self._api_key},
                    json={
                        "q": texts,
                        "target": target_lang,
                        "source": "en",
                        "format": "html",  # preserves HTML tags
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            raise TranslationError(f"Google Translate API error: {exc}") from exc

        translations = data.get("data", {}).get("translations", [])
        if len(translations) != len(requests):
            raise TranslationError(
                f"Expected {len(requests)} translations, got {len(translations)}"
            )

        results: list[TranslationResult] = []
        for req, t in zip(requests, translations):
            results.append(
                TranslationResult(
                    key=req.key,
                    source_text=req.source_text,
                    translated_text=t["translatedText"],
                    target_language=target_lang,
                    provider=self.name,
                )
            )
        return results
